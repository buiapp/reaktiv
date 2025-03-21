# ComputeSignal API

The `ComputeSignal` class extends `Signal` to provide values that are computed from other signals. It automatically tracks dependencies and updates when those dependencies change.

## Basic Usage

```python
from reaktiv import Signal, ComputeSignal

# Base signals
x = Signal(10)
y = Signal(20)

# Computed signal that depends on x and y
sum_xy = ComputeSignal(lambda: x.get() + y.get())

print(sum_xy.get())  # 30

# When a dependency changes, the computed value updates automatically
x.set(15)
print(sum_xy.get())  # 35
```

## Constructor

```python
ComputeSignal(compute_fn: Callable[[], T], default: Optional[T] = None, *, equal: Optional[Callable[[T, T], bool]] = None)
```

Creates a new computed signal that derives its value from other signals.

### Parameters

- `compute_fn`: A function that computes the signal's value. When this function calls `get()` on other signals, dependencies are automatically tracked.
- `default`: An optional default value to use until the first computation and when computation fails due to an error.
- `equal`: Optional custom equality function to determine if two computed values are considered equal.

## Methods

### get

```python
get() -> T
```

Returns the computed value, calculating it if necessary. When called within an active effect or another computed signal, it establishes a dependency relationship.

**Returns**: The computed value.

**Note**: Unlike a regular `Signal`, a `ComputeSignal` is lazy. It only computes its value when `get()` is called, and it caches the result until dependencies change.

## Inherited Methods

`ComputeSignal` inherits from `Signal` but overrides some behaviors:

### set

The `set()` method is not available on computed signals. Their values are derived from their dependencies, so you cannot set them directly. Attempting to call `set()` will raise an `AttributeError`.

### update

The `update()` method is also not available for the same reasons as `set()`.

### subscribe / unsubscribe

These methods work the same as in `Signal` and are usually used internally by the library.

## Error Handling

If the computation function raises an exception, `ComputeSignal` catches it and:

1. Logs the exception via `traceback.print_exc()`
2. Returns the default value if one was provided, or the last successfully computed value

```python
from reaktiv import Signal, ComputeSignal

# Base signal
x = Signal(10)

# Computed signal with error handling
safe_compute = ComputeSignal(
    compute_fn=lambda: 100 / x.get(),  # Will throw ZeroDivisionError if x is 0
    default=0  # Default value to use in case of error
)

print(safe_compute.get())  # 10 (100 / 10)

# Set x to 0, which would cause a division by zero
x.set(0)

# Instead of crashing, it returns the default value
print(safe_compute.get())  # 0 (the default value)
```

## Lazy Evaluation

A key feature of `ComputeSignal` is lazy evaluation. The computation function only runs:

1. The first time `get()` is called
2. When dependencies have changed since the last computation

This means expensive computations are only performed when necessary:

```python
from reaktiv import Signal, ComputeSignal

x = Signal(10)
y = Signal(20)

def expensive_computation():
    print("Computing...")
    return x.get() * y.get()

result = ComputeSignal(expensive_computation)

# Nothing happens yet - computation is lazy

# First access - computation runs
print(result.get())  # Prints: "Computing..." then "200"

# Second access - no computation needed because nothing changed
print(result.get())  # Just prints "200" (no "Computing..." message)

# Change a dependency
x.set(5)

# Now accessing will recompute
print(result.get())  # Prints: "Computing..." then "100"
```