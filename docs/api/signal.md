# Signal API

The `Signal` class is the core building block in reaktiv. It provides a container for values that can change over time and notify dependents of those changes.

## Basic Usage

```python
from reaktiv import Signal

# Create a signal with an initial value
counter = Signal(0)

# Get the current value
value = counter.get()  # 0

# Set a new value
counter.set(5)

# Update using a function
counter.update(lambda x: x + 1)  # Now 6
```

## Constructor

```python
Signal(value: T, *, equal: Optional[Callable[[T, T], bool]] = None)
```

Creates a new signal with an initial value.

### Parameters

- `value`: The initial value of the signal.
- `equal`: Optional custom equality function to determine if two values should be considered equal. By default, identity (`is`) is used.

## Methods

### get

```python
get() -> T
```

Returns the current value of the signal. When called within an active effect or computed signal, it establishes a dependency relationship.

**Returns**: The current value of the signal.

### set

```python
set(new_value: T) -> None
```

Updates the signal's value and notifies subscribers if the value has changed.

**Parameters**:
- `new_value`: The new value to set.

**Note**: A notification is triggered only if the new value is considered different from the current value. By default, identity comparison (`is`) is used unless a custom equality function was provided.

### update

```python
update(update_fn: Callable[[T], T]) -> None
```

Updates the signal's value by applying a function to its current value.

**Parameters**:
- `update_fn`: A function that takes the current value and returns the new value.

### subscribe

```python
subscribe(subscriber: Subscriber) -> None
```

Adds a subscriber to be notified when the signal's value changes.

**Parameters**:
- `subscriber`: An object implementing the `Subscriber` protocol with a `notify()` method.

**Note**: This is typically used internally by the library. Most applications should use `Effect` or `ComputeSignal` instead.

### unsubscribe

```python
unsubscribe(subscriber: Subscriber) -> None
```

Removes a subscriber so it no longer receives notifications.

**Parameters**:
- `subscriber`: The subscriber to remove.

**Note**: This is typically used internally by the library.

## Custom Equality Example

```python
from reaktiv import Signal

# Custom equality function for comparing dictionaries by value
def dict_equal(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return a == b
    if a.keys() != b.keys():
        return False
    return all(a[k] == b[k] for k in a)

# Create a signal with custom equality
user = Signal({"name": "Alice", "age": 30}, equal=dict_equal)

# This won't trigger updates because the dictionaries have the same key-value pairs
user.set({"name": "Alice", "age": 30})

# This will trigger updates because the "age" value differs
user.set({"name": "Alice", "age": 31})
``` 