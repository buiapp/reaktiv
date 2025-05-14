# reaktiv: Reactive Signals for Python

<div align="center">
  <img src="assets/logo_3.png" alt="reaktiv logo" width="300">
</div>

**reaktiv** is a Python library that brings reactive programming principles to Python with first-class async support.

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![PyPI Version](https://img.shields.io/pypi/v/reaktiv.svg)
![PyPI - Downloads](https://img.shields.io/pypi/dm/reaktiv)
![License](https://img.shields.io/badge/license-MIT-green)

## Links

- **Documentation**: [https://reaktiv.readthedocs.io/](https://reaktiv.readthedocs.io/)
- **GitHub**: [https://github.com/buiapp/reaktiv](https://github.com/buiapp/reaktiv)

## What is reaktiv?

reaktiv is a lightweight reactive state management library for Python that automatically keeps your derived values and side effects in sync with their data sources. When data changes, everything that depends on it updates automatically.

Think of it as a spreadsheet for your Python application: change a cell, and all formulas using that cell recalculate instantly.

## Why Use reaktiv?

reaktiv solves common pain points in state management:

- **Eliminates manual state synchronization** - No more forgetting to update derived values
- **Reduces bugs** - Ensures consistent state throughout your application
- **Simplifies code** - Declare relationships once, not every time data changes
- **Improves performance** - Only recomputes what actually needs to change
- **First-class async support** - Built for Python's asyncio ecosystem

[Learn more about why you should use reaktiv →](why-reaktiv.md)

## Features

* **Automatic state propagation:** Change a value once, and all dependent computations update automatically
* **Efficient updates:** Only the necessary parts are recomputed
* **Async-friendly:** Seamlessly integrates with Python's `asyncio` for managing real-time data flows
* **Zero external dependencies:** Lightweight and easy to incorporate into any project
* **Type-safe:** Fully annotated for clarity and maintainability

## Overview

reaktiv is built around three core primitives:

1. **Signals**: Store values and notify dependents when they change
2. **Computed Signals**: Derive values that automatically update when dependencies change
3. **Effects**: Run side effects when signals or computed signals change

```python
from reaktiv import Signal, Effect

# Create a signal with initial value
name = Signal("Alice")

# Create an effect that reacts to changes
def on_name_change():
    print(f"Hello, {name()}!")

# Create the effect
greeter = Effect(on_name_change)  # Prints: "Hello, Alice!"

# Update the signal value
name.set("Bob")  # Will print: "Hello, Bob!"
```

## Documentation

* [Installation](installation.md) - How to install the library
* [Quick Start](quickstart.md) - Get up and running quickly
* [Why reaktiv?](why-reaktiv.md) - When and why to use reaktiv
* [Core Concepts](core-concepts.md) - Understanding the fundamentals
* [API Reference](api/signal.md) - Detailed API documentation
* [Advanced Features](advanced-features.md) - More powerful capabilities
* [Real-World Examples](examples/index.md) - Practical applications