import pytest
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


def test_parse_yaml():
    targets = generate(root, "yaml")
    assert targets == [
        {
            "targets": ["10.1.1.9:9100", "10.1.1.10:9100"],
            "labels": {"job": "node", "datacenter": "nyc", "group": "g1"},
        },
        {
            "targets": ["10.2.1.9:9100", "10.2.1.10:9100"],
            "labels": {"job": "node", "datacenter": "sg", "group": "g2"},
        },
    ]


def test_non_exist():
    with pytest.raises(FileNotFoundError):
        targets = generate(root, "non-exist")
