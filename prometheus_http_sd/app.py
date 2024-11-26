import os
import logging
from pathlib import Path


from flask import Flask, jsonify, render_template, request
from .sd import generate, generate_perf, run_python
from .version import VERSION
from .config import config
from prometheus_client import Gauge, Counter, Histogram, Info
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import make_wsgi_app


logger = logging.getLogger(__name__)


path_last_generated_targets = Gauge(
    "httpsd_path_last_generated_targets",
    "Generated targets count in last request",
    ["path"],
)
version_info = Info(
    "httpsd_version",
    "prometheus_http_sd version info",
)
version_info.info({"version": VERSION})
target_path_requests_total = Counter(
    "httpsd_path_requests_total",
    "The total count of a path being requested, status label can be"
    " success/fail",
    ["path", "status", "l1_dir", "l2_dir"],
)
target_path_request_duration_seconds = Histogram(
    "httpsd_target_path_request_duration_seconds",
    "The bucket of request duration in seconds",
    ["path"],
)


def create_app(prefix):
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
    )

    # Add prometheus wsgi middleware to route /metrics requests
    prometheus_wsgi_app = make_wsgi_app()
    app.wsgi_app = DispatcherMiddleware(
        app.wsgi_app,
        {
            "/metrics": prometheus_wsgi_app,
            f"{prefix}/metrics": prometheus_wsgi_app,
        },
    )

    # temp solution, return dynamic scape configs from python file.
    # only support python file, not directory.
    @app.route(f"{prefix}/scrape_configs/<path:rest_path>")
    def get_scrape_configs(rest_path):
        generated = run_python(
            str(Path(config.root_dir) / (rest_path + ".py")), **request.args
        )
        return generated

    @app.route(f"{prefix}/targets", defaults={"rest_path": ""})
    @app.route(f"{prefix}/targets/", defaults={"rest_path": ""})
    # match the rest of the path
    @app.route(f"{prefix}/targets/<path:rest_path>")
    def get_targets(rest_path):

        if request.args.get("debug") == "true":
            arg_list = dict(request.args)
            del arg_list["debug"]
            return generate_perf(config.root_dir, rest_path, **arg_list)

        logger.info(
            "request target path: {}, with parameters: {}".format(
                rest_path,
                request.args,
            )
        )

        l1_dir = l2_dir = ""
        path_splits = rest_path.split("/")
        if len(path_splits) > 0:
            l1_dir = path_splits[0]
        if len(path_splits) > 1:
            l2_dir = path_splits[1]

        with target_path_request_duration_seconds.labels(
            path=rest_path
        ).time():
            try:
                targets = generate(config.root_dir, rest_path, **request.args)
            except:  # noqa: E722
                target_path_requests_total.labels(
                    path=rest_path, status="fail", l1_dir=l1_dir, l2_dir=l2_dir
                ).inc()
                raise
            else:
                target_path_requests_total.labels(
                    path=rest_path,
                    status="success",
                    l1_dir=l1_dir,
                    l2_dir=l2_dir,
                ).inc()
                if (
                    isinstance(targets, list)
                    and len(targets) > 0
                    and isinstance(targets[0], dict)
                ):
                    path_last_generated_targets.labels(path=rest_path).set(
                        sum(len(t.get("targets", []) or []) for t in targets)
                    )

                return jsonify(targets)

    @app.route(f"{prefix}/")
    def admin():
        paths = []

        for dirpath, _, _ in os.walk(config.root_dir):
            should_ignore_underscore = any(
                p.startswith("_")
                for p in os.path.normpath(dirpath).split(os.sep)
            )
            if should_ignore_underscore:
                continue

            dirpath = dirpath.removeprefix(config.root_dir)
            dirpath = dirpath.removeprefix("/")
            paths.append(dirpath)

        paths = sorted(list(set(paths)))
        return render_template(
            "admin.html", prefix=prefix, paths=paths, version=VERSION
        )

    return app
