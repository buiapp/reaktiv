"""Execution context for dependency tracking."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, TypeVar, Union, ContextManager, overload

from . import graph
from .protocols import ReadableSignal

T = TypeVar("T")


@overload
def untracked() -> ContextManager[None]: ...


@overload
def untracked(func_or_signal: Callable[[], T]) -> T: ...


@overload
def untracked(func_or_signal: ReadableSignal[T]) -> T: ...


def untracked(
    func_or_signal: Union[Callable[[], T], ReadableSignal[T], None] = None,
) -> Union[T, ContextManager[None]]:
    """Execute a function without establishing dependencies.
    
    This utility prevents dependency tracking, useful when you want to read signal
    values without creating reactive relationships. Use as a context manager (recommended)
    or as a function wrapper.
    
    Args:
        func_or_signal: Optional function to execute, or None for context manager usage
            
    Returns:
        The result of the function if provided, or a context manager if None
        
    Examples:
        As a context manager (recommended):
        ```python
        from reaktiv import Signal, Effect, untracked
        
        count = Signal(0)
        other = Signal(100)
        
        def my_effect():
            # Tracked read
            c = count()
            
            # Untracked reads within this block
            with untracked():
                o = other()
            
            print(f"Count: {c}, Other: {o}")
        
        # Keep reference to prevent GC
        effect = Effect(my_effect)
        # Prints: "Count: 0, Other: 100"
        
        other.set(200)
        # No print - 'other' was read in untracked context
        ```
        
        As a function wrapper:
        ```python
        from reaktiv import Signal, Effect, untracked
        
        count = Signal(0)
        other = Signal(100)
        
        def my_effect():
            # This creates a dependency
            c = count()
            
            # This does NOT create a dependency
            o = untracked(lambda: other())
            
            print(f"Count: {c}, Other: {o}")
        
        # Keep reference to prevent GC
        effect = Effect(my_effect)
        # Prints: "Count: 0, Other: 100"
        
        count.set(1)
        # Prints: "Count: 1, Other: 100" (effect re-runs)
        
        other.set(200)
        # No print - effect doesn't depend on 'other'
        ```
    """
    if func_or_signal is None:

        @contextmanager
        def _ctx():
            prev = graph.set_active_consumer(None)
            try:
                yield
            finally:
                graph.set_active_consumer(prev)

        return _ctx()

    prev = graph.set_active_consumer(None)
    try:
        return func_or_signal()
    finally:
        graph.set_active_consumer(prev)
