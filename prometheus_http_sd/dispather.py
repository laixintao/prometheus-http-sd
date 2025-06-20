from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
from pathlib import Path
import threading
import time
from prometheus_client import Counter, Gauge, Summary


from .config import config
from .sd import generate

logger = logging.getLogger(__name__)

GENERATOR_LATENCY = Summary(
    "sd_generator_duration_seconds",
    "Run generator for full_path time",
    ["full_path", "status"],
)

QUEUE_JOB_GAUGE = Gauge("httpsd_update_queue_jobs", "Current jobs pending in the queue", ['status'])
FINISHED_JOBS = Counter("httpsd_finished_jobs", "Already finished jobs")


class CacheNotExist(Exception):
    """Cache not exist"""


class CacheExpired(Exception):
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
        self.threadpool = ThreadPoolExecutor(max_workers=max_workers)
        self.cache_location = cache_location
        self.cache_expire_seconds = cache_expire_seconds

    def run_forever(self):
        while True:
            logger.info("Weak up! I start to check all pending tasks...")
            counter = 0
            for full_path, task in self.tasks.items():
                if task.need_update:
                    if not task.running:
                        task.running = True
                        logger.info("Put into queue: full_path=%s", task.full_path)
                        self.threadpool.submit(self.update, task)
                        counter += 1
                        QUEUE_JOB_GAUGE.labels("pending").inc()
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
        logger.info("dispather started")

    def update(self, task):
        start_time = time.time()
        logger.info("Task for full_path=%s started", task.full_path)
        QUEUE_JOB_GAUGE.labels("pending").dec()
        QUEUE_JOB_GAUGE.labels("running").inc()
        try:
            targets = generate(config.root_dir, task.path, **task.extra_args)

            data = {"updated_timestamp": time.time(), "results": targets}

            flocation = self.get_cache_location(task.full_path)
            with open(flocation, "w+") as f:
                json.dump(data, f)
            duration = time.time() - start_time
            GENERATOR_LATENCY.labels(task.full_path, "success").observe(duration)
        except:  # noqa
            duration = time.time() - start_time
            GENERATOR_LATENCY.labels(task.full_path, "fail").observe(duration)
            logger.exception("Error when run for task full_path=%s", task.full_path)
        finally:
            duration = time.time() - start_time
            logger.info(
                "Task for full_path=%s end, tooke %s",
                task.full_path,
                time.time() - start_time,
            )
            task.running = False
            QUEUE_JOB_GAUGE.labels("running").dec()
            FINISHED_JOBS.inc()

    def append_task(self, full_path, path, extra_args):
        task = self.tasks.setdefault(full_path, Task(full_path, path, extra_args))
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
            data = json.load(f)
            updated_timestamp = data["updated_timestamp"]
            current = time.time()
            if current - updated_timestamp > self.cache_expire_seconds:
                raise CacheExpired(
                    updated_timestamp=updated_timestamp,
                    cache_excepire_seconds=self.cache_expire_seconds,
                )
            return data["results"]
