import os
import logging
from pathlib import Path


from flask import Flask, jsonify, abort, render_template
from .sd import generate
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
    ["path", "status"],
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

    @app.route(f"{prefix}/targets", defaults={"rest_path": ""})
    @app.route(f"{prefix}/targets/", defaults={"rest_path": ""})
    # match the rest of the path
    @app.route(f"{prefix}/targets/<path:rest_path>")
    def get_targets(rest_path):
        logger.info("request target path: {}".format(rest_path))
        with target_path_request_duration_seconds.labels(
            path=rest_path
        ).time():
            try:
                targets = generate(config.root_dir, rest_path)
            except FileNotFoundError:
                logger.error(f"Didn't found {config.root_dir}/{rest_path}!")
                abort(404)
            except:  # noqa: E722
                target_path_requests_total.labels(
                    path=rest_path, status="fail"
                ).inc()
                raise
            else:
                target_path_requests_total.labels(
                    path=rest_path, status="success"
                ).inc()
                path_last_generated_targets.labels(path=rest_path).set(
                    sum(len(t.get("targets", [])) for t in targets)
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

            paths.append(dirpath.removeprefix(config.root_dir))

        paths = sorted(list(set(paths)))
        return render_template("admin.html", prefix=prefix, paths=paths)

    return app
