
# reaktiv ![Python Version](https://img.shields.io/badge/python-3.9%2B-blue) [![PyPI Version](https://img.shields.io/pypi/v/reaktiv.svg)](https://pypi.org/project/reaktiv/) ![License](https://img.shields.io/badge/license-MIT-green)

**Reactive Signals for Python** with first-class async support, inspired by Angular's reactivity model.

```python
from reaktiv import Signal, ComputeSignal, Effect

count = Signal(0)
doubled = ComputeSignal(lambda: count.get() * 2)

async def log_count():
    print(f"Count: {count.get()}, Doubled: {doubled.get()}")

Effect(log_count).schedule()
count.set(5)  # Triggers: "Count: 5, Doubled: 10"
```

## Features

⚡ **Angular-inspired reactivity**  
✅ **First-class async/await support**  
🧠 **Automatic dependency tracking**  
💡 **Zero external dependencies**  
🧩 **Type annotations throughout**  
♻️ **Efficient memory management**

## Installation

```bash
pip install reaktiv
# or with uv
uv pip install reaktiv
```

## Quick Start

### Basic Reactivity
```python
from reaktiv import Signal, Effect

name = Signal("Alice")

async def greet():
    print(f"Hello, {name.get()}!")

# Create and schedule effect
greeter = Effect(greet)
greeter.schedule()

name.set("Bob")  # Prints: "Hello, Bob!"
```

### Async Effects
```python
from reaktiv import Signal, Effect
import asyncio

data = Signal([])

async def fetch_data():
    await asyncio.sleep(0.1)
    data.set([1, 2, 3])

Effect(fetch_data).schedule()
```

### Computed Values
```python
from reaktiv import Signal, ComputeSignal

price = Signal(100)
tax_rate = Signal(0.2)

total = ComputeSignal(lambda: price.get() * (1 + tax_rate.get()))

print(total.get())  # 120.0
tax_rate.set(0.25)
print(total.get())  # 125.0
```

## Core Concepts

### Signals
```python
# Create
user = Signal("Alice")

# Get value
print(user.get())  # "Alice"

# Update value
user.set("Bob")
```

### Computed Signals
```python
a = Signal(2)
b = Signal(3)
sum_signal = ComputeSignal(
    lambda: a.get() + b.get(),
    default=0  # Optional error fallback
)
```

### Effects
```python
async def stock_ticker():
    price = stock.get()
    print(f"Current price: {price}")
    await save_to_db(price)

# Create and schedule
effect = Effect(stock_ticker)
effect.schedule()

# Dispose when done
effect.dispose()
```

## Advanced Usage

### Error Handling in Computed
```python
# Safe computation with fallback
divisor = Signal(2)
safe_divide = ComputeSignal(
    lambda: 10 / divisor.get(),
    default=float('inf')
)

divisor.set(0)  # Prints traceback but maintains last valid value
```

### Nested Effects
```python
async def parent_effect():
    if user.get().is_admin:
        # Create child effect conditionally
        Effect(child_effect).schedule()
```

### Dynamic Dependencies
```python
switch = Signal(True)
a = Signal(10)
b = Signal(20)

dynamic = ComputeSignal(
    lambda: a.get() if switch.get() else b.get()
)
```

---

**Inspired by** Angular Signals • **Built for** Python's async-first world