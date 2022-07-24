import os
import json
import logging
import importlib
import importlib.machinery

import importlib.util

from typing import List
from .targets import TargetList
from prometheus_client import Gauge, Counter, Histogram

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


def get_generator_list(root: str, path: str = "") -> List[str]:
    """
    generate targets start from ``path``
    if ``path`` is None or empty, then start from the root path
    ``TARGETS_DIR_ENV_NAME ``
    """
    if path:
        root = os.path.join(root, path)

    generators = []

    for root, _, files in os.walk(root):
        for file in files:
            full_path = os.path.join(root, file)

            should_ignore = any(
                p.startswith("_")
                for p in os.path.normpath(full_path).split(os.sep)
            )
            if should_ignore:
                continue

            generators.append(full_path)

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
        executor = run_file
    elif generator_path.endswith(".py"):
        executor = run_python
    else:
        generator_requests_total.labels(
            generator=generator_path, status="fail"
        ).inc()
        raise Exception(f"Unknown File Type: {generator_path}")

    with generator_run_duration_seconds.labels(
        generator=generator_path
    ).time():
        result = executor(generator_path)
        generator_last_generated_targets.labels(generator=generator_path).set(
            len(result)
        )

    generator_requests_total.labels(
        generator=generator_path, status="success"
    ).inc()
    return result


def run_file(file_path: str) -> TargetList:
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


if __name__ == "__main__":
    generate("")
    generate("spex")
