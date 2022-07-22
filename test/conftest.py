import os
from pytest import fixture


@fixture(autouse=True)
def set_test_dir_env():
    os.environ["TARGETS_DIR_ENV_NAME"] = "./test_dir"
