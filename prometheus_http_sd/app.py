import logging
import sys

import click
import waitress

from flask import Flask, jsonify
from .sd import generate
from . import consts, version
import os
from prometheus_client import Gauge

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


DEBUG = os.environ.get(consts.DEBUG_ENV_NAME) == "True"

path_last_generated_targets_gauge = Gauge(
    "httpsd_path_last_generated_targets_gauge",
    "Genarated targets count in last request",
    ["path"],
)
version_info = Gauge(
    "httpsd_version_info", "prometheus_http_sd version info", ["version"]
)
version_info.labels(version=version.VERSION).set(1)
target_path_requests_total
    http_code
target_path_request_duration_seconds


@app.route("/targets", defaults={"path": ""})
@app.route("/targets/<string:path>")
def get_targets(path):
    targets = generate(path)
    return jsonify(targets)


@app.route("/")
def admin():
    return ""


@click.command()
@click.option(
    "--host", "-h", default="127.0.0.1", help="The interface to bind to."
)
@click.option("--port", "-p", default=8080, help="The port to bind to.")
def main(host, port):
    waitress.serve(app, host=host, port=port)


if __name__ == "__main__":
    main()
