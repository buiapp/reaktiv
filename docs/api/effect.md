# Effect API

The `Effect` class creates side effects that automatically run when their dependencies change. Effects are useful for  updating UI elements, logging, API calls, and other operations that respond to state changes.

## Basic Usage

```python
from reaktiv import Signal, Effect

# Create a signal
counter = Signal(0)

# Create an effect that runs when counter changes
counter_effect = Effect(lambda: print(f"Counter: {counter()}"))
# Immediately prints: "Counter: 0"

# When the signal changes, the effect runs automatically
counter.set(1)
# Prints: "Counter: 1"

# Clean up when done
counter_effect.dispose()
```

## Creation

```python
Effect(func: Callable[..., Union[None, Coroutine[None, None, None]]]) -> Effect
```

Creates a new effect that automatically runs when its dependencies change.

### Parameters

- `func`: A function or coroutine function to run when dependencies change. Dependencies are automatically tracked when this function accesses signals by calling them. If the function accepts a parameter, it receives an `on_cleanup` function.

### Returns

An effect object that manages the execution of the function when dependencies change.

## Methods

### dispose

```python
dispose() -> None
```

Disposes of the effect, removing all dependencies and preventing it from running again.

**Note**: You should call `dispose()` when an effect is no longer needed to prevent memory leaks.

## Asynchronous Effects

reaktiv has first-class support for asynchronous effects:

```python
import asyncio
from reaktiv import Signal, Effect

async def main():
    counter = Signal(0)
    
    async def log_counter():
        print(f"Counter value: {counter()}")
    
    # Create and schedule the async effect
    logger = Effect(log_counter)  # Prints: "Counter value: 0"
    
    # Update the signal and wait for the effect to run
    counter.set(1)
    await asyncio.sleep(0)  # Gives the effect time to execute
    # Prints: "Counter value: 1"
    
    # Clean up
    logger.dispose()

asyncio.run(main())
```

## Cleanup Functions

Effects can register cleanup functions that will be executed before the effect runs again or when it's disposed:

```python
from reaktiv import Signal, Effect

counter = Signal(0)

def counter_effect(on_cleanup):
    value = counter()
    print(f"Counter value: {value}")
    
    # Register a cleanup function
    def cleanup():
        print(f"Cleaning up for value: {value}")
    
    on_cleanup(cleanup)

# Create and schedule the effect with cleanup
logger = Effect(counter_effect)
# Prints: "Counter value: 0"

# Update the signal
counter.set(1)
# Prints: "Cleaning up for value: 0"
# Prints: "Counter value: 1"

# Dispose the effect
logger.dispose()
# Prints: "Cleaning up for value: 1"
```

## Memory Management

Effects are not automatically garbage collected as long as they're actively tracking dependencies. To prevent memory leaks:

1. Keep a reference to your effect as long as you need it
2. Call `dispose()` when you're done with the effect
3. Avoid creating effects inside loops or frequently-called functions without disposing of them

```python
from reaktiv import Signal, Effect

def create_temporary_effect(s):
    # This effect will only exist while the function runs
    temp_effect = Effect(lambda: print(f"Value: {s()}"))
    # ... do something ...
    temp_effect.dispose()  # Clean up properly

# Better pattern for component lifecycle
class MyComponent:
    def __init__(self, s):
        self.s = s
        self.effect_instance = Effect(self._render)
    
    def _render(self):
        print(f"Rendering: {self.s()}")
    
    def destroy(self):
        self.effect_instance.dispose()
```

## Notification Batching

When multiple signals change, their effects are batched to avoid unnecessary executions:

```python
from reaktiv import Signal, Effect, batch

x = Signal(1)
y = Signal(2)

def log_values():
    print(f"x: {x()}, y: {y()}")

logger = Effect(log_values)  # Prints: "x: 1, y: 2"

# Without batching, the effect would run twice:
# x.set(10)  # Effect runs
# y.set(20)  # Effect runs again

# With batching, the effect runs only once after all changes:
with batch():
    x.set(10)  # No effect execution yet
    y.set(20)  # No effect execution yet
# After batch completes: Effect runs once with new values
# Prints: "x: 10, y: 20"
```

## Note on Effect vs effect()

While reaktiv provides both the `Effect` class and `effect()` shortcut function, the recommended approach is to use the `Effect` class directly for a more consistent API.

The `effect()` function is deprecated and will be removed in a future version. It currently emits a deprecation warning:

```python
# Deprecated approach (will show warning):
from reaktiv import signal, effect
count = signal(0)
count_effect = effect(lambda: print(f"Count: {count()}"))

# Recommended approach:
from reaktiv import Signal, Effect
count = Signal(0)
count_effect = Effect(lambda: print(f"Count: {count()}"))
```