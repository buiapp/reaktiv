# reaktiv: Reactive Signals for Python

<div align="center">
  <img src="assets/logo.svg" alt="reaktiv logo" width="300">
</div>

**Reactive declarative state management for Python** — automatic dependency tracking and reactive updates for your application state.

<div class="badge-container flex flex-wrap justify-center gap-2">
  <img src="https://img.shields.io/badge/python-3.9%2B-blue" alt="Python Version">
  <a href="https://pypi.org/project/reaktiv/"><img src="https://img.shields.io/pypi/v/reaktiv.svg" alt="PyPI Version"></a>
  <a href="https://pepy.tech/projects/reaktiv"><img src="https://static.pepy.tech/badge/reaktiv/month" alt="PyPI Downloads"></a>
  <img src="https://readthedocs.org/projects/reaktiv/badge/" alt="Documentation Status">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
  <a href="https://microsoft.github.io/pyright/"><img src="https://microsoft.github.io/pyright/img/pyright_badge.svg" alt="Checked with pyright"></a>
</div>

## Links

- **Website**: [https://reaktiv.bui.app/](https://reaktiv.bui.app/)
- **Live Playground**: [https://reaktiv.bui.app/#playground](https://reaktiv.bui.app/#playground)
- **Deep Dive Article**: [https://bui.app/the-missing-manual-for-signals-state-management-for-python-developers/](https://bui.app/the-missing-manual-for-signals-state-management-for-python-developers/)
- **GitHub**: [https://github.com/buiapp/reaktiv](https://github.com/buiapp/reaktiv)

## What is reaktiv?

reaktiv is a reactive declarative state management library for Python that lets you declare relationships between your data instead of manually wiring updates. When data changes, everything that depends on it updates automatically — eliminating a whole class of bugs where you forget to update dependent state.

Think of it as a spreadsheet for your Python application: change a cell, and all formulas using that cell recalculate instantly.

## Why Use reaktiv?

reaktiv solves common pain points in state management:

- **Eliminates manual state synchronization** - No more forgetting to update derived values
- **Reduces bugs** - Ensures consistent state throughout your application
- **Simplifies code** - Declare relationships once, not every time data changes
- **Improves performance** - Only recomputes what actually needs to change

[Learn more about why you should use reaktiv →](why-reaktiv.md)

## Features

* **Automatic state propagation:** Change a value once, and all dependent computations update automatically
* **Efficient updates:** Only the necessary parts are recomputed (fine‑grained reactivity)
* **Zero external dependencies:** Lightweight and easy to incorporate into any project
* **Type-safe:** Fully annotated for clarity and maintainability
* **Lazy and memoized:** Computations run only when needed and cache until dependencies change

## Quick Start

reaktiv is built around core primitives for reactive programming:

1. **Signals**: Store values and notify dependents when they change
2. **Computed Signals**: Derive values that automatically update when dependencies change
3. **Effects**: Run side effects when signals or computed signals change

```python
from reaktiv import Signal, Computed, Effect

# Reactive data sources
name = Signal("Alice")
age = Signal(30)

# Reactive derived value
greeting = Computed(lambda: f"Hello, {name()}! You are {age()} years old.")

# Reactive side effect (retain a reference!)
greeting_effect = Effect(lambda: print(f"Updated: {greeting()}"))

# Update base data — everything reacts automatically
name.set("Bob")   # Prints: Updated: Hello, Bob! You are 30 years old.
age.set(31)       # Prints: Updated: Hello, Bob! You are 31 years old.
```

## Documentation

* [Installation](./installation.md) - How to install the library
* [Quick Start](./quickstart.md) - Get up and running quickly
* [Why reaktiv?](./why-reaktiv.md) - When and why to use reaktiv
* [Core Concepts](./core-concepts.md) - Understanding the fundamentals
* [API Reference](./api/signal.md) - Detailed API documentation
  * [Signal](./api/signal.md) - Writable reactive values
  * [Computed](./api/compute-signal.md) - Derived reactive values
  * [Effect](./api/effect.md) - Reactive side effects
  * [LinkedSignal](./api/linked-signal.md) - Writable derived signal with auto-reset

* [Advanced Features](./advanced-features.md) - More powerful capabilities
* [Real-World Examples](./examples/index.md) - Practical applications