# `resource` API

Use `resource(...)` or `@resource` to connect asynchronous loading to a reactive
parameter graph. Resources expose synchronous signal-like accessors for status,
value, error, loading state, and snapshots.

!!! note "Naming"

    Prefer `resource(...)` and `@resource` in application code. `Resource` is
    the concrete async resource class and remains supported for existing
    class-style code, type references, and advanced use.

::: reaktiv.resource
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true

::: reaktiv.Resource
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      show_bases: false
      members_order: source

::: reaktiv.ResourceStatus
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      show_bases: false

::: reaktiv.ResourceLoaderParams
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      show_bases: false

::: reaktiv.ResourceSnapshot
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      show_bases: false
