import time
import pytest
import threading
import traceback

from random import random
from prometheus_http_sd.decorator import TimeoutDecorator, TimeoutException


def test_timeout_cache():
    @TimeoutDecorator(
        timeout=0.5,
        cache_time=1,
        garbage_collection_interval=0,
        garbage_collection_count=0,
    )
    def havy_function():
        time.sleep(2)
        return random()

    # test if the decorator can raise an exception after timeout.
    with pytest.raises(TimeoutException):
        _ = havy_function()

    # test if the decorator can cache the result.
    time.sleep(2)
    first_call = havy_function()
    second_call = havy_function()
    assert first_call is second_call, "the function did't cache the result :("

    time.sleep(1)
    # after cache_time, the next call should returns different value.
    with pytest.raises(TimeoutException):
        _ = havy_function()
    time.sleep(2)
    third_call = havy_function()
    assert first_call != third_call, "oops, cache_time doesn't work!"


def test_garbage_collection():
    decorator = TimeoutDecorator(
        timeout=0.5,
        cache_time=1,
        garbage_collection_interval=0,
        garbage_collection_count=1000000,  # avoid automatic garbage collection
    )

    @decorator
    def function(n):
        return object()

    expired_result = []
    alive_result = []
    old_object = function(10)
    for i in range(5):
        expired_result.append((i, function(i)))

    time.sleep(1.2)
    for j in range(5, 10):
        alive_result.append((j, function(j)))

    new_object = function(10)
    decorator._cache_garbage_collection()
    for key, _ in alive_result:
        assert decorator._cal_cache_key(key) in decorator.thread_cache

    for key, _ in expired_result:
        assert decorator._cal_cache_key(key) not in decorator.thread_cache

    assert old_object is not new_object
    assert decorator._cal_cache_key(10) in decorator.thread_cache


def test_exception_cache():
    decorator = TimeoutDecorator(
        timeout=0.5,
        cache_time=999,
        garbage_collection_interval=0,
        garbage_collection_count=1000000,  # avoid automatic garbage collection
    )

    global a
    a = 0

    @decorator
    def function():
        global a
        a += 1
        raise Exception("A")

    first_error = None
    second_error = None
    try:
        function()
        assert False, "function should raise error"
    except Exception as e:
        first_error = e

    try:
        function()
        assert False, "function should raise error"
    except Exception as e:
        second_error = e

    assert first_error is not second_error
    assert a == 2


def test_duplicated_append_traceback_problem():
    decorator = TimeoutDecorator(
        timeout=2,
        cache_time=999,
        garbage_collection_interval=0,
        garbage_collection_count=1000000,  # avoid automatic garbage collection
    )

    global first_error
    global second_error
    first_error = None
    second_error = None

    @decorator
    def function():
        time.sleep(1)
        raise Exception("A")

    def first_function():
        global first_error
        try:
            function()
            assert False, "function should raise error"
        except Exception as e:
            first_error = e

    def second_function():
        global second_error
        try:
            function()
            assert False, "function should raise error"
        except Exception as e:
            second_error = e

    first_thread = threading.Thread(
        target=first_function,
    )

    second_thread = threading.Thread(
        target=second_function,
    )
    first_thread.start()
    second_thread.start()

    first_thread.join()
    second_thread.join()

    assert first_error is not second_error

    print(traceback.extract_tb(
        first_error.__traceback__
    ))
    print(traceback.extract_tb(
        second_error.__traceback__
    ))

    # since python stores the tb in the same address,
    # raise a exception twice will be a problem.
    # therefore, we copy the exception in the cache decorator
    #    to correct the traceback
    assert traceback.extract_tb(
        first_error.__traceback__
    )[0] != traceback.extract_tb(
        second_error.__traceback__
    )[0]
    # expect the first item (function call from "test_timeout"),
    # other tb should be the same
    assert traceback.extract_tb(
        first_error.__traceback__
    )[1:] == traceback.extract_tb(
        second_error.__traceback__
    )[1:]
