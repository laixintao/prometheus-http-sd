import time
import heapq
import logging
import threading

logger = logging.getLogger(__name__)


class TimeoutException(Exception):
    pass


class TimeoutDecorator:
    def __init__(
        self,
        timeout=None,
        cache_time=0,
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
        garbage_collection_interval: count
            the count should execute the garbage_collection.
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

    def _cache_garbage_collection(self):
        def can_iterate():
            with self.heap_lock:
                if len(self.heap) == 0 or self.heap[0][0] > time.time():
                    return False
            return True

        logger.info(
            f"""Start garbage collection metrics:
        Last garbage collection time: {self.garbage_collection_timestamp},
        Start collection time: {time.time()}
        len(heap): {len(self.heap)}
        len(thread_cache): {self.thread_cache}"""
        )
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
        self.garbage_collection_timestamp = time.time()
        logger.info(
            f"""Finish garbage collection finish metrics:
        Finish garbage collection time: {self.garbage_collection_timestamp},
        len(heap): {len(self.heap)}
        len(thread_cache): {self.thread_cache}"""
        )

    def is_expired(self, cache):
        """Check thread_cache dict is expired."""
        return cache["expired_timestamp"] < time.time()

    def _cal_cache_key(*arg, **kwargs):
        return hash(tuple([hash(arg), tuple(sorted(kwargs.items()))]))

    def __call__(self, function):
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
            cache["thread"].join(self.timeout)

            if (
                self.can_garbage_collection()
                and self.garbage_collection_lock.acquire(False)
            ):
                try:
                    self._cache_garbage_collection()
                finally:
                    self.garbage_collection_lock.release()
            if cache["thread"].is_alive():
                raise TimeoutException("target function timeout!")
            if cache["error"]:
                raise cache["error"]
            return cache["response"]

        return wrapper
