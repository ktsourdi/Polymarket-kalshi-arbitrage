"""Timing utilities for performance monitoring.

This module provides timing decorators and context managers to measure
execution time of operations for debugging and optimization.
"""

import time
from contextlib import contextmanager
from functools import wraps
from typing import Callable, Dict, Optional


class TimingTracker:
    """Track multiple timing intervals."""
    
    def __init__(self):
        self.timings: Dict[str, float] = {}
        self._starts: Dict[str, float] = {}
    
    def start(self, name: str) -> None:
        """Start timing an operation."""
        self._starts[name] = time.time()
    
    def stop(self, name: str) -> float:
        """Stop timing an operation and return elapsed time.
        
        Args:
            name: Name of the operation
            
        Returns:
            Elapsed time in seconds
        """
        if name not in self._starts:
            return 0.0
        
        elapsed = time.time() - self._starts[name]
        self.timings[name] = elapsed
        del self._starts[name]
        return elapsed
    
    def get(self, name: str) -> Optional[float]:
        """Get timing for a completed operation."""
        return self.timings.get(name)
    
    def format_time(self, seconds: float) -> str:
        """Format seconds into human-readable string.
        
        Args:
            seconds: Time in seconds
            
        Returns:
            Formatted string (e.g., "1.23s", "123ms", "5m 32s")
        """
        if seconds < 0.001:
            return f"{seconds * 1000000:.0f}μs"
        elif seconds < 1:
            return f"{seconds * 1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.2f}s"
        else:
            minutes = int(seconds // 60)
            secs = seconds % 60
            return f"{minutes}m {secs:.1f}s"
    
    def summary(self) -> Dict[str, str]:
        """Get all timings formatted as strings.
        
        Returns:
            Dictionary of operation names to formatted time strings
        """
        return {name: self.format_time(seconds) for name, seconds in self.timings.items()}


@contextmanager
def timer(name: str, tracker: Optional[TimingTracker] = None):
    """Context manager for timing code blocks.
    
    Args:
        name: Name of the operation being timed
        tracker: Optional TimingTracker instance to record timings
        
    Example:
        with timer("fetch_data", my_tracker):
            # code to time
            pass
    """
    start = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start
        if tracker:
            tracker.timings[name] = elapsed


def timed_function(tracker: Optional[TimingTracker] = None):
    """Decorator to time function execution.
    
    Args:
        tracker: Optional TimingTracker instance to record timings
        
    Example:
        @timed_function(my_tracker)
        def my_function():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.time() - start
                if tracker:
                    tracker.timings[func.__name__] = elapsed
        return wrapper
    return decorator


def format_duration(seconds: float) -> str:
    """Format seconds into human-readable string.
    
    Args:
        seconds: Time in seconds
        
    Returns:
        Formatted string (e.g., "1.23s", "123ms", "5m 32s")
    """
    if seconds < 0.001:
        return f"{seconds * 1000000:.0f}μs"
    elif seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.2f}s"
    else:
        minutes = int(seconds // 60)
        secs = seconds % 60
        return f"{minutes}m {secs:.1f}s"

