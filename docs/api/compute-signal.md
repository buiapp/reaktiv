# Computed Signal API

The `Computed` class creates a signal that derives its value from other signals. It automatically tracks dependencies and updates when those dependencies change.

## Basic Usage

```python
from reaktiv import Signal, Computed

# Base signals
x = Signal(10)
y = Signal(20)

# Computed signal that depends on x and y
sum_xy = Computed(lambda: x() + y())

print(sum_xy())  # 30

# When a dependency changes, the computed value updates automatically
x.set(15)
print(sum_xy())  # 35
```

## Creation

```python
Computed(compute_fn: Callable[[], T], default: Optional[T] = None, *, equal: Optional[Callable[[T, T], bool]] = None) -> ComputedSignal[T]
```

Creates a new computed signal that derives its value from other signals.

### Parameters

- `compute_fn`: A function that computes the signal's value. When this function accesses other signals by calling them, dependencies are automatically tracked.
- `default`: An optional default value to use until the first computation and when computation fails due to an error.
- `equal`: Optional custom equality function to determine if two computed values are considered equal.

### Returns

A computed signal object that can be called to get its value.

## Methods

### Calling the computed signal

```python
sum_xy()  # equivalent to sum_xy.get()
```

Returns the computed value, calculating it if necessary. When called within an active effect or another computed signal, it establishes a dependency relationship.

**Returns**: The computed value.

**Note**: A computed signal is lazy. It only computes its value when called, and it caches the result until dependencies change.

## Advanced Methods

The following methods are typically used internally by the library:

### subscribe / unsubscribe

These methods work the same as in regular signals and are usually used internally by the library.

## Error Handling

If the computation function raises an exception, the computed signal catches it and:

1. Logs the exception via `traceback.print_exc()`
2. Returns the default value if one was provided, or the last successfully computed value

```python
from reaktiv import Signal, Computed

# Base signal
x = Signal(10)

# Computed signal with error handling
safe_compute = Computed(
    lambda: 100 / x(),  # Will throw ZeroDivisionError if x is 0
    default=0  # Default value to use in case of error
)

print(safe_compute())  # 10 (100 / 10)

# Set x to 0, which would cause a division by zero
x.set(0)

# Instead of crashing, it returns the default value
print(safe_compute())  # 0 (the default value)
```

## Lazy Evaluation

A key feature of computed signals is lazy evaluation. The computation function only runs:

1. The first time the signal is called
2. When dependencies have changed since the last computation

This means expensive computations are only performed when necessary:

```python
from reaktiv import Signal, Computed

x = Signal(10)
y = Signal(20)

def expensive_computation():
    print("Computing...")
    return x() * y()

result = Computed(expensive_computation)

# Nothing happens yet - computation is lazy

# First access - computation runs
print(result())  # Prints: "Computing..." then "200"

# Second access - no computation needed because nothing changed
print(result())  # Just prints "200" (no "Computing..." message)

# Change a dependency
x.set(5)

# Now accessing will recompute
print(result())  # Prints: "Computing..." then "100"
```

## Note on ComputeSignal vs computed()

While reaktiv provides both the `Computed` class (alias for `ComputeSignal`) and `computed()` shortcut function, the recommended approach is to use the `Computed` class directly for a more consistent API.

The `computed()` function is deprecated and will be removed in a future version. It currently emits a deprecation warning:

```python
# Deprecated approach (will show warning):
from reaktiv import signal, computed
x = signal(10)
doubled = computed(lambda: x() * 2)

# Recommended approach:
from reaktiv import Signal, Computed
x = Signal(10)
doubled = Computed(lambda: x() * 2)
```