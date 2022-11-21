import os
import json
import logging
import importlib
import importlib.machinery

import importlib.util
from pathlib import Path

from typing import List
from .targets import TargetList
from prometheus_client import Gauge, Counter, Histogram

import yaml

try:
    from yaml import CLoader as Loader
except ImportError:
    from yaml import Loader

logger = logging.getLogger(__name__)

generator_requests_total = Counter(
    "httpsd_generator_requests_total",
    "The total count that this generator executed, status can be success/fail",
    ["generator", "status"],
)

generator_last_generated_targets = Gauge(
    "httpsd_generator_last_generated_targets",
    "The target count that this generator gets during its last execution",
    ["generator"],
)

generator_run_duration_seconds = Histogram(
    "httpsd_generator_run_duration_seconds",
    "The time cost that this generator run",
    ["generator"],
)


def should_ignore(file, full_path, ignore_dirs):
    logger.info(f"{file=}")
    if ignore_dirs:
        for ignore in ignore_dirs:
            if full_path.startswith(ignore):
                logger.warning(
                    f"{full_path} is ignored due to match ignore"
                    f" pattern {ignore}"
                )
                return True

    should_ignore_underscore = any(
        p.startswith("_") for p in os.path.normpath(full_path).split(os.sep)
    )
    if should_ignore_underscore:
        return True

    should_ignore_hidden = file.startswith(".")
    if should_ignore_hidden:
        return True
    return False


def get_generator_list(
    root: str, path: str = "", ignore_dirs=None
) -> List[str]:
    """
    generate targets start from ``path``
    if ``path`` is None or empty, then start from the root path
    ``TARGETS_DIR_ENV_NAME ``
    """
    logger.debug(f"{root=}, {path=}")
    if path:
        root = os.path.join(root, path)

    generators = []

    if not Path(root).exists():
        raise FileNotFoundError(f"{root} not exist!")

    for root, _, files in os.walk(root):
        for file in files:
            full_path = os.path.join(root, file)

            if should_ignore(file, full_path, ignore_dirs):
                continue

            generators.append(full_path)

    logger.debug(f"{generators=}")
    return generators


def generate(root: str, path: str = "") -> TargetList:
    generators = get_generator_list(root, path)
    all_targets = []
    for generator in generators:
        target_list = run_generator(generator)
        all_targets.extend(target_list)

    return all_targets


def run_generator(generator_path: str) -> TargetList:
    if generator_path.endswith(".json"):
        executor = run_json
    elif generator_path.endswith(".py"):
        executor = run_python
    elif generator_path.endswith(".yaml"):
        executor = run_yaml
    else:
        generator_requests_total.labels(
            generator=generator_path, status="fail"
        ).inc()
        raise Exception(f"Unknown File Type: {generator_path}")

    with generator_run_duration_seconds.labels(
        generator=generator_path
    ).time():
        try:
            result = executor(generator_path)
        except:  # noqa: E722
            generator_requests_total.labels(
                generator=generator_path, status="fail"
            ).inc()
            raise
        else:
            generator_requests_total.labels(
                generator=generator_path, status="success"
            ).inc()

        generator_last_generated_targets.labels(generator=generator_path).set(
            sum(len(t.get("targets", [])) for t in result)
        )

    return result


def run_json(file_path: str) -> TargetList:
    with open(file_path) as jsonf:
        return json.load(jsonf)


def run_python(generator_path) -> TargetList:
    logger.debug(f"start to import module {generator_path}...")

    loader = importlib.machinery.SourceFileLoader("mymodule", generator_path)
    spec = importlib.util.spec_from_loader("mymodule", loader)
    if spec:
        mymodule = importlib.util.module_from_spec(spec)
        loader.exec_module(mymodule)
    else:
        raise Exception("Load a None module!")

    return mymodule.generate_targets()


def run_yaml(file_path: str):
    with open(file_path) as yamlf:
        data = yaml.load(yamlf, Loader=Loader)
        return data


if __name__ == "__main__":
    generate("")
    generate("spex")
