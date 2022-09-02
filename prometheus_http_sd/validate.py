import sys
import time
import logging
from .sd import get_generator_list, run_generator

logger = logging.getLogger("checker")


def validate(root_dir):
    generators = get_generator_list(root_dir)

    total_targets = 0
    exit_0 = True

    by_generator = {}
    for generator in generators:
        start = time.time()
        target_list = run_generator(generator)
        all_good = True
        for t in target_list:
            all_good = check_content(t)
            if not all_good:
                exit_0 = False
        end = time.time()
        count = 0
        count = sum(len(t["targets"]) for t in target_list)
        status = "PASS"
        if not all_good:
            status = "FAIL"
        logger.info(
            f"{status} run generator {generator}, took {end-start}s, generated"
            f" {count} targets."
        )
        by_generator[str(generator)] = count
        total_targets += count

    logger.info(f"Done! Generated {total_targets} targets in total.")

    by_generator["_total"] = total_targets
    if exit_0:
        return by_generator
    sys.exit(1)


def check_content(target):
    if "targets" not in target:
        logger.warning(f"`targets` key is not in {target}")
        return False

    host_ports = target["targets"]
    if not isinstance(host_ports, list):
        logger.warning(f"`targets` key in {target} is not a array.")
        return False
    for k in host_ports:
        if ":" not in k:
            logger.warning(f"is target {k} missing port?")
            return False

    labels = target.get("labels")
    if labels:
        if not isinstance(labels, dict):
            logger.warning(f"`labels` key in {target} is not a dict.")
            return False
        for k, v in labels.items():
            if  not isinstance(k, str) or not isinstance(v, str):
                logger.warning(f"label pair {k}:{v} is not string.")
                return False
    return True
