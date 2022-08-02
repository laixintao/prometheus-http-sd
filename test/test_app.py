from pathlib import Path


def test_target_non_exist_should_404(client):
    from prometheus_http_sd.config import config

    config.root_dir = str(Path(__file__).parent / "app_root")
    resp = client.get("/targets/no-exist")
    assert resp.status_code == 404
