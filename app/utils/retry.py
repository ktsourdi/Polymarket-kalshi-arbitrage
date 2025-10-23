"""Retry utilities with exponential backoff.

This module provides retry logic for network requests and other
operations that may fail transiently. This improves reliability
without overwhelming servers with rapid retries.
"""

import asyncio
import random
from functools import wraps
from typing import TypeVar, Callable, Type, Tuple, Optional

from app.utils.logging import get_logger


logger = get_logger("retry")


T = TypeVar('T')


async def retry_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    jitter: bool = True,
    *args,
    **kwargs
) -> T:
    """Retry an async function with exponential backoff.
    
    Args:
        func: The async function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        backoff_factor: Multiplier for delay between retries
        max_delay: Maximum delay between retries in seconds
        exceptions: Tuple of exception types to catch and retry
        jitter: Whether to add random jitter to delays
        *args: Positional arguments to pass to func
        **kwargs: Keyword arguments to pass to func
        
    Returns:
        The result of calling func
        
    Raises:
        The last exception raised by func if all retries fail
    """
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except exceptions as e:
            last_exception = e
            
            if attempt < max_retries - 1:
                # Add jitter to prevent thundering herd
                if jitter:
                    actual_delay = delay * (0.5 + random.random() * 0.5)
                else:
                    actual_delay = delay
                
                actual_delay = min(actual_delay, max_delay)
                
                logger.debug(
                    "Retry attempt %d/%d after %.2fs: %s",
                    attempt + 1,
                    max_retries,
                    actual_delay,
                    str(e)
                )
                
                await asyncio.sleep(actual_delay)
                delay *= backoff_factor
            else:
                logger.warning(
                    "All %d retry attempts failed: %s",
                    max_retries,
                    str(e)
                )
    
    if last_exception:
        raise last_exception
    
    raise RuntimeError("No exception captured but retries exhausted")


def retry_sync_with_backoff(
    func: Callable[..., T],
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    jitter: bool = True,
    *args,
    **kwargs
) -> T:
    """Retry a synchronous function with exponential backoff.
    
    Args:
        func: The function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        backoff_factor: Multiplier for delay between retries
        max_delay: Maximum delay between retries in seconds
        exceptions: Tuple of exception types to catch and retry
        jitter: Whether to add random jitter to delays
        *args: Positional arguments to pass to func
        **kwargs: Keyword arguments to pass to func
        
    Returns:
        The result of calling func
        
    Raises:
        The last exception raised by func if all retries fail
    """
    delay = initial_delay
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except exceptions as e:
            last_exception = e
            
            if attempt < max_retries - 1:
                # Add jitter to prevent thundering herd
                if jitter:
                    actual_delay = delay * (0.5 + random.random() * 0.5)
                else:
                    actual_delay = delay
                
                actual_delay = min(actual_delay, max_delay)
                
                logger.debug(
                    "Retry attempt %d/%d after %.2fs: %s",
                    attempt + 1,
                    max_retries,
                    actual_delay,
                    str(e)
                )
                
                import time
                time.sleep(actual_delay)
                delay *= backoff_factor
            else:
                logger.warning(
                    "All %d retry attempts failed: %s",
                    max_retries,
                    str(e)
                )
    
    if last_exception:
        raise last_exception
    
    raise RuntimeError("No exception captured but retries exhausted")


def retry_decorator(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 60.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    jitter: bool = True
):
    """Decorator for async functions with retry logic.
    
    Usage:
        @retry_decorator(max_retries=5, initial_delay=2.0)
        async def my_function():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await retry_with_backoff(
                func,
                max_retries=max_retries,
                initial_delay=initial_delay,
                backoff_factor=backoff_factor,
                max_delay=max_delay,
                exceptions=exceptions,
                jitter=jitter,
                *args,
                **kwargs
            )
        return wrapper
    return decorator

