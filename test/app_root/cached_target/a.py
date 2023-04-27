from prometheus_http_sd.decroator import TimeDecorator


@TimeDecorator(
    cache_time=100,
)
def generate_targets():
    import time

    time.sleep(5)
    return [
        {
            "labels": {"foo": "bar"},
            "targets": ["127.0.0.1:8080"],
        }
    ]
