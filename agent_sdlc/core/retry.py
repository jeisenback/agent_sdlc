from __future__ import annotations
from typing import Callable, Tuple, Type
import time
import random


def with_retry(
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    backoff: float = 2.0,
    retry_on: Tuple[Type[BaseException], ...] = (Exception,),
):
    """Simple retry decorator with exponential backoff and jitter.

    This avoids adding heavier dependencies like `tenacity` while providing
    a predictable retry policy for core primitives.
    """

    def decorator(func: Callable):
        def wrapper(*args, **kwargs):
            attempt = 0
            delay = float(initial_delay)
            while True:
                try:
                    return func(*args, **kwargs)
                except retry_on:
                    attempt += 1
                    if attempt >= max_attempts:
                        raise
                    jitter = random.uniform(0, delay * 0.1)
                    time.sleep(delay + jitter)
                    delay *= backoff

        wrapper.__name__ = getattr(func, "__name__", "wrapper")
        return wrapper

    return decorator
