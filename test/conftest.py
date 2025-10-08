import pytest
from prometheus_http_sd.app import create_app
from pathlib import Path


@pytest.fixture()
def app():
    cache_dir = str(Path(__file__).parent)
    app = create_app("/", cache_dir, 300, 1, 1024)
    app.config.update(
        {
            "TESTING": True,
        }
    )

    yield app


@pytest.fixture()
def client(app):
    return app.test_client()
