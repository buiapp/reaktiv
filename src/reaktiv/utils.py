"""Utility functions for the reaktiv library."""

import asyncio
from typing import AsyncIterator, TypeVar

from .signal import Signal
from .effect import Effect

T = TypeVar("T")


async def to_async_iter(signal: Signal[T], initial: bool = True) -> AsyncIterator[T]:
    """Convert a signal to an async iterator that yields each time the signal changes.

    Args:
        signal: The signal to convert into an async iterator
        initial: Whether to yield the current value immediately (True) or only yield on changes (False)

    Returns:
        An async iterator that yields the signal's value on each change
    """
    queue = asyncio.Queue()

    # Create an effect that pushes new values to the queue
    def push_to_queue():
        try:
            value = signal.get()
            queue.put_nowait(value)
        except Exception as e:
            # In case of errors, put the exception in the queue
            queue.put_nowait(e)

    # Create the effect
    effect = Effect(push_to_queue)

    try:
        while True:
            value = await queue.get()

            if not initial:
                # If initial is False, skip the first value
                initial = True
                continue
            elif isinstance(value, Exception):
                raise value
            yield value
    finally:
        # Clean up the effect when the iterator is done
        effect.dispose()
