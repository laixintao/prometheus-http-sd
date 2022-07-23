import logging
import sys

import click
import waitress

from flask import Flask, jsonify
from .sd import generate
from .config import config
from .version import VERSION
from prometheus_client import Gauge, Counter, Histogram, Info
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import make_wsgi_app

stdout_handler = logging.StreamHandler(stream=sys.stdout)
logging.basicConfig(
    level=logging.DEBUG,
    format=(
        "[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s"
    ),
    handlers=[stdout_handler],
)

logger = logging.getLogger("LOGGER_NAME")

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
    "httpsd_version_info",
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


@app.route("/targets", defaults={"path": ""})
@app.route("/targets/", defaults={"path": ""})
@app.route("/targets/<string:path>")
def get_targets(path):
    with target_path_request_duration_seconds.labels(path=path).time():
        try:
            targets = generate(config.root_dir, path)
        except:  # noqa: E722
            target_path_requests_total.labels(path=path, status="fail").inc()
            raise
        else:
            target_path_requests_total.labels(
                path=path, status="success"
            ).inc()
            path_last_generated_targets.labels(path=path).set(len(targets))

            return jsonify(targets)


@app.route("/")
def admin():
    return ""


@click.command()
@click.option(
    "--host", "-h", default="127.0.0.1", help="The interface to bind to."
)
@click.option("--port", "-p", default=8080, help="The port to bind to.")
@click.argument(
    "root_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
)
def main(host, port, root_dir):
    config.root_dir = root_dir
    waitress.serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
