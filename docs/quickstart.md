# Quick Start Guide

This guide will walk you through the basic usage of reaktiv to help you get started with reactive programming in Python.

## Basic Concepts

reaktiv is built around three core primitives:

1. **Signals**: Store a value and notify dependents when it changes
2. **Computed Signals**: Derive values that automatically update when dependencies change
3. **Effects**: Run side effects when signals or computed signals change

## Installation

The quickest way to get started is to install reaktiv using pip:

```bash
pip install reaktiv
# or with uv
uv pip install reaktiv
```

## Basic Example

Here's a simple example showing the core functionality:

```python
from reaktiv import Signal, Computed, Effect

# Create a signal with initial value
name = Signal("Alice")

# A computed value that stays in sync automatically
greeting = Computed(lambda: f"Hello, {name()}!")

# Keep a reference to the effect to prevent garbage collection
greeter = Effect(lambda: print(greeting()))

# Prints: "Hello, Alice!"

# Update the signal value — everything reacts automatically
name.set("Bob")  # Prints: "Hello, Bob!"
```

## Solving Real Problems

Let's look at a more practical example. Imagine you're calculating the total price of items in a shopping cart:

```python
from reaktiv import Signal, Computed, Effect

# Create signals for our base values
price = Signal(10.0)
quantity = Signal(2)
tax_rate = Signal(0.1)  # 10% tax

# Create computed values that automatically update when dependencies change
subtotal = Computed(lambda: price() * quantity())
tax = Computed(lambda: subtotal() * tax_rate())
total = Computed(lambda: subtotal() + tax())

# Create an effect to display the total (will run initially and when dependencies change)
display = Effect(lambda: print(f"Order total: ${total():.2f}"))
# Prints: "Order total: $22.00"

# Update a signal - all dependent computed values and effects update automatically
quantity.set(3)
# Prints: "Order total: $33.00"

# Update multiple values
price.set(15.0)
tax_rate.set(0.15)
# Prints: "Order total: $51.75"
```

Notice how we never needed to manually recalculate the total! reaktiv automatically detects the dependencies between values and updates them when needed.

## Computed Values

Computed signals let you derive values from other signals:

```python
from reaktiv import Signal, Computed

# Create base signals
price = Signal(100)
tax_rate = Signal(0.2)

# Create a computed signal that depends on price and tax_rate
total = Computed(lambda: price() * (1 + tax_rate()))

print(total())  # 120.0

# Change a dependency
tax_rate.set(0.25)

# The computed value updates automatically
print(total())  # 125.0
```

## Working with Updates

Instead of using `set(new_value)`, you can use `update()` to modify a signal based on its current value:

```python
from reaktiv import Signal

counter = Signal(0)

# Standard way
counter.set(counter() + 1)

# Using update() for cleaner syntax
counter.update(lambda x: x + 1)

print(counter())  # 2
```

## Batching Updates

When making multiple signal updates, you can batch them together to optimize performance:

```python
from reaktiv import Signal, Computed, batch

x = Signal(10)
y = Signal(20)
sum_xy = Computed(lambda: x() + y())

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
from reaktiv import Signal

# Custom equality function for case-insensitive string comparison
def case_insensitive_equal(a, b):
    return a.lower() == b.lower()

# Create a signal with custom equality function
name = Signal("Alice", equal=case_insensitive_equal)

# This won't trigger updates because "alice" is considered equal to "Alice"
name.set("alice")

# This will trigger updates because "Bob" is not equal to "Alice"
name.set("Bob")
```

## Optional: Async usage

Recommendation: Prefer synchronous effects for predictable behavior. If you need to integrate with asyncio, either spawn a background task from a sync effect, or (advanced) use an async effect.

```python
import asyncio
from reaktiv import Signal, Effect

counter = Signal(0)

# Recommended: sync effect that spawns async work
def on_counter():
    value = counter()
    async def background():
        await asyncio.sleep(0.1)
        print(f"Counter value is: {value}")
    asyncio.create_task(background())

counter_effect = Effect(on_counter)

# Advanced: direct async effect (use with care)
# async def on_counter_async():
#     await asyncio.sleep(0.1)
#     print(f"Counter value is: {counter()}")
# counter_effect = Effect(on_counter_async)

for i in range(1, 3):
    counter.set(i)
```

## Next Steps

- Read [Why reaktiv?](why-reaktiv.md) to understand when and why to use reaktiv
- See the [Core Concepts](core-concepts.md) page for a deeper understanding of reaktiv's design
- Check out the [Examples](examples/index.md) page for real-world usage examples
- Explore the [Advanced Features](advanced-features.md) for more powerful capabilities