# reaktiv ![Python Version](https://img.shields.io/badge/python-3.9%2B-blue) [![PyPI Version](https://img.shields.io/pypi/v/reaktiv.svg)](https://pypi.org/project/reaktiv/) ![License](https://img.shields.io/badge/license-MIT-green)

**Reactive Signals for Python** with first-class async support, inspired by Angular's reactivity model.

```python
import asyncio
from reaktiv import Signal, ComputeSignal, Effect

async def main():
    count = Signal(0)
    doubled = ComputeSignal(lambda: count.get() * 2)

    async def log_count():
        print(f"Count: {count.get()}, Doubled: {doubled.get()}")

    Effect(log_count).schedule()
    count.set(5)  # Triggers: "Count: 5, Doubled: 10"
    await asyncio.sleep(0)  # Allow effects to process

asyncio.run(main())
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
import asyncio
from reaktiv import Signal, Effect

async def main():
    name = Signal("Alice")

    async def greet():
        print(f"Hello, {name.get()}!")

    # Create and schedule effect
    greeter = Effect(greet)
    greeter.schedule()

    name.set("Bob")  # Prints: "Hello, Bob!"
    await asyncio.sleep(0)  # Process effects

asyncio.run(main())
```

### Async Effects
```python
import asyncio
from reaktiv import Signal, Effect

async def main():
    data = Signal([])

    async def fetch_data():
        await asyncio.sleep(0.1)
        data.set([1, 2, 3])

    Effect(fetch_data).schedule()
    await asyncio.sleep(0.2)  # Allow async effect to complete

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

## Core Concepts

### Signals
```python
import asyncio
from reaktiv import Signal

async def main():
    user = Signal("Alice")
    print(user.get())  # "Alice"
    user.set("Bob")
    await asyncio.sleep(0)  # Process any dependent effects

asyncio.run(main())
```

### Effects in Async Context
```python
import asyncio
from reaktiv import Signal, Effect

async def main():
    stock = Signal(100.0)

    async def stock_ticker():
        price = stock.get()
        print(f"Current price: {price}")
        await asyncio.sleep(0.1)

    effect = Effect(stock_ticker)
    effect.schedule()
    
    stock.set(105.5)
    await asyncio.sleep(0.2)
    effect.dispose()

asyncio.run(main())
```

---

**Inspired by** Angular Signals • **Built for** Python's async-first world