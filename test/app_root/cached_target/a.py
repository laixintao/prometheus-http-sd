def generate_targets(**kwargs):
    import time

    time.sleep(5)
    return [
        {
            "labels": {"foo": "bar"},
            "targets": ["127.0.0.1:8080"],
        }
    ]
