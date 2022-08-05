from prometheus_http_sd.validate import check_content


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
