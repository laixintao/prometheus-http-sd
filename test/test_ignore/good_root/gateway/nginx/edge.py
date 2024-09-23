def generate_targets(**kwargs):
    return [
        {
            "targets": ["10.71.99.1:3333", "10.71.99.2:3333"],
            "labels": {
                "__meta_datacenter": "singapore",
                "__meta_prometheus_job": "nginx",
            },
        }
    ]
