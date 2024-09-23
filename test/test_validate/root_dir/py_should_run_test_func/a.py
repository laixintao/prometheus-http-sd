def generate_targets(**args):
    return [
        {
            "labels": {"arg_foo": args["foo"]},
            "targets": ["127.0.0.1:8080"],
        }
    ]


def test_generate_targets(*args, **kwargs):
    return generate_targets(foo="bar")
