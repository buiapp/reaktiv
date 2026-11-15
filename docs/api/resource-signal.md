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

### Value equality

`resource(params=..., loader=..., equal=comparator)` accepts a two-argument comparator for loaded and manually set values. Returning
True retains the previous value and suppresses value updates; omitting the callback
keeps identity comparison. `resource[Params, Value](params, equal=comparator)`
also configures the descriptor. Loading/error status, cancellation, and request
parameter comparison are independent of value equality.

### Cancellation

`resource.cancel()` returns whether a load was running. It sets the loader's
cancellation event, cancels its asyncio task, and sets `status()` to
`ResourceStatus.CANCELLED` while retaining any previous value. A cancelled loader
cannot publish a late result. Dependencies remain active; changing parameters or
calling `reload()` starts a new load. Call cancellation on the resource's event
loop. Async cleanup can run in `finally`; blocking work in native code or a
separate thread still needs its own cancellation mechanism.

### Disposal

`resource.dispose()` stops a resource permanently: it cancels a running load
(whose result is never published), stops reacting to parameter changes, and
makes `reload()` a no-op. The last value, error and status stay readable.
Disposal is idempotent. `destroy()` is a compatibility alias of `dispose()`.
