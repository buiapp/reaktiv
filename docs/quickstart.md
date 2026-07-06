# Quick Start Guide

This guide will walk you through the basic usage of reaktiv to help you get started with reactive programming in Python.

## Basic Concepts

reaktiv is built around three core primitives:

1. **`signal`**: Store a value and notify dependents when it changes
2. **`computed`**: Derive values that automatically update when dependencies change
3. **`effect`**: Run side effects when signals or computed signals change

## Installation

The quickest way to get started is to install reaktiv using pip:

```bash
pip install reaktiv
# or with uv
uv pip install reaktiv
```

## Basic Example

Here's a simple example showing the core functionality:

```pyodide install="reaktiv" height="18" theme="github,one_dark"
from reaktiv import computed, effect, signal

# Create a signal with initial value
name = signal("Alice")

# A computed value that stays in sync automatically
@computed
def greeting():
    return f"Hello, {name()}!"

# Keep a reference to the effect to prevent garbage collection
def print_greeting():
    print(greeting())

greeter = effect(print_greeting)

# Prints: "Hello, Alice!"

# Update the signal value — everything reacts automatically
name.set("Bob")  # Prints: "Hello, Bob!"
greeter.dispose()
```

## Solving Real Problems

Let's look at a more practical example. Imagine you're calculating the total price of items in a shopping cart:

```pyodide install="reaktiv" assets="no" height="28" theme="github,one_dark"
from reaktiv import computed, effect, signal

# Create signals for our base values
price = signal(10.0)
quantity = signal(2)
tax_rate = signal(0.1)  # 10% tax

# Create computed values that automatically update when dependencies change
@computed
def subtotal():
    return price() * quantity()

@computed
def tax():
    return subtotal() * tax_rate()

@computed
def total():
    return subtotal() + tax()

# Create an effect to display the total (will run initially and when dependencies change)
def print_total():
    print(f"Order total: ${total():.2f}")

display = effect(print_total)
# Prints: "Order total: $22.00"

# Update a signal - all dependent computed values and effects update automatically
quantity.set(3)
# Prints: "Order total: $33.00"

# Update multiple values
price.set(15.0)
tax_rate.set(0.15)
# Prints: "Order total: $51.75"
display.dispose()
```

Notice how we never needed to manually recalculate the total! reaktiv automatically detects the dependencies between values and updates them when needed.

## Computed Values

Computed signals let you derive values from other signals using the
`@computed` decorator:

```pyodide install="reaktiv" assets="no" height="18" theme="github,one_dark"
from reaktiv import computed, signal

# Create base signals
price = signal(100)
tax_rate = signal(0.2)

# Create a computed signal that depends on price and tax_rate
@computed
def total():
    return price() * (1 + tax_rate())

print(total())  # 120.0

# Change a dependency
tax_rate.set(0.25)

# The computed value updates automatically
print(total())  # 125.0
```

You can also use the factory function style if you prefer:
```pyodide install="reaktiv" assets="no" height="12" theme="github,one_dark"
# Alternative: factory function style
from reaktiv import computed, signal

price = signal(100)
tax_rate = signal(0.2)

@computed
def total():
    return price() * (1 + tax_rate())

print(total())  # 120.0
```

## Working with Updates

Instead of using `set(new_value)`, you can use `update()` to modify a signal based on its current value:

```pyodide install="reaktiv" assets="no" height="18" theme="github,one_dark"
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

```pyodide install="reaktiv" assets="no" height="18" theme="github,one_dark"
from reaktiv import signal, computed, batch

x = signal(10)
y = signal(20)

@computed
def sum_xy():
    return x() + y()

# Without batching, computed values are recalculated after each signal update
x.set(5)  # Recalculates sum_xy
y.set(10)  # Recalculates sum_xy again

# With batching, computed values are recalculated only once after all updates
with batch():
    x.set(15)  # No recalculation yet
    y.set(25)  # No recalculation yet
    # sum_xy will be recalculated only once after the batch completes

print(sum_xy())  # 40
```

## Custom Equality

By default, signals use identity (`is`) for equality checking. You can provide a custom equality function:

```pyodide install="reaktiv" assets="no" height="18" theme="github,one_dark"
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

print(name())  # Bob
```

## Optional: Async usage

Recommendation: Prefer synchronous effects for predictable behavior. If you need to integrate with asyncio, either spawn a background task from a sync effect, or (advanced) use an async effect.

```pyodide install="reaktiv" assets="no" height="24" theme="github,one_dark"
import asyncio
from reaktiv import signal, effect

counter = signal(0)

# Recommended: sync effect that spawns async work
def on_counter():
    value = counter()
    async def background():
        await asyncio.sleep(0.05)
        print(f"Counter value is: {value}")
    asyncio.create_task(background())

counter_effect = effect(on_counter)

# Advanced: direct async effect (use with care)
# async def on_counter_async():
#     await asyncio.sleep(0.1)
#     print(f"Counter value is: {counter()}")
# counter_effect = effect(on_counter_async)

for i in range(1, 3):
    counter.set(i)

await asyncio.sleep(0.1)
counter_effect.dispose()
```

## Next Steps

- Read [Why reaktiv?](why-reaktiv.md) to understand when and why to use reaktiv
- See the [Core Concepts](core-concepts.md) page for a deeper understanding of reaktiv's design
- Organize application state with the [ReactiveModel API guide](api/reactive-model.md)
- Check out the [Examples](examples/index.md) page for real-world usage examples
- Explore the [Advanced Features](advanced-features.md) for more powerful capabilities
