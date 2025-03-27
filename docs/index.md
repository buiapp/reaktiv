# reaktiv: Reactive Signals for Python

**reaktiv** is a Python library that brings reactive programming principles to Python with first-class async support.

![Python Version](https://img.shields.io/badge/python-3.9%2B-blue)
![PyPI Version](https://img.shields.io/pypi/v/reaktiv.svg)
![PyPI - Downloads](https://img.shields.io/pypi/dm/reaktiv)
![License](https://img.shields.io/badge/license-MIT-green)

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
from reaktiv import signal, effect

# Create a signal with initial value
name = signal("Alice")

# Create an effect that reacts to changes
def on_name_change():
    print(f"Hello, {name()}!")

# Create and schedule the effect
greeter = effect(on_name_change)  # Prints: "Hello, Alice!"

# Update the signal value
name.set("Bob")  # Will print: "Hello, Bob!"
```

## Documentation

* [Installation](installation.md) - How to install the library
* [Quick Start](quickstart.md) - Get up and running quickly
* [Core Concepts](core-concepts.md) - Understanding the fundamentals
* [API Reference](api/signal.md) - Detailed API documentation
* [Advanced Features](advanced-features.md) - More powerful capabilities