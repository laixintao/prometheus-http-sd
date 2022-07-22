from prometheus_http_sd.sd import get_generator_list


def test_underscore_should_be_ignored():
    generators = get_generator_list()
    assert "utils" not in generators
