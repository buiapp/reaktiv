# reaktiv ![Python Version](https://img.shields.io/badge/python-3.9%2B-blue) [![PyPI Version](https://img.shields.io/pypi/v/reaktiv.svg)](https://pypi.org/project/reaktiv/) ![License](https://img.shields.io/badge/license-MIT-green)

**Reactive Signals for Python** with first-class async support, inspired by Angular's reactivity model.

```python
import asyncio
from reaktiv import Signal, ComputeSignal, Effect

async def main():
    # Real-time stock prices
    apple_price = Signal(195.00)
    google_price = Signal(2750.00)
    
    # User's portfolio
    shares = Signal({
        'AAPL': 100,
        'GOOGL': 50
    })

    # Computed total portfolio value
    portfolio_value = ComputeSignal(lambda: (
        shares.get()['AAPL'] * apple_price.get() +
        shares.get()['GOOGL'] * google_price.get()
    ))

    # Price alert system
    async def check_alerts():
        if apple_price.get() > 200:
            print("📈 AAPL alert: Above $200!")
        if google_price.get() < 2700:
            print("📉 GOOGL alert: Below $2700!")

    # Automatic updates
    async def live_updates():
        # Simulate real-time updates
        while True:
            await asyncio.sleep(1)
            apple_price.set(apple_price.get() * 1.01)  # +1%
            google_price.set(google_price.get() * 0.995)  # -0.5%
            print(f"🍏 AAPL: ${apple_price.get():,.2f}  🌐 GOOGL: ${google_price.get():,.2f}")

    # Track portfolio value
    async def monitor_portfolio():
        print(f"💰 Current value: ${portfolio_value.get():,.2f}")

    # Set up effects
    alerts_effect = Effect(check_alerts)
    updates_effect = Effect(live_updates)
    portfolio_effect = Effect(monitor_portfolio)

    alerts_effect.schedule()
    updates_effect.schedule()
    portfolio_effect.schedule()
    
    # Run for 5 seconds
    await asyncio.sleep(5)

asyncio.run(main())
```

Output:

```
💰 Current value: $157,000.00
🍏 AAPL: $196.95  🌐 GOOGL: $2,736.25
💰 Current value: $156,507.50
🍏 AAPL: $198.92  🌐 GOOGL: $2,722.57
💰 Current value: $156,020.39
🍏 AAPL: $200.91  🌐 GOOGL: $2,708.96
📈 AAPL alert: Above $200!
💰 Current value: $155,538.66
🍏 AAPL: $202.92  🌐 GOOGL: $2,695.41
📈 AAPL alert: Above $200!
📉 GOOGL alert: Below $2700!
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