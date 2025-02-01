# reaktiv ![Python Version](https://img.shields.io/badge/python-3.9%2B-blue) [![PyPI Version](https://img.shields.io/pypi/v/reaktiv.svg)](https://pypi.org/project/reaktiv/) ![License](https://img.shields.io/badge/license-MIT-green)

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