from prometheus_http_sd.validate import check_content
from prometheus_http_sd.validate import validate

from pathlib import Path


def test_run_test_generate_method():
    result = validate(
        Path(__file__).parent / "root_dir" / "py_should_run_test_func"
    )
    assert result["_total"] == 1


def test_no_port():
    assert not check_content(
        {
            "targets": [
                "192.168.19.2:9100",
                "192.168.19.3:9100",
                "192.168.19.4:9100",
                "192.168.19.5",
            ],
            "labels": {
                "__meta_datacenter": "singapore",
                "__meta_prometheus_job": "gateway",
            },
        }
    )


def test_no_targets():
    assert not check_content(
        {
            "labels": {
                "__meta_datacenter": "singapore",
                "__meta_prometheus_job": "gateway",
            },
        }
    )


def test_label_notdict():
    assert not check_content(
        {
            "targets": ["10.0.0.1:123"],
            "labels": ["__meta_datacenter", "__meta_prometheus_job"],
        }
    )


def test_label_no_bool():
    assert not check_content(
        {"targets": ["10.0.0.1:123"], "labels": {"abc": False}}
    )
