import time

from prometheus_http_sd.decorator import (
    TimeoutDecorator,
    TimeoutException,
    DecoratorSelector,
)


def test_decorator_select():
    selector = DecoratorSelector(
        "None",
    )

    @selector
    def function():
        time.sleep(2)
        return "hello"

    assert function() == "hello", "should be none selector"

    selector.select_decorator(
        cache_type="Timeout",
        timeout=1,
    )
    try:
        function()
        assert False, "it should raise a timeout exception"
        pass
    except TimeoutException as e:
        pass
