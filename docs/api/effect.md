# Effect API

The `effect()` function in reaktiv allows you to execute side effects when signals change. It's useful for updating UI elements, logging, making network requests, or any other operations that respond to state changes.

## Basic Usage

```python
from reaktiv import signal, effect

# Create a signal
counter = signal(0)

# Define an effect that uses the signal
def log_counter():
    print(f"Counter value: {counter()}")

# Create and schedule the effect
logger = effect(log_counter)  # Prints: "Counter value: 0"

# Update the signal
counter.set(1)  # Prints: "Counter value: 1"

# Clean up when done
logger.dispose()
```

## Creation

```python
effect(func: Callable[[], Union[None, Coroutine[Any, Any, Any]]]) -> Effect
```

Creates a new effect that executes the provided function.

### Parameters

- `func`: The function to execute when dependencies change. This can be either a synchronous function or an asynchronous coroutine function.

### Returns

An Effect object that automatically starts tracking dependencies and responding to changes.

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
from reaktiv import signal, effect

async def main():
    counter = signal(0)
    
    async def log_counter():
        print(f"Counter value: {counter()}")
    
    # Create and schedule the async effect
    logger = effect(log_counter)  # Prints: "Counter value: 0"
    
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
from reaktiv import signal, effect

counter = signal(0)

def counter_effect(on_cleanup):
    value = counter()
    print(f"Counter value: {value}")
    
    # Register a cleanup function
    def cleanup():
        print(f"Cleaning up for value: {value}")
    
    on_cleanup(cleanup)

# Create and schedule the effect with cleanup
logger = effect(counter_effect)
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
from reaktiv import signal, effect

def create_temporary_effect(s):
    # This effect will only exist while the function runs
    temp_effect = effect(lambda: print(f"Value: {s()}"))
    # ... do something ...
    temp_effect.dispose()  # Clean up properly

# Better pattern for component lifecycle
class MyComponent:
    def __init__(self, s):
        self.s = s
        self.effect_instance = effect(self._render)
    
    def _render(self):
        print(f"Rendering: {self.s()}")
    
    def destroy(self):
        self.effect_instance.dispose()
```

## Notification Batching

When multiple signals change, their effects are batched to avoid unnecessary executions:

```python
from reaktiv import signal, effect, batch

x = signal(1)
y = signal(2)

def log_values():
    print(f"x: {x()}, y: {y()}")

logger = effect(log_values)  # Prints: "x: 1, y: 2"

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

While reaktiv provides both the `Effect` class and `effect()` shortcut function, the recommended approach is to use the `effect()` shortcut function for a more concise and ergonomic API.