import copy
import time
import heapq
import traceback
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
    """Raised when target function timeout."""

    pass


class TimeoutDecorator:
    """
    TimeoutDecorator run target function in a single thread.

    +------------+
    |            |
    |            |
    |            |                  +-----------+
    |  Caller 1  +----+             |           |
    |            |    |             |           |
    |            |    |             |           |
    |            |    |             |           |
    +------------+    |             |           |
                      |             |           |
                      |             |           |
    +------------+    |             |           |                  +----------+
    |            |    |             |           |                  |          |
    |            |    | call at the |           | only single call |          |
    |            |    |  same time  |  Timeout  |    to the back   |          |
    |  Caller 2  +----+------------>+   Cache   +----------------->+ Function |
    |            |    |             |           |                  |          |
    |            |    |             |           |                  |          |
    |            |    |             |           |                  |          |
    +------------+    |             |           |                  +----------+
                      |             |           |
                      |             |           |
    +------------+    |             |           |
    |            |    |             |           |
    |            |    |             |           |
    |            |    |             |           |
    |  Caller 3  +----+             |           |
    |            |                  +-----------+
    |            |
    |            |
    +------------+
    """

    def __init__(
        self,
        timeout=None,
        cache_time=0,
        cache_exception_time=0,
        name="",
        garbage_collection_interval=5,
        garbage_collection_count=30,
        copy_response=False,
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
        cache_exception_time: int
            after function return incorrectly,
                how long should we cache the exception (in sec).
        name: str
            prometheus_client metrics prefix
        garbage_collection_count: int
            garbage collection threshold
        garbage_collection_interval: int
            the second to avoid collection too often.
        copy_response: bool
            use copy.deepcopy on the response from the target function.

        Returns
        -------
        TimeoutDecorator
            decorator class.
        """
        self.timeout = timeout
        self.cache_time = cache_time
        self.cache_exception_time = cache_exception_time
        self.name = name
        self.garbage_collection_interval = garbage_collection_interval
        self.garbage_collection_count = garbage_collection_count
        self.copy_response = copy_response

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
                    if "traceback" in self.thread_cache[_key]:
                        traceback.clear_frames(
                            self.thread_cache[_key]["traceback"],
                        )
                    del self.thread_cache[_key]
                    _collected_total.labels(name=self.name).inc(1)
        _heap_cache_count.labels(
            name=self.name,
        ).set(len(self.heap))
        _thread_cache_count.labels(
            name=self.name,
        ).set(len(self.thread_cache))
        current_time = time.time()
        if self.garbage_collection_timestamp != 0:
            _collection_run_interval.labels(
                name=self.name,
            ).observe(current_time - self.garbage_collection_timestamp)
        self.garbage_collection_timestamp = current_time

    def is_expired(self, cache):
        """Check thread_cache dict is expired."""
        return cache["expired_timestamp"] < time.time()

    def _cal_cache_key(*arg, **kwargs):
        return hash(tuple([hash(arg), tuple(sorted(kwargs.items()))]))

    def __call__(self, function):
        """
        Call target function with response cache.

        Raises
        ------
        TimeoutException
            If the target function exceeds the executing time.
        """

        def wrapper(*arg, **kwargs):
            # cache stores the context for this function call.
            # same function call will use the same cache.
            cache = {
                "thread": None,
                "error": None,
                "response": None,
                "expired_timestamp": float("inf"),
            }

            # target_function is a wrapper of the real function
            def target_function(key):
                try:
                    if self.copy_response:
                        cache["response"] = copy.deepcopy(
                            function(*arg, **kwargs),
                        )
                    else:
                        cache["response"] = function(*arg, **kwargs)
                    cache["expired_timestamp"] = time.time() + self.cache_time
                except Exception as e:
                    cache["error"] = e
                    cache["expired_timestamp"] = (
                        time.time() + self.cache_exception_time
                    )
                with self.heap_lock:
                    heapq.heappush(
                        self.heap,
                        (
                            cache["expired_timestamp"],
                            key,
                        ),
                    )
                    _heap_cache_count.labels(
                        name=self.name,
                    ).set(len(self.heap))

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
                    name=self.name,
                ).set(len(self.thread_cache))
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
                e = cache["error"]
                raise copy.copy(e).with_traceback(e.__traceback__)
            if self.copy_response:
                return copy.deepcopy(cache["response"])
            else:
                return cache["response"]

        return wrapper


class NoDecoratorException(Exception):
    """Raised if cache type not found."""

    pass


class DecoratorSelector:
    """Wrapper for select different "run_python" function cache method."""

    def __init__(
        self,
        cache_type="None",
        **kwargs,
    ):
        """
        Init function to select the target decorators.

        Parameters
        ----------
        cache_type: str
            select different decorators.
        kwargs: Dict[string, Any]
            parameters passed to the target cache decorators.

        Raises
        ------
        NoDecoratorException
            If no cache type matches.
        """
        self._functions = []
        self.select_decorator(cache_type, **kwargs)

    def select_decorator(
        self,
        cache_type="Timeout",
        **kwargs,
    ):
        """
        Re-init the decorator.

        Parameters
        ----------
        cache_type: str
            select different decorators.
        kwargs: Dict[string, Any]
            parameters passed to the target cache decorators.

        Raises
        ------
        NoDecoratorException
            If no cache type matches.
        """
        if cache_type == "Timeout":
            self._decorator = self._timeout_decorator_init(**kwargs)
        elif cache_type == "None":
            self._decorator = lambda function: function
        else:
            raise NoDecoratorException(
                "cache_type %s not support" % cache_type
            )
        for index in range(0, len(self._functions)):
            function = self._functions[index][0]
            self._functions[index] = (
                function,
                self._decorator(function),
            )

    def _timeout_decorator_init(
        self,
        timeout=None,
        cache_time=0,
        cache_exception_time=0,
        name="",
        garbage_collection_interval=5,
        garbage_collection_count=30,
        copy_response=False,
    ):
        if timeout is not None:
            timeout = int(timeout)
        cache_time = int(cache_time)
        cache_exception_time = int(cache_exception_time)
        name = str(name)
        garbage_collection_interval = int(garbage_collection_interval)
        garbage_collection_count = int(garbage_collection_count)
        copy_response = bool(copy_response)
        return TimeoutDecorator(
            timeout=timeout,
            cache_time=cache_time,
            cache_exception_time=cache_exception_time,
            name=name,
            garbage_collection_interval=garbage_collection_interval,
            garbage_collection_count=garbage_collection_count,
            copy_response=copy_response,
        )

    def __call__(self, function):
        """Call the decorator that we initialized."""
        target_function = self._decorator(function)
        self._functions.append(
            (
                function,
                target_function,
            )
        )
        index = len(self._functions) - 1

        def wrapper(*arg, **kwargs):
            return self._functions[index][1](*arg, **kwargs)

        return wrapper
