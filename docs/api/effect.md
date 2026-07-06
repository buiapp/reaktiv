# `effect` API

Use `effect(...)` or `@effect` to run side effects when the signals read by the
effect change:

```pyodide install="reaktiv" height="16" theme="github,one_dark"
from reaktiv import effect, signal

count = signal(0)

def print_count():
    print(f"count={count()}")

runner = effect(print_count)
count.set(1)
runner.dispose()
```

!!! note "Naming"

    Prefer `effect(...)` and `@effect` in application code. `Effect` is the
    concrete disposable effect class and remains supported for existing
    class-style code, type references, and advanced use.

::: reaktiv.effect
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true

::: reaktiv.Effect
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      show_bases: false
      members_order: source
