# reaktiv

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue) [![PyPI Version](https://img.shields.io/pypi/v/reaktiv.svg)](https://pypi.org/project/reaktiv/) ![PyPI - Downloads](https://img.shields.io/pypi/dm/reaktiv) ![License](https://img.shields.io/badge/license-MIT-green)

**Reactive Signals for Python** with first-class async support, inspired by Angular's reactivity model.

## Why reaktiv?

If you've worked with modern frontend frameworks like React, Vue, or Angular, you're familiar with the power of reactive state management. The idea is simple but transformative: when data changes, everything that depends on it updates automatically. This is the magic behind dynamic UIs and real-time systems.

But why should Python miss out on the benefits of reactivity? `reaktiv` brings these **reactive programming** advantages to your Python projects:

- **Automatic state propagation:** Change a value once, and all dependent computations update automatically.
- **Efficient updates:** Only the necessary parts are recomputed.
- **Async-friendly:** Seamlessly integrates with Python's `asyncio` for managing real-time data flows.
- **Zero external dependencies:** Lightweight and easy to incorporate into any project.
- **Type-safe:** Fully annotated for clarity and maintainability.

### Real-World Use Cases

Reactive programming isn't just a frontend paradigm. In Python, it can simplify complex backend scenarios such as:

- **Real-time data streams:** Stock prices, sensor readings, or live updates.
- **User session management:** Keep track of state changes without heavy manual subscription management.
- **Complex API workflows:** Automatically cascade changes across related computations.

By combining these features, `reaktiv` provides a robust foundation for building **reactive, real-time systems** - whether for data streaming, live monitoring, or even Python-powered UI frameworks.

## How it Works

`reaktiv` provides three core primitives:

1. **Signals**: Store a value and notify dependents when it changes.
2. **Computed Signals**: Derive values that automatically update when dependencies change.
3. **Effects**: Run side effects when signals or computed signals change.

## Core Concepts

```mermaid
graph LR
    A[Signal] -->|Value| B[Computed Signal]
    A -->|Change| C[Effect]
    B -->|Value| C
    B -->|Change| C
    C -->|Update| D[External System]
    
    classDef signal fill:#4CAF50,color:white;
    classDef computed fill:#2196F3,color:white;
    classDef effect fill:#FF9800,color:white;
    
    class A,B signal;
    class B computed;
    class C effect;
```

## Installation

```bash
pip install reaktiv
# or with uv
uv pip install reaktiv
```

## Quick Start

### Basic Reactivity

```python
import asyncio
from reaktiv import Signal, Effect

async def main():
    name = Signal("Alice")

    async def greet():
        print(f"Hello, {name.get()}!")

    # Create and schedule effect
    # IMPORTANT: Assign the Effect to a variable to ensure it is not garbage collected.
    greeter = Effect(greet)
    greeter.schedule()

    name.set("Bob")  # Prints: "Hello, Bob!"
    await asyncio.sleep(0)  # Process effects

asyncio.run(main())
```

### Using `update()`

Instead of calling `set(new_value)`, `update()` lets you modify a signal based on its current value.

```python
from reaktiv import Signal

counter = Signal(0)

# Standard way
counter.set(counter.get() + 1)

# Using update() for cleaner syntax
counter.update(lambda x: x + 1)

print(counter.get())  # 2
```

### Computed Values

```python
from reaktiv import Signal, ComputeSignal

# Synchronous context example
price = Signal(100)
tax_rate = Signal(0.2)
total = ComputeSignal(lambda: price.get() * (1 + tax_rate.get()))

print(total.get())  # 120.0
tax_rate.set(0.25)
print(total.get())  # 125.0
```

### Async Effects

```python
import asyncio
from reaktiv import Signal, Effect

async def main():
    counter = Signal(0)

    async def print_counter():
        print(f"Counter value is: {counter.get()}")

    # IMPORTANT: Assign the Effect to a variable to prevent it from being garbage collected.
    counter_effect = Effect(print_counter)
    counter_effect.schedule()

    for i in range(1, 4):
        await asyncio.sleep(1)  # Simulate an asynchronous operation or delay.
        counter.set(i)

    # Wait a bit to allow the last effect to process.
    await asyncio.sleep(1)

asyncio.run(main())
```

---

## Advanced Features

### Using `untracked()`

By default, when you access a signal inside a computed function or an effect, it will subscribe to that signal. However, sometimes you may want to access a signal **without tracking** it as a dependency.

```python
import asyncio
from reaktiv import Signal, Effect, untracked

async def main():
    count = Signal(10)
    message = Signal("Hello")

    async def log_message():
        tracked_count = count.get()
        untracked_msg = untracked(lambda: message.get())  # Not tracked as a dependency
        print(f"Count: {tracked_count}, Message: {untracked_msg}")

    effect = Effect(log_message)
    effect.schedule()

    count.set(20)  # Effect runs (count is tracked)
    await asyncio.sleep(1)
    message.set("New Message")  # Effect does NOT run (message is untracked)

    await asyncio.sleep(1)

asyncio.run(main())
```

---

### Using `on_cleanup()`

Sometimes, you need to clean up resources (e.g., cancel timers, close files, reset state) when an effect re-runs or is disposed.

```python
import asyncio
from reaktiv import Signal, Effect

async def main():
    active = Signal(False)

    async def monitor_status(on_cleanup):
        print("Monitoring started")
        active.get()

        def cleanup():
            print("Cleaning up before next run or disposal")

        on_cleanup(cleanup)

    effect = Effect(monitor_status)
    effect.schedule()

    await asyncio.sleep(1)
    active.set(True)  # Cleanup runs before the effect runs again

    await asyncio.sleep(1)
    effect.dispose()  # Cleanup runs before the effect is disposed

asyncio.run(main())

# Output:
# Monitoring started
# Cleaning up before next run or disposal
# Monitoring started
# Cleaning up before next run or disposal
```

### Custom Equality

When creating a Signal or ComputeSignal, you can provide a custom equality function to control when updates are triggered. This is useful for comparing objects by value rather than identity.

```python
from reaktiv import Signal

# Simple example: compare numbers with tolerance
num = Signal(10.0, equal=lambda a, b: abs(a - b) < 0.5)

# This won't trigger updates since 10.0 and 10.3 are within 0.5 of each other
num.set(10.3)  

# This will trigger updates since 10.0 and 10.6 differ by more than 0.5
num.set(10.6)  

# Custom class comparison example
class User:
    def __init__(self, name, role):
        self.name = name
        self.role = role
        
# By default, different User instances are considered different even with same data
# Let's create a signal with custom equality that only cares about the role
user = Signal(User("Alice", "admin"), 
              equal=lambda a, b: a.role == b.role)

# This won't trigger updates because the role is still "admin"
# even though it's a different User instance with a different name
user.set(User("Bob", "admin"))

# This will trigger updates because the role changed
user.set(User("Charlie", "user"))

# For deep equality with nested structures, a simple JSON-based approach works well:
import json

def json_equal(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

# This signal will only update when the content actually changes, 
# even for complex nested structures
user_profile = Signal({
    'name': 'Alice',
    'preferences': {'theme': 'dark', 'notifications': True}
}, equal=json_equal)

# This won't trigger updates (same content in a new object)
user_profile.set({
    'name': 'Alice',
    'preferences': {'theme': 'dark', 'notifications': True}
})

# This will trigger updates (content changed)
user_profile.set({
    'name': 'Alice',
    'preferences': {'theme': 'light', 'notifications': True}
})
```

---

## Real-Time Example: Polling System

```python
import asyncio
from reaktiv import Signal, ComputeSignal, Effect

async def main():
    candidate_a = Signal(100)
    candidate_b = Signal(100)
    
    total_votes = ComputeSignal(lambda: candidate_a.get() + candidate_b.get())
    percent_a = ComputeSignal(lambda: (candidate_a.get() / total_votes.get()) * 100)
    percent_b = ComputeSignal(lambda: (candidate_b.get() / total_votes.get()) * 100)

    async def display_results():
        print(f"Total: {total_votes.get()} | A: {candidate_a.get()} ({percent_a.get():.1f}%) | B: {candidate_b.get()} ({percent_b.get():.1f}%)")

    async def check_dominance():
        if percent_a.get() > 60:
            print("Alert: Candidate A is dominating!")
        elif percent_b.get() > 60:
            print("Alert: Candidate B is dominating!")

    # Assign effects to variables to ensure they are retained
    display_effect = Effect(display_results)
    alert_effect = Effect(check_dominance)
    
    display_effect.schedule()
    alert_effect.schedule()

    for _ in range(3):
        await asyncio.sleep(1)
        candidate_a.set(candidate_a.get() + 40)
        candidate_b.set(candidate_b.get() + 10)
    
    await asyncio.sleep(1)

asyncio.run(main())
```

**Sample Output:**

```
Total: 200 | A: 100 (50.0%) | B: 100 (50.0%)
Total: 250 | A: 140 (56.0%) | B: 110 (44.0%)
Total: 300 | A: 180 (60.0%) | B: 120 (40.0%)
Total: 350 | A: 220 (62.9%) | B: 130 (37.1%)
Alert: Candidate A is dominating!
```

## Examples

You can find example scripts in the `examples` folder to help you get started with using this project.

---

**Inspired by** Angular Signals • **Built for** Python's async-first world • **Made in** Hamburg