from prometheus_http_sd.sd import generate
from pathlib import Path


root = str(Path(__file__).parent / "root")


def test_parse_json():
    targets = generate(root, "json")
    assert targets == [
        {
            "targets": [
                "192.168.19.2:9100",
                "192.168.19.3:9100",
                "192.168.19.4:9100",
                "192.168.19.5:9100",
            ],
            "labels": {
                "__meta_datacenter": "singapore",
                "__meta_prometheus_job": "gateway",
            },
        }
    ]
