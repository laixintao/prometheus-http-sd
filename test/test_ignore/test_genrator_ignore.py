from prometheus_http_sd.sd import get_generator_list
from pathlib import Path


good_root = str(Path(__file__).parent / "good_root")


def test_underscore_should_be_ignored():
    generators = get_generator_list(good_root)
    for g in generators:
        assert "utils" not in g


def test_dot_should_be_ignored():
    generators = get_generator_list(good_root)
    for g in generators:
        assert "hidden" not in g

def test_dot_directory_should_be_ignored():
    generators = get_generator_list(good_root)
    for g in generators:
        assert "should_ignore" not in g
