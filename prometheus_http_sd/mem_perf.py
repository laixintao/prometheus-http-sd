import time
import tracemalloc
import logging
import threading

logger = logging.getLogger("memorytracer")

INTERVAL_SECONDS = 10
TOPN = 10


class MemTracer:
    def __init__(self):
        self.last_snapshot = None

    def snapshot_once(self):
        snapshot = tracemalloc.take_snapshot()
        if self.last_snapshot:
            top_stats = snapshot.compare_to(self.last_snapshot, "lineno")
            logger.info("[ Top 10 differences ]")
            for stat in top_stats[:TOPN]:
                logger.info(stat)
        self.last_snapshot = snapshot

        top_stats = snapshot.statistics("lineno")

        logger.info("[ Top 10 ]")
        for stat in top_stats[:TOPN]:
            logger.info(stat)

    def run_forever(self):
        tracemalloc.start()
        logger.info(
            "Memory tracer started, will print out the memory usage every %d"
            " seconds...",
            INTERVAL_SECONDS,
        )
        while 1:
            self.snapshot_once()

            time.sleep(INTERVAL_SECONDS)


def start_tracing_thread():
    tracer = MemTracer()
    t = threading.Thread(target=tracer.run_forever, daemon=True)
    t.start()
