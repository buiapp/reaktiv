"""Utility functions for the reaktiv library."""

import asyncio
from typing import AsyncIterator, TypeVar

from .protocols import ReadableSignal
from .effect import Effect

T = TypeVar("T")


async def to_async_iter(signal: ReadableSignal[T], initial: bool = True) -> AsyncIterator[T]:
    """Convert a signal to an async iterator that yields on each change.
    
    This utility allows you to use signals with Python's async iteration syntax,
    making it easy to integrate reaktiv with async code and frameworks.
    
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
        from reaktiv import Signal, to_async_iter
        
        counter = Signal(0)
        
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
        from reaktiv import Signal, to_async_iter
        
        status = Signal("idle")
        
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
        from reaktiv import Signal, to_async_iter
        
        data_signal = Signal(None)
        
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
