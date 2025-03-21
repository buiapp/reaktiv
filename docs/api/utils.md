# Utilities API

reaktiv provides several utility functions to enhance your reactive programming experience.

## batch

```python
batch()
```

A context manager that batches multiple signal updates together, deferring computations and effects until the batch completes.

### Usage

```python
from reaktiv import Signal, ComputeSignal, Effect, batch

x = Signal(5)
y = Signal(10)
sum_xy = ComputeSignal(lambda: x.get() + y.get())

def log_sum():
    print(f"Sum: {sum_xy.get()}")

logger = Effect(log_sum)
logger.schedule()  # Prints: "Sum: 15"

# Without batching, this would trigger two separate updates:
# x.set(10)  # Triggers recomputation & effect
# y.set(20)  # Triggers recomputation & effect again

# With batching, updates are processed together:
with batch():
    x.set(10)  # No immediate effect execution
    y.set(20)  # No immediate effect execution
# After batch completes, computations and effects run once
# Prints: "Sum: 30"
```

### Benefits

- **Performance**: Reduces unnecessary recomputations when multiple signals change together
- **Consistency**: Ensures effects only see the final state after all updates are complete
- **Atomicity**: Makes a series of updates appear as a single atomic change

## untracked

```python
untracked(func: Callable[[], T]) -> T
```

Executes a function without creating dependencies on any signals accessed within it.

### Parameters

- `func`: The function to execute without tracking signal dependencies.

### Returns

- The return value of the executed function.

### Usage

```python
from reaktiv import Signal, Effect, untracked

name = Signal("Alice")
greeting = Signal("Hello")

def log_message():
    # This creates a dependency on the 'name' signal
    person = name.get()
    
    # This does NOT create a dependency on the 'greeting' signal
    prefix = untracked(lambda: greeting.get())
    
    print(f"{prefix}, {person}!")

logger = Effect(log_message)
logger.schedule()  # Prints: "Hello, Alice!"

# This will trigger the effect because 'name' is a dependency
name.set("Bob")  # Prints: "Hello, Bob!"

# This will NOT trigger the effect because 'greeting' is accessed via untracked()
greeting.set("Hi")  # No effect execution
```

### Use Cases

- Accessing signals without creating dependencies
- Reading configuration values that shouldn't trigger reactivity
- Breaking circular dependencies
- Optimizing performance by selectively tracking only necessary dependencies

## to_async_iter

```python
to_async_iter(signal: Signal[T]) -> AsyncIterator[T]
```

Converts a signal into an async iterator that yields values whenever the signal changes.

### Parameters

- `signal`: The signal to convert to an async iterator.

### Returns

- An async iterator that yields the signal's value on each change.

### Usage

```python
import asyncio
from reaktiv import Signal, to_async_iter

async def main():
    counter = Signal(0)
    
    # Create a task that increments the counter
    async def increment_counter():
        for i in range(1, 6):
            await asyncio.sleep(1)
            counter.set(i)
    
    # Start the counter task
    asyncio.create_task(increment_counter())
    
    # Use the counter signal as an async iterator
    async for value in to_async_iter(counter):
        print(f"Counter changed: {value}")
        if value >= 5:
            break

asyncio.run(main())
```

### Output

```
Counter changed: 0
Counter changed: 1
Counter changed: 2
Counter changed: 3
Counter changed: 4
Counter changed: 5
```

### Use Cases

- Integrating signals with async for loops
- Processing signal values as a stream
- Converting between signals and other async primitives
- Building reactive data pipelines
- Using signals with other async libraries