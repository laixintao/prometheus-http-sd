import time
import pytest

from random import random
from prometheus_http_sd.decroator import TimeDecorator, TimeoutException


def test_timeout_cache():
    @TimeDecorator(
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
    decorator = TimeDecorator(
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
