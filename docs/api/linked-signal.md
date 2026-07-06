# `linked` API

Use `linked(...)` or `@linked` for writable derived state: a value can be
overridden manually, then reset when its source context changes.

```pyodide install="reaktiv" height="18" theme="github,one_dark"
from reaktiv import linked, signal

page = signal(1)

@linked
def selection():
    return f"default-for-page-{page()}"

selection.set("custom-choice")
print(selection())  # custom-choice

page.set(2)
print(selection())  # default-for-page-2
```

!!! note "Naming"

    Prefer `linked(...)` and `@linked` in application code. `LinkedSignal` is
    the concrete writable-derived signal class. `Linked` remains available as a
    compatibility alias.

::: reaktiv.linked
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true

::: reaktiv.LinkedSignal
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      show_bases: false
      members_order: source

::: reaktiv.PreviousState
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      show_bases: false
