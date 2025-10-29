import logging
import os
from pathlib import Path
from datetime import datetime

from flask import Flask, jsonify, render_template, request
from prometheus_client import make_wsgi_app
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from prometheus_http_sd.dispather import (
    CacheNotExist,
    Dispatcher,
    CacheExpired,
)

from .config import config
from .sd import generate_perf, run_python
from .metrics import (
    path_last_generated_targets,
    target_path_requests_total,
    target_path_request_duration_seconds,
)
from .version import VERSION

logger = logging.getLogger(__name__)


def create_app(
    prefix,
    cache_location,
    cache_seconds,
    cache_refresh_interval,
    update_threads,
):
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

    cache_dir = Path(cache_location)
    dispatcher = Dispatcher(
        interval=cache_refresh_interval,
        max_workers=update_threads,
        cache_location=cache_dir,
        cache_expire_seconds=cache_seconds,
    )
    dispatcher.start_dispatcher()

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
                full_path = request.full_path
                targets = dispatcher.get_targets(
                    rest_path, full_path, **request.args
                )
            except CacheNotExist:
                target_path_requests_total.labels(
                    path=rest_path,
                    status="cache-not-exist",
                    l1_dir=l1_dir,
                    l2_dir=l2_dir,
                ).inc()
                logger.error("Cache miss, full_path=%s", request.full_path)
                return jsonify({"error": "cache miss"}), 500
            except CacheExpired as e:
                target_path_requests_total.labels(
                    path=rest_path,
                    status="cache-expired",
                    l1_dir=l1_dir,
                    l2_dir=l2_dir,
                ).inc()
                updated_timestamp = e.updated_timestamp
                cache_expire_seconds = e.cache_excepire_seconds
                dt = datetime.fromtimestamp(updated_timestamp)

                logger.error(
                    "Cache expired, full_path=%s, updated_timestamp: %s, "
                    "cache_expire_seconds: %s (%s)",
                    request.full_path,
                    updated_timestamp,
                    cache_expire_seconds,
                    dt,
                )
                return (
                    jsonify(
                        {
                            "error": (
                                "cache expired, you should try again later"
                            ),
                            "updated_timestamp": updated_timestamp,
                            "updated_time": dt,
                            "cache_expire_seconds": cache_expire_seconds,
                        },
                    ),
                    500,
                )
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
