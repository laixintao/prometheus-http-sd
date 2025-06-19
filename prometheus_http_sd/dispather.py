from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
from pathlib import Path
import threading
import time

from .config import config
from .sd import generate

logger = logging.getLogger(__name__)


class CacheNotExist(Exception):
    """Cache not exist"""


class CacheExpired(Exception):
    def __init__(self, updated_timestamp, cache_excepire_seconds) -> None:
        super().__init__("Cache file expired")
        self.updated_timestamp = updated_timestamp
        self.cache_excepire_seconds = cache_excepire_seconds


class Task:
    def __init__(self, url, path, extra_args) -> None:
        self.url = url
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
            for url, task in self.tasks.items():
                if task.need_update:
                    if not task.running:
                        task.running = True
                        logger.info("Put into queue: url=%s", task.url)
                        self.threadpool.submit(self.update, task)
                    task.need_update = False
            logger.info(
                "All tasks checked, now I sleep %d seconds", self.interval
            )
            time.sleep(self.interval)

    def start_dispatcher(self):
        thread = threading.Thread(target=self.run_forever, daemon=True)
        thread.start()
        logger.info("dispather started")

    def update(self, task):
        start_time = time.time()
        logger.info("Task for url=%s started", task.url)
        try:
            targets = generate(config.root_dir, task.path, **task.extra_args)

            data = {"updated_timestamp": time.time(), "results": targets}

            flocation = self.get_cache_location(task.url)
            with open(flocation, "w+") as f:
                json.dump(data, f)
        except:  # noqa
            logger.exception("Error when run for task url=%s", task.url)
        finally:
            logger.info(
                "Task for url=%s end, tooke %s",
                task.url,
                time.time() - start_time,
            )
            task.running = False

    def append_task(self, url, path, extra_args):
        task = self.tasks.setdefault(url, Task(url, path, extra_args))
        task.need_update = True

    def _hash_key(self, url) -> str:
        md5_hash = hashlib.md5(url.encode()).hexdigest()
        return md5_hash

    def get_cache_location(self, url) -> Path:
        return self.cache_location / self._hash_key(url)

    def get_targets(self, path: str, url: str, **extra_args):
        self.append_task(url, path, extra_args)

        cache_file = self.get_cache_location(url)

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
