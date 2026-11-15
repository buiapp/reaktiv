# subtle: primitives for framework authors

`reaktiv.subtle` contains low-level building blocks modelled on the TC39
`Signal.subtle` namespace. Application code should use `effect`; reach for these
when you integrate reaktiv into a framework, UI loop or host that owns scheduling.

## Custom scheduling with `Watcher`

`effect` runs synchronously when the outermost `batch` ends. A `Watcher` lets you
choose when work runs instead. It is notified when a watched signal *may* have
changed, before anything is recomputed, and you evaluate on your own schedule:

```python
import asyncio
from reaktiv import computed, signal
from reaktiv.subtle import Watcher

async def main() -> None:
    count = signal(1)
    label = computed(lambda: f"count={count()}")
    loop = asyncio.get_running_loop()

    def flush() -> None:
        watcher.watch()    # re-arm first (see below)
        for node in watcher.get_pending():
            print(node())  # evaluate, then commit side effects here

    watcher = Watcher(lambda: loop.call_soon(flush))
    watcher.watch(label)
    flush()                # prints "count=1"
    count.set(2)           # notify only; nothing is recomputed yet
    await asyncio.sleep(0) # flush runs on the next tick: prints "count=2"

asyncio.run(main())
```

Rules:

- `notify` runs synchronously during propagation, also inside `batch`, and at
  most once until `watch()` re-arms the watcher. Reading or writing any signal
  in `notify` raises, also through `untracked`, and a rejected read evaluates
  nothing. Work that `notify` schedules (`call_soon`, `create_task`, a queue)
  runs later and can read and write normally.
- **Re-arm at the start of your flush**, before reading pending nodes. If
  committing a result changes a watched dependency, the armed watcher notifies
  again and the next flush picks up the new value. Re-arming at the end would
  suppress that notification and leave work pending with no flush scheduled.
  A commit that always changes its own inputs therefore reschedules forever,
  one flush at a time.
- `watch(*nodes)` and `unwatch(*nodes)` never evaluate. Watching a computed keeps
  it subscribed to its sources; unwatching releases that subscription.
- `get_pending()` returns watched computed nodes that need evaluation, as the
  same handles you passed in (read-only wrappers stay read-only). Plain signals
  notify but are never pending.
- Computations cannot write signals. Put side effects in your flush, after
  reading the pending nodes.
- Like effects, a watcher is referenced weakly by its sources. Keep a reference
  for as long as it should observe, then call `dispose()` (or register it with
  `model.own`). After disposal `notify` never runs and `watch()` does nothing,
  so a flush scheduled before disposal can still re-arm safely.

## Differences from TC39 `Signal.subtle`

`Watcher` follows the TC39 proposal's contract ("may have changed", no reads or
writes during `notify`, re-arm with `watch()`), with these deliberate differences:

- **Weak retention.** Sources reference a watcher weakly, as they do effects.
  A watcher you don't keep a reference to is garbage collected and stops
  observing. In TC39, watched signals keep their watcher alive.
- **Exceptions in `notify` are printed, not raised.** The change keeps reaching
  the remaining effects and watchers, so one faulty callback cannot leave the
  graph half-notified.
- **`dispose()`** stops a watcher permanently; TC39 has only `unwatch`.
- **No graph introspection.** There is no `introspectSources`/`introspectSinks`
  and no `watched`/`unwatched` callbacks. `current_consumer()` and
  `signal_version()` are not a substitute for dependency inspection; public
  graph traversal for tooling is a separate API decision.

## Read tracking and change detection

- `current_consumer()` returns the computation or effect currently tracking
  reads, or `None` (also inside `untracked` and during `notify`). Treat it as an
  opaque identity.
- `signal_version(node)` returns a node's revision without reading, evaluating
  or tracking it. It advances when the node publishes a new value or error, is
  local to that node, and a stale computed keeps its old revision until read.

## Owning extension objects

`model.own(value)` registers an object with a `ReactiveModel` and returns it.
The object must implement `dispose()` or `destroy()`; otherwise `TypeError` is
raised. `model.dispose()` cleans up owned objects in reverse registration order,
once each.

::: reaktiv.subtle.Watcher
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
      members_order: source

::: reaktiv.subtle.current_consumer
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true

::: reaktiv.subtle.signal_version
    options:
      show_source: false
      heading_level: 2
      show_root_heading: true
