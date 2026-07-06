# `computed` API

Use `computed(...)` or `@computed` to create reactive derived values. Computed
signals derive from other signals, recompute lazily, and cache their latest
value until a dependency changes.

!!! note "Naming"

    Prefer `computed(...)` and `@computed` in application code. `Computed`
    remains supported for existing uppercase constructor/decorator-style code.
    `ComputeSignal` is the concrete readable signal type returned by the
    factory.

## Create Derived State

Create a computed signal from a callable:

```pyodide install="reaktiv" height="12" theme="github,one_dark"
from reaktiv import computed, signal

price = signal(10)
quantity = signal(2)

@computed
def total():
    return price() * quantity()

print(total())  # 20
```


Use typed decorator syntax when you want to state the result type explicitly:

```pyodide install="reaktiv" assets="no" height="12" theme="github,one_dark"
from reaktiv import computed, signal

name = signal("Ada")

@computed[str]
def normalized_name():
    return name().strip().lower()

print(normalized_name())  # ada
```

Custom equality can suppress downstream updates when two computed values should
be treated as equivalent:

```pyodide install="reaktiv" assets="no" height="14" theme="github,one_dark"
from reaktiv import computed, signal

temperature = signal(21.04)

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
