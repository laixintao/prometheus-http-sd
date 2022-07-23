from prometheus_http_sd.sd import get_generator_list


def test_underscore_should_be_ignored(good_root):
    generators = get_generator_list(good_root)
    assert "utils" not in generators
