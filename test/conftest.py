import pytest
from prometheus_http_sd.app import create_app


@pytest.fixture()
def app():
    app = create_app("/")
    app.config.update(
        {
            "TESTING": True,
        }
    )

    yield app


@pytest.fixture()
def client(app):
    return app.test_client()
