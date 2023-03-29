def generate_targets(**args):
    """Return arg list in label target."""
    return [{
        "labels": args,
        "targets": ["127.0.0.1:8080"],
    }]


if __name__ == "__main__":
    generate_targets()
