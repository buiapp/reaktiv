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

## Change One Value. Let The Graph Handle The Rest.

A form field changes. Validation, normalized values, totals, availability, and
the UI must follow. A query changes. Results, loading state, selection, and
background work must stay consistent.

Without a reactive graph, every mutation needs to remember what else to update.
With reaktiv, each value declares what it depends on:

```python
query = Signal("")
results = Computed(lambda: search(query()))
summary = Computed(lambda: f"{len(results())} matches")
display = Effect(lambda: render(summary(), results()))

query.set("python")
```

reaktiv tracks the relationships, invalidates the affected graph, recomputes
derived values lazily, and runs the relevant effects.

## Try It In Your Browser

Edit the code and press **Run**. The example runs entirely in your browser with
Pyodide.

```pyodide install="reaktiv" height="22" theme="github_light_default,github_dark"
from reaktiv import Computed, Effect, Signal

unit_price = Signal(12.50)
quantity = Signal(1)

total = Computed(lambda: unit_price() * quantity())
receipt = Effect(
    lambda: print(f"{quantity()} item(s): ${total():.2f}")
)

quantity.set(3)
unit_price.set(10.00)

receipt.dispose()
```

The first run downloads Pyodide and installs `reaktiv`; later runs are cached by
the browser.

## Three Building Blocks

1. **`Signal` stores changing state.**
   Read it by calling it and update it with `set()` or `update()`.
2. **`Computed` describes derived state.**
   Dependencies are discovered automatically; results are lazy and cached.
3. **`Effect` reacts to changes.**
   It reruns when a signal or computed value read by the effect changes.

That small vocabulary scales from a total in a form to branching dependency
graphs, async resources, and independently updating threaded workloads.

## Why reaktiv?

- **Relationships stay next to the values they define.** You do not have to
  trace every setter and callback to understand what updates what.
- **Derived state stays current.** Dependencies are tracked automatically.
- **Updates stay focused.** Only affected parts of the graph are invalidated.
- **Computations are lazy and memoized.** Work happens when a value is needed.
- **Lifetimes are explicit.** Effects and resources can be disposed cleanly.
- **Thread safety is enabled by default.** Independent graphs do not share a
  global execution lock.

[See when a reactive graph helps](why-reaktiv.md)

## Organize Application State With ReactiveModel

After learning the primitives, use `ReactiveModel` to keep a related graph and
its lifecycle in one object:

```pyodide install="reaktiv" assets="no" height="28" theme="github_light_default,github_dark"
from reaktiv import ReactiveModel, computed, effect, field


class ShoppingCart(ReactiveModel):
    unit_price = field(12.50)
    quantity = field(1)
    discount = field(0.0)

    @computed
    def total(self):
        return self.unit_price() * self.quantity() * (1 - self.discount())

    @effect
    def show_total(self):
        print(f"{self.quantity()} item(s): ${self.total():.2f}")


cart = ShoppingCart()
cart.quantity.set(3)
cart.discount.set(0.10)
cart.dispose()
```

Every model instance owns independent fields, computed values, effects, linked
state, and resources. Model-owned work is retained automatically and cleaned up
by `dispose()`.

[Explore ReactiveModel](api/reactive-model.md)

## Where To Go Next

- **New to signals?** Start with the [Quick Start](quickstart.md).
- **Want the mental model?** Read [Core Concepts](core-concepts.md).
- **Building application state?** See
  [ReactiveModel](api/reactive-model.md).
- **Working with async data?** Read the [Resource Guide](resource-guide.md).
- **Looking for complete programs?** Browse the [Examples](examples/index.md).
- **Need a class or method?** Open the [API Reference](api/signal.md).

## Project Links

- [Installation](installation.md)
- [GitHub](https://github.com/buiapp/reaktiv)
- [PyPI](https://pypi.org/project/reaktiv/)
- [Live playground](https://reaktiv.bui.app/#playground)
- [Deep dive article](https://bui.app/the-missing-manual-for-signals-state-management-for-python-developers/)
