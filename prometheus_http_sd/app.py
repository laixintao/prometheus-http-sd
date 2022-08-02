import logging
import sys

import click
import waitress

from flask import Flask, jsonify, abort
from .sd import generate
from .config import config
from .version import VERSION
from prometheus_client import Gauge, Counter, Histogram, Info
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import make_wsgi_app


def config_log(level):
    stdout_handler = logging.StreamHandler(stream=sys.stdout)
    logging.basicConfig(
        level=level,
        format=(
            "[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s -"
            " %(message)s"
        ),
        handlers=[stdout_handler],
    )


logger = logging.getLogger(__name__)

app = Flask(__name__)

# Add prometheus wsgi middleware to route /metrics requests
app.wsgi_app = DispatcherMiddleware(
    app.wsgi_app, {"/metrics": make_wsgi_app()}
)


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


@app.route("/targets", defaults={"rest_path": ""})
@app.route("/targets/", defaults={"rest_path": ""})
# match the rest of the path
@app.route("/targets/<path:rest_path>")
def get_targets(rest_path):
    logger.info("request target path: {}".format(rest_path))
    with target_path_request_duration_seconds.labels(path=rest_path).time():
        try:
            targets = generate(config.root_dir, rest_path)
        except FileNotFoundError:
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


@app.route("/")
def admin():
    return ""


@click.command()
@click.option(
    "--host", "-h", default="127.0.0.1", help="The interface to bind to."
)
@click.option("--port", "-p", default=8080, help="The port to bind to.")
@click.option(
    "--log-level",
    default=20,
    help=(
        "Python logging level, default 20,"
        " https://docs.python.org/3/library/logging.html"
    ),
)
@click.argument(
    "root_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
def main(host, port, log_level, root_dir):
    config_log(log_level)
    config.root_dir = root_dir
    waitress.serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
