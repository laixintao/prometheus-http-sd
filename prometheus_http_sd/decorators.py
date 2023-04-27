import time
import heapq
import threading

from prometheus_client import Gauge, Counter, Histogram

_collected_total = Counter(
    "httpsd_garbage_collection_collected_items_total",
    "The total count of the garbage collection collected items.",
    ["name"],
)

_thread_cache_count = Gauge(
    "httpsd_garbage_collection_cache_count",
    "Show current thread_cache count",
    ["name"],
)

_heap_cache_count = Gauge(
    "httpsd_garbage_collection_heap_count",
    "Show current heap length",
    ["name"],
)

_collection_run_interval = Histogram(
    "http_sd_garbage_collection_run_interval_seconds_bucket",
    "The interval of two garbage collection run.",
    ["name"],
)


class TimeoutException(Exception):
    pass


class TimeoutDecorator:
    def __init__(
        self,
        timeout=None,
        cache_time=60 * 5,
        garbage_collection_interval=5,
        garbage_collection_count=30,
    ):
        """
        Use threading and cache to store the function result.

        Garbage Collection time complexity:
            worse: O(nlogn)
            average in every operation: O(logn)

        Parameters
        ----------
        timeout: int
            function timeout. if exceed, raise TimeoutException (in sec).
        cache_time: int
            after function return normally,
                how long should we cache the result (in sec).
        name: str
            prometheus_client metrics label
        garbage_collection_count: int
            garbage collection threshold
        garbage_collection_interval: int
            the second to avoid collection too often.

        Returns
        -------
        TimeoutDecorator
            decorator class.
        """
        self.timeout = timeout
        self.cache_time = cache_time
        self.garbage_collection_interval = garbage_collection_interval
        self.garbage_collection_count = garbage_collection_count

        self.thread_cache = {}
        self.cache_lock = threading.Lock()
        self.heap = []
        self.heap_lock = threading.Lock()
        self.garbage_collection_timestamp = 0
        self.garbage_collection_lock = threading.Lock()

    def can_garbage_collection(self):
        """Check current state can run garbage collection."""
        return (
            self.garbage_collection_interval
            + self.garbage_collection_timestamp
            < time.time()
            and len(self.heap) > self.garbage_collection_count
        )

    def _cache_garbage_collection(self, name_label):
        def can_iterate():
            with self.heap_lock:
                if len(self.heap) == 0 or self.heap[0][0] > time.time():
                    return False
            return True

        worked_keys = {}
        while can_iterate():
            _timestamp, _key = None, None
            with self.heap_lock:
                _timestamp, _key = heapq.heappop(self.heap)
            if _key in worked_keys:
                continue
            worked_keys[_key] = True
            with self.cache_lock:
                if _key not in self.thread_cache:
                    continue
                if self.is_expired(self.thread_cache[_key]):
                    del self.thread_cache[_key]
                    _collected_total.labels(name=name_label).inc(1)
        _heap_cache_count.labels(
            name=name_label,
        ).set(len(self.heap))
        _thread_cache_count.labels(
            name=name_label,
        ).set(len(self.thread_cache))
        current_time = time.time()
        if self.garbage_collection_timestamp != 0:
            _collection_run_interval.labels(
                name=name_label,
            ).observe(current_time - self.garbage_collection_timestamp)
        self.garbage_collection_timestamp = current_time

    def is_expired(self, cache):
        """Check thread_cache dict is expired."""
        return cache["expired_timestamp"] < time.time()

    def _cal_cache_key(*arg, **kwargs):
        return hash(tuple([hash(arg), tuple(sorted(kwargs.items()))]))

    def __call__(self, function):
        name_label = f"{function.__module__}/{function.__funcname__}"

        def wrapper(*arg, **kwargs):
            cache = {
                "thread": None,
                "error": None,
                "response": None,
                "expired_timestamp": float("inf"),
            }

            def target_function(key):
                try:
                    cache["response"] = function(*arg, **kwargs)
                    cache["expired_timestamp"] = time.time() + self.cache_time
                    with self.heap_lock:
                        heapq.heappush(
                            self.heap,
                            (
                                cache["expired_timestamp"],
                                key,
                            ),
                        )
                        _heap_cache_count.labels(
                            name=name_label,
                        ).set(len(self.heap))
                except Exception as e:
                    cache["error"] = e

            key = self._cal_cache_key(*arg, **kwargs)
            with self.cache_lock:
                if key in self.thread_cache:
                    if self.thread_cache[key][
                        "thread"
                    ].is_alive() or not self.is_expired(
                        self.thread_cache[key]
                    ):
                        cache = self.thread_cache[key]
                if cache["thread"] is None:
                    cache["thread"] = threading.Thread(
                        target=target_function,
                        args=(key,),
                    )
                    cache["thread"].start()
                self.thread_cache[key] = cache
                _thread_cache_count.labels(
                    name=name_label,
                ).set(len(self.thread_cache))
            cache["thread"].join(self.timeout)

            if (
                self.can_garbage_collection()
                and self.garbage_collection_lock.acquire(False)
            ):
                try:
                    self._cache_garbage_collection(name_label)
                finally:
                    self.garbage_collection_lock.release()
            if cache["thread"].is_alive():
                raise TimeoutException("target function timeout!")
            if cache["error"]:
                raise cache["error"]
            return cache["response"]

        return wrapper
