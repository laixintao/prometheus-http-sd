from concurrent.futures import ThreadPoolExecutor, as_completed
import importlib
import importlib.machinery
import importlib.util
import json
import logging
import os
from pathlib import Path
import time
from typing import Dict, List

from prometheus_client import Counter, Gauge, Histogram
import yaml

from prometheus_http_sd.decorator import DecoratorSelector
from prometheus_http_sd.exceptions import SDResultNotValidException

from .const import TEST_ENV_NAME
from .targets import TargetList

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

generator_executor = ThreadPoolExecutor(max_workers=400)


def should_ignore(full_path, ignore_dirs):
    if ignore_dirs:
        for ignore in ignore_dirs:
            if full_path.startswith(ignore):
                logger.warning(
                    f"{full_path} is ignored due to match ignore"
                    f" pattern {ignore}"
                )
                return True

    should_ignore_this = any(
        p.startswith("_") or (p.startswith(".") and p != "..")
        for p in os.path.normpath(full_path).split(os.sep)
    )

    if should_ignore_this:
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

            ignore = should_ignore(full_path, ignore_dirs)
            logger.info(f"{file=}, ignore={ignore}")
            if ignore:
                continue

            generators.append(full_path)

    logger.debug(f"{generators=}")
    return generators


def generate(root: str, path: str = "", **extra_args) -> TargetList:
    generators = get_generator_list(root, path)
    all_targets = []

    futures = []
    for generator in generators:
        future = generator_executor.submit(
            run_generator, generator, **extra_args
        )
        futures.append(future)

    for future in as_completed(futures):
        target_list = future.result()
        if isinstance(target_list, list):
            all_targets.extend(target_list)
        else:
            all_targets.append(target_list)

    return all_targets


def _timed_wrapper(*args, **kwargs):
    start = time.time()
    run_generator(*args, **kwargs)
    return time.time() - start


def generate_perf(root: str, path: str = "", **extra_args) -> Dict[str, float]:
    generators = get_generator_list(root, path)
    futures = {}
    result = {}

    for generator in generators:
        futures[generator] = generator_executor.submit(
            _timed_wrapper, generator, **extra_args
        )

    for generator, future in futures.items():
        time_cost = future.result()
        result[generator] = time_cost
    return {"generator_run_seconds": result}


def run_generator(generator_path: str, **extra_args) -> TargetList:
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
            result = executor(generator_path, **extra_args)
            if result is None:
                raise SDResultNotValidException("Generated result is None")
        except:  # noqa: E722
            generator_requests_total.labels(
                generator=generator_path, status="fail"
            ).inc()
            raise
        else:
            generator_requests_total.labels(
                generator=generator_path, status="success"
            ).inc()

        if (
            isinstance(result, list)
            and len(result) > 0
            and isinstance(result[0], dict)
        ):
            generator_last_generated_targets.labels(
                generator=generator_path
            ).set(sum(len(t.get("targets", []) or []) for t in result))

    return result


def run_json(file_path: str) -> TargetList:
    with open(file_path) as jsonf:
        return json.load(jsonf)


py_cache = DecoratorSelector()


@py_cache
def run_python(generator_path, **extra_args) -> TargetList:
    logger.debug(f"start to import module {generator_path}...")

    loader = importlib.machinery.SourceFileLoader("mymodule", generator_path)
    spec = importlib.util.spec_from_loader("mymodule", loader)
    if spec:
        mymodule = importlib.util.module_from_spec(spec)
        loader.exec_module(mymodule)
    else:
        raise Exception("Load a None module!")
    func = getattr(mymodule, "generate_targets")

    if os.getenv(TEST_ENV_NAME) == "1":
        try:
            test_func = getattr(mymodule, "test_generate_targets")
        except AttributeError:
            pass
        else:
            func = test_func
    return func(**extra_args)


def run_yaml(file_path: str):
    with open(file_path) as yamlf:
        data = yaml.load(yamlf, Loader=Loader)
        return data


if __name__ == "__main__":
    generate("")
    generate("spex")
