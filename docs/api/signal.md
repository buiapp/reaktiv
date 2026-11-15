# `signal` API

Use `signal(...)` to create writable reactive state in new code:

```pyodide install="reaktiv" height="12" theme="github,one_dark"
from reaktiv import signal

count = signal(0)
count.update(lambda value: value + 1)

print(count())  # 1
```

!!! note "Naming"

    Prefer `signal(...)` in application code. `Signal` is the concrete writable
    signal class and remains supported for existing class-style code, type
    references, and advanced use.

::: reaktiv.signal
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true

::: reaktiv.Signal
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      show_bases: false
      inherited_members: true
      members_order: source
      group_by_category: false

::: reaktiv.ReadonlySignal
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      show_bases: false
