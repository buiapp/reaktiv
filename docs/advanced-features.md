# Advanced Features

This page covers advanced features and techniques in reaktiv for building more sophisticated reactive systems.

## Custom Equality Functions

By default, reaktiv uses identity comparison (`is`) to determine if a signal's value has changed. For more complex types, you can provide custom equality functions:

```python
from reaktiv import Signal

# Custom equality for dictionaries
def dict_equal(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return a == b
    if set(a.keys()) != set(b.keys()):
        return False
    return all(a[k] == b[k] for k in a)

# Create a signal with custom equality
user = Signal({"name": "Alice", "age": 30}, equal=dict_equal)

# This won't trigger updates because the dictionaries are equal by value
user.set({"name": "Alice", "age": 30})

# This will trigger updates because the "age" value is different
user.set({"name": "Alice", "age": 31})
```

Custom equality functions are especially useful for:
- Complex data structures like dictionaries, lists, or custom objects
- Case-insensitive string comparison
- Numerical comparison with tolerance (for floating-point values)
- Domain-specific equality (e.g., comparing users by ID regardless of other attributes)

## Effect Cleanup

Effects can register cleanup functions that will run before the next execution or when the effect is disposed:

```python
from reaktiv import Signal, Effect

counter = Signal(0)

def counter_effect(on_cleanup):
    value = counter()
    print(f"Setting up for counter value: {value}")
    
    # Set up some resource or state
    
    # Define cleanup function
    def cleanup():
        print(f"Cleaning up for counter value: {value}")
        # Release resources, remove event listeners, etc.
    
    # Register the cleanup function
    on_cleanup(cleanup)

# Create and schedule the effect
logger = Effect(counter_effect)

# Prints: "Setting up for counter value: 0"

# Update the signal
counter.set(1)
# Prints: "Cleaning up for counter value: 0"
# Prints: "Setting up for counter value: 1"

# Dispose the effect
logger.dispose()
# Prints: "Cleaning up for counter value: 1"
```

This pattern is useful for:
- Managing subscriptions to external event sources
- Releasing resources when values change or the effect is disposed
- Setting up and tearing down UI elements in response to data changes
- Cancelling pending operations when new values arrive

## Asynchronous Iteration

The `to_async_iter` utility lets you use signals with `async for` loops:

```python
import asyncio
from reaktiv import Signal, to_async_iter

async def main():
    counter = Signal(0)
    
    # Start a task that increments the counter
    async def increment_counter():
        for i in range(1, 5):
            await asyncio.sleep(1)
            counter.set(i)
    
    asyncio.create_task(increment_counter())
    
    # Use the signal as an async iterator
    async for value in to_async_iter(counter):
        print(f"Got value: {value}")
        if value >= 4:
            break

asyncio.run(main())
```

Output:
```
Got value: 0
Got value: 1
Got value: 2
Got value: 3
Got value: 4
```

This is useful for:
- Building reactive data processing pipelines
- Integrating with other async code
- Responding to signal changes in event loops
- Creating reactive streams of data

## Selective Dependency Tracking

You can selectively control which signals create dependencies using `untracked`:

```python
from reaktiv import Signal, Effect, untracked

user_id = Signal(123)
user_data = Signal({"name": "Alice"})
show_details = Signal(False)

def render_user():
    # Always creates a dependency on user_id
    id_value = user_id()
    
    # Only access user_data if show_details is true,
    # but don't create a dependency on show_details
    if untracked(lambda: show_details()):
        print(f"User {id_value}: {user_data()}")
    else:
        print(f"User {id_value}")

# Create and schedule the effect
display = Effect(render_user)

# Update dependencies will trigger the effect
user_id.set(456)

# This update won't trigger the effect, even though it changes the output
show_details.set(True)
```