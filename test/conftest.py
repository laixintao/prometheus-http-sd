import os
from pytest import fixture
from prometheus_http_sd import consts


@fixture(autouse=True)
def set_test_dir_env():
    os.environ[consts.TARGETS_DIR_ENV_NAME] = "./test_dir"
