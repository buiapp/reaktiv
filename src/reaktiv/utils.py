"""Utility functions for the reaktiv library."""

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator, Generic, TypeVar, Union

from .protocols import ReadableSignal
from .effect import Effect, EffectDescriptor
from . import scheduler as _sched

T = TypeVar("T")


@dataclass(frozen=True)
class _SignalValue(Generic[T]):
    value: T


@dataclass(frozen=True)
class _SignalError:
    error: Exception


async def to_async_iter(signal: ReadableSignal[T], initial: bool = True) -> AsyncIterator[T]:
    """Convert a signal to an async iterator that yields on each change.
    
    This utility allows you to use signals with Python's async iteration syntax,
    making it easy to integrate reaktiv with async code and frameworks.

    The iterator buffers the values it *observes*, not every write: writes
    inside one ``batch()`` are observed once, with the final value, and writes
    of an equal value are not observed at all. Observed values are kept
    without a bound and yielded in order, so a slow consumer holds its whole
    backlog in memory.
    Writes may come from any thread; values are delivered on the event loop
    that iterates.
    
    Args:
        signal: The signal to convert into an async iterator
        initial: Whether to yield the current value immediately (True) or only 
            yield on changes (False)
            
    Yields:
        The signal's value each time it changes
        
    Examples:
        Basic usage:
        ```python
        import asyncio
        from reaktiv import signal, to_async_iter
        
        counter = signal(0)
        
        async def watch_counter():
            async for value in to_async_iter(counter):
                print(f"Counter: {value}")
                if value >= 3:
                    break
        
        async def main():
            # Start watching
            task = asyncio.create_task(watch_counter())
            
            # Make changes
            await asyncio.sleep(0.1)
            counter.set(1)
            await asyncio.sleep(0.1)
            counter.set(2)
            await asyncio.sleep(0.1)
            counter.set(3)
            
            await task
        
        asyncio.run(main())
        # Prints:
        # Counter: 0
        # Counter: 1
        # Counter: 2
        # Counter: 3
        ```
        
        Skip initial value:
        ```python
        import asyncio
        from reaktiv import signal, to_async_iter
        
        status = signal("idle")
        
        async def watch_status():
            # Only yield on changes, not initial value
            async for value in to_async_iter(status, initial=False):
                print(f"Status changed to: {value}")
                if value == "done":
                    break
        
        async def main():
            task = asyncio.create_task(watch_status())
            
            await asyncio.sleep(0.1)
            status.set("loading")  # Prints: "Status changed to: loading"
            await asyncio.sleep(0.1)
            status.set("done")     # Prints: "Status changed to: done"
            
            await task
        
        asyncio.run(main())
        ```
        
        Integration with async frameworks:
        ```python
        import asyncio
        from reaktiv import signal, to_async_iter
        
        data_signal = signal(None)
        
        async def process_data_stream():
            async for data in to_async_iter(data_signal):
                if data is not None:
                    # Process data
                    await send_to_api(data)
        
        async def main():
            processor = asyncio.create_task(process_data_stream())
            
            # Simulate data updates
            data_signal.set({"id": 1})
            await asyncio.sleep(0.1)
            data_signal.set({"id": 2})
            
            # ... continue processing
        ```
    """
    queue = asyncio.Queue[Union[_SignalValue[T], _SignalError]]()
    loop = asyncio.get_running_loop()

    # The effect runs on whichever thread writes the signal, but asyncio queues
    # are not thread-safe: hand every item to the iterator's loop, in order.
    def push_to_queue():
        item: Union[_SignalValue[T], _SignalError]
        try:
            item = _SignalValue(signal.get())
        except Exception as e:
            item = _SignalError(e)
        _sched.call_soon(loop, queue.put_nowait, item)

    # Create the effect
    effect = Effect(push_to_queue)
    if isinstance(effect, EffectDescriptor):
        raise TypeError("to_async_iter expected an Effect instance")

    try:
        while True:
            item = await queue.get()

            if not initial:
                # If initial is False, skip the first value
                initial = True
                continue
            if isinstance(item, _SignalError):
                raise item.error
            yield item.value
    finally:
        # Clean up the effect when the iterator is done
        effect.dispose()
