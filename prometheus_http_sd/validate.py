import time
import logging
from .sd import get_generator_list, run_generator

logger = logging.getLogger("checker")


def validate(root_dir):
    generators = get_generator_list(root_dir)

    total_targets = 0
    for generator in generators:
        start = time.time()
        target_list = run_generator(generator)
        end = time.time()
        logger.info(
            f"Run generator {generator}, took {end-start}s, generated"
            f" {len(target_list)} targets."
        )
        total_targets += len(target_list)

    logger.info("Done! Generated {total_targets} in total.")
