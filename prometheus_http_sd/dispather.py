from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import logging
from pathlib import Path
import threading
import time

from .config import config
from .sd import generate
from .metrics import (
    generator_latency,
    queue_job_gauge,
    finished_jobs,
    dispatcher_started_counter,
)

logger = logging.getLogger(__name__)


class CacheError(Exception):
    """Cache is not valid"""


class CacheNotValidJson(CacheError):
    """Cache file is not a valid json"""


class CacheNotExist(CacheError):
    """Cache not exist"""


class CacheExpired(CacheError):
    def __init__(self, updated_timestamp, cache_excepire_seconds) -> None:
        super().__init__("Cache file expired")
        self.updated_timestamp = updated_timestamp
        self.cache_excepire_seconds = cache_excepire_seconds


class Task:
    def __init__(self, full_path, path, extra_args) -> None:
        self.full_path = full_path
        self.path = path
        self.extra_args = extra_args
        self.need_update = True
        self.running = False


class Dispatcher:
    def __init__(
        self,
        interval: int,
        max_workers: int,
        cache_location: Path,
        cache_expire_seconds: int,
    ) -> None:
        self.interval = interval
        self.tasks = {}
        self.tasks_lock = threading.Lock()

        logger.info("Create threadpool with workers=%d", max_workers)
        self.threadpool = ThreadPoolExecutor(max_workers=max_workers)
        self.cache_location = cache_location
        self.cache_expire_seconds = cache_expire_seconds

        self.dispather_thread = None

    def run_forever(self):
        while True:
            logger.info("Weak up! I start to check all pending tasks...")

            if (
                not self.dispather_thread
                or not self.dispather_thread.is_alive()
            ):
                logger.warning("dispatcher thread died! restart it now")
                self.start_dispatcher()

            counter = 0

            copy_start = time.time()
            with self.tasks_lock:
                task_pool = copy.copy(self.tasks)
            copy_end = time.time()
            logger.info(
                "copy tasks done, took %s seconds", copy_end - copy_start
            )

            for task in task_pool.values():
                if task.need_update:
                    if not task.running:
                        task.running = True
                        logger.info(
                            "Put into queue: full_path=%s", task.full_path
                        )
                        self.threadpool.submit(self.update, task)
                        counter += 1
                        queue_job_gauge.labels("pending").inc()
                    task.need_update = False
            logger.info(
                "All tasks checked, %d tasks added, now I sleep %d seconds",
                counter,
                self.interval,
            )
            time.sleep(self.interval)

    def start_dispatcher(self):
        thread = threading.Thread(target=self.run_forever, daemon=True)
        thread.start()
        self.dispather_thread = thread
        logger.info("dispather started")
        dispatcher_started_counter.inc()

    def update(self, task):
        start_time = time.time()
        logger.info("Task for full_path=%s started", task.full_path)
        queue_job_gauge.labels("pending").dec()
        queue_job_gauge.labels("running").inc()
        try:
            targets = generate(config.root_dir, task.path, **task.extra_args)

            data = {"updated_timestamp": time.time(), "results": targets}

            flocation = self.get_cache_location(task.full_path)
            with open(flocation, "w+") as f:
                json.dump(data, f)
            duration = time.time() - start_time
            generator_latency.labels(task.full_path, "success").observe(
                duration
            )
        except:  # noqa
            duration = time.time() - start_time
            generator_latency.labels(task.full_path, "fail").observe(duration)
            logger.exception(
                "Error when run for task full_path=%s", task.full_path
            )
        finally:
            duration = time.time() - start_time
            logger.info(
                "Task for full_path=%s end, tooke %s",
                task.full_path,
                time.time() - start_time,
            )
            task.running = False
            queue_job_gauge.labels("running").dec()
            finished_jobs.inc()

    def append_task(self, full_path, path, extra_args):
        task = self.tasks.get(full_path)
        if not task:
            with self.tasks_lock:
                task = self.tasks.setdefault(
                    full_path, Task(full_path, path, extra_args)
                )
        task.need_update = True

    def _hash_key(self, full_path) -> str:
        md5_hash = hashlib.md5(full_path.encode()).hexdigest()
        return md5_hash

    def get_cache_location(self, full_path) -> Path:
        return self.cache_location / self._hash_key(full_path)

    def get_targets(self, path: str, full_path: str, **extra_args):
        self.append_task(full_path, path, extra_args)

        cache_file = self.get_cache_location(full_path)

        if not cache_file.exists():
            raise CacheNotExist()

        with open(cache_file) as f:
            try:
                data = json.load(f)
            except json.decoder.JSONDecodeError:
                logger.warning(
                    "Cache file %s is not a valid json, delete it...",
                    cache_file,
                )
                Path(cache_file).unlink()
                raise CacheNotValidJson()

        updated_timestamp = data["updated_timestamp"]
        current = time.time()
        if current - updated_timestamp > self.cache_expire_seconds:
            raise CacheExpired(
                updated_timestamp=updated_timestamp,
                cache_excepire_seconds=self.cache_expire_seconds,
            )
        return data["results"]
