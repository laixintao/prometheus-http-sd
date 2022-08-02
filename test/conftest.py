import pytest
from prometheus_http_sd.app import app as global_app


@pytest.fixture()
def app():
    global_app.config.update(
        {
            "TESTING": True,
        }
    )

    yield global_app


@pytest.fixture()
def client(app):
    return app.test_client()
