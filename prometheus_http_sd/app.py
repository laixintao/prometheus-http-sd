import logging
import sys

from flask import Flask
from .sd import generate

stdout_handler = logging.StreamHandler(stream=sys.stdout)

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s",
    handlers=[stdout_handler],
)

logger = logging.getLogger("LOGGER_NAME")

app = Flask(__name__)


@app.route("/targets")
def get_targets():
    targets = generate()
    return None


@app.route("/")
def admin():
    return None
