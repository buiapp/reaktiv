# Computed Signal API

`Computed` and `computed` create computed signals: reactive values that derive
from other signals, recompute lazily, and cache their latest value until a
dependency changes.

`Computed` is kept as the uppercase constructor-style API. `computed` is the
preferred lowercase decorator/factory spelling for new code, especially inside
`ReactiveModel` classes.

## Computed / computed Factory

Create a computed signal from a callable:

```pyodide install="reaktiv" height="12" theme="github_light_default,github_dark"
from reaktiv import Computed, Signal

price = Signal(10)
quantity = Signal(2)

total = Computed(lambda: price() * quantity())

print(total())  # 20
```

Use lowercase decorator syntax for new code:

```pyodide install="reaktiv" assets="no" height="14" theme="github_light_default,github_dark"
from reaktiv import Signal, computed

price = Signal(10)
quantity = Signal(2)

@computed
def total() -> int:
    return price() * quantity()

print(total())  # 20
```

When omitting a return annotation, use typed decorator syntax so type checkers
can preserve the returned signal type:

```pyodide install="reaktiv" assets="no" height="12" theme="github_light_default,github_dark"
from reaktiv import Signal, computed

name = Signal("Ada")

@computed[str]
def normalized_name():
    return name().strip().lower()

print(normalized_name())  # ada
```

Custom equality can suppress downstream updates when two computed values should
be treated as equivalent:

```pyodide install="reaktiv" assets="no" height="14" theme="github_light_default,github_dark"
from reaktiv import Signal, computed

temperature = Signal(21.04)

@computed[float](equal=lambda left, right: round(left, 1) == round(right, 1))
def rounded_temperature():
    return temperature()

print(rounded_temperature())
temperature.set(21.05)
print(rounded_temperature())
```

::: reaktiv.ComputeSignal
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      show_bases: false
      members_order: source
