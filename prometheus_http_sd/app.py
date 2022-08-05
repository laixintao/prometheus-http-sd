import logging
import sys

import click
import waitress

from flask import Flask, jsonify, abort
from .sd import generate
from .config import config
from .version import VERSION
from .validate import validate
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


@click.group()
@click.option(
    "--log-level",
    default=20,
    help=(
        "Python logging level, default 20, can set from 0 to 50, step 10:"
        " https://docs.python.org/3/library/logging.html"
    ),
)
def main(log_level):
    config_log(log_level)


@main.command(help="Start a HTTP_SD server for Prometheus.")
@click.option(
    "--host", "-h", default="127.0.0.1", help="The interface to bind to."
)
@click.option("--port", "-p", default=8080, help="The port to bind to.")
@click.argument(
    "root_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
def serve(host, port, root_dir):
    config.root_dir = root_dir
    waitress.serve(app, host=host, port=port)


@main.command(help="Run and verify the generators under target directory.")
@click.argument(
    "root_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
def check(root_dir):
    config.root_dir = root_dir
    validate(root_dir)


if __name__ == "__main__":
    main()
