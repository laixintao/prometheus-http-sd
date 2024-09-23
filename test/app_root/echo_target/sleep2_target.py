import time


def generate_targets(**kwargs):
    """Return arg list in label target."""
    time.sleep(2)
    return [
        {
            "labels": {"sleep": "2"},
            "targets": ["127.0.0.1:8080"],
        }
    ]


if __name__ == "__main__":
    generate_targets()