import logging
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class Task:
    def __init__(self, url) -> None:
        self.url = url
        self.need_update = True
        self.running = False


def update(task):
    pass


class Dispatcher:
    def __init__(self, interval: int, max_workers: int) -> None:
        self.interval = interval
        self.tasks = {}
        self.threadpool = ThreadPoolExecutor(max_workers=max_workers)

    def run_forever(self):
        while True:
            for url, task in self.tasks.items():
                if task.need_update:
                    if not task.running:
                        self.threadpool.submit(update, task)
                    task.need_update = False
            logger.info(
                "All tasks checked, now I sleep %d seconds", self.interval
            )
            time.sleep(self.interval)

    def append_task(self, url):
        self.tasks.setdefault(url, Task(url)).need_update = True
