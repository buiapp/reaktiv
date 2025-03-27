# Quick Start Guide

This guide will walk you through the basic usage of reaktiv to help you get started with reactive programming in Python.

## Basic Concepts

reaktiv is built around three core primitives:

1. **Signals**: Store a value and notify dependents when it changes
2. **Computed Signals**: Derive values that automatically update when dependencies change
3. **Effects**: Run side effects when signals or computed signals change

## Basic Example

Here's a simple example showing the core functionality:

```python
import asyncio
from reaktiv import signal, effect

async def main():
    # Create a signal with initial value
    name = signal("Alice")
    
    # Create an effect that depends on the signal
    async def greet():
        print(f"Hello, {name()}!")
    
    # Create and schedule the effect (important: keep a reference to prevent garbage collection)
    greeter = effect(greet)
    
    # Prints: "Hello, Alice!"
    
    # Update the signal value
    name.set("Bob")  # Will trigger the effect to run again
    
    # Give the effect time to process
    await asyncio.sleep(0)  # Prints: "Hello, Bob!"

asyncio.run(main())
```

## Computed Values

Computed signals let you derive values from other signals:

```python
from reaktiv import signal, computed

# Create base signals
price = signal(100)
tax_rate = signal(0.2)

# Create a computed signal that depends on price and tax_rate
total = computed(lambda: price() * (1 + tax_rate()))

print(total())  # 120.0

# Change a dependency
tax_rate.set(0.25)

# The computed value updates automatically
print(total())  # 125.0
```

## Working with Updates

Instead of using `set(new_value)`, you can use `update()` to modify a signal based on its current value:

```python
from reaktiv import signal

counter = signal(0)

# Standard way
counter.set(counter() + 1)

# Using update() for cleaner syntax
counter.update(lambda x: x + 1)

print(counter())  # 2
```

## Batching Updates

When making multiple signal updates, you can batch them together to optimize performance:

```python
from reaktiv import signal, computed, batch

x = signal(10)
y = signal(20)
sum_xy = computed(lambda: x() + y())

# Without batching, computed values are recalculated after each signal update
x.set(5)  # Recalculates sum_xy
y.set(10)  # Recalculates sum_xy again

# With batching, computed values are recalculated only once after all updates
with batch():
    x.set(15)  # No recalculation yet
    y.set(25)  # No recalculation yet
    # sum_xy will be recalculated only once after the batch completes
```

## Custom Equality

By default, signals use identity (`is`) for equality checking. You can provide a custom equality function:

```python
from reaktiv import signal

# Custom equality function for case-insensitive string comparison
def case_insensitive_equal(a, b):
    return a.lower() == b.lower()

# Create a signal with custom equality function
name = signal("Alice", equal=case_insensitive_equal)

# This won't trigger updates because "alice" is considered equal to "Alice"
name.set("alice")

# This will trigger updates because "Bob" is not equal to "Alice"
name.set("Bob")
```

## Asynchronous Effects

reaktiv has first-class support for async functions:

```python
import asyncio
from reaktiv import signal, effect

async def main():
    counter = signal(0)
    
    async def print_counter():
        print(f"Counter value is: {counter()}")
    
    # Keep a reference to prevent garbage collection
    counter_effect = effect(print_counter)
    
    for i in range(1, 4):
        await asyncio.sleep(1)
        counter.set(i)
    
    # Cleaning up when done
    counter_effect.dispose()

asyncio.run(main())
```

## Next Steps

- See the [Core Concepts](core-concepts.md) page for a deeper understanding of reaktiv's design
- Check out the [Examples](examples.md) page for real-world usage examples
- Explore the [Advanced Features](advanced-features.md) for more powerful capabilities