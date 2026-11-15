# Changelog

## 0.25.0 (2026-11-15)

Changes since 0.24.2.

### Added

- **`reaktiv.subtle`**: low-level primitives for framework authors, modelled on
  the TC39 `Signal.subtle` namespace.
  - `Watcher(notify)`, with `watch()`, `unwatch()`, `get_pending()` and
    `dispose()`, tells you when watched signals may have changed without
    evaluating anything, so you can run work on your own schedule. Reading or
    writing signals inside `notify` raises, also through `untracked`. See
    `docs/api/subtle.md` for the scheduling recipe and the deliberate
    differences from TC39.
  - `current_consumer()` returns the computation or effect currently
    tracking reads.
  - `signal_version(node)` returns a node's revision without reading it.
- **`equal=` for model fields and resources**: `field(default, equal=...)`,
  `field(factory=..., equal=...)`, `resource(params=..., loader=..., equal=...)`
  and `resource[Params, Value](params, equal=...)`. Returning `True` keeps the
  previous value and skips notifications.
- **`resource.cancel()`**: cancels the running load, keeps the previous value,
  and sets the new status `ResourceStatus.CANCELLED`. Returns whether a load was
  running.
- **`resource.dispose()`**: stops a resource permanently. It cancels a running
  load, stops reacting to parameter changes and makes `reload()` a no-op.
- **`@linked(computation=...)` decorator**: the decorated function is the source.
  On a `ReactiveModel` method the computation receives the owner first:
  `computation(self, source, previous)`.
- **Guide for coding agents**: `reaktiv/AGENTS.md` ships in the package (so it
  matches the installed version) and is published in the docs, with an
  `llms.txt` index. It covers the mental model, which primitive to use, rules
  and pitfalls; its examples run in the test suite and type-check with
  pyright and mypy.
- **`py.typed`**: the package is marked as typed, so mypy and other checkers
  use reaktiv's annotations instead of treating it as untyped. The public API
  is fully annotated (`pyright --verifytypes`: 100%).
- **`ReactiveModel.own(obj)`**: registers an object with `dispose()` or
  `destroy()` so that `model.dispose()` cleans it up (in reverse registration
  order, once each). It returns `obj`. On a disposed model the object is
  disposed immediately, and so are members first accessed after
  `model.dispose()`, so nothing registered late waits for a cleanup that never
  comes.

### Changed

These may require changes when upgrading:

- **Computed and linked signals keep their previous value when `equal()`
  returns `True`**, as signals already did and as Angular and SolidJS do. Before,
  they stored the new value without notifying, so a fresh read and a dependent
  computation could disagree, and a tolerance compared against the latest value
  could drift without ever notifying. Equality is now always checked against the
  last published value.
- **Computed and linked signals memoize errors**, as Angular and Preact do. A
  failing computation runs once; later reads re-raise the same exception
  without recomputing until a dependency changes. Before, it reran on every
  read.
- **An `equal()` function that raises is no longer ignored.** `set()` and
  `update()` raise and keep the old value. In a computed or linked signal the
  exception becomes the node's error, raised on read. When a resource publishes a
  loaded value, it becomes the resource's error (status `ERROR`). Before, the
  exception was logged and the values were treated as different.
- **Linked writes apply pending source changes first**, as Angular's
  `linkedSignal` does. `update()` receives the up-to-date value (before, `None`
  before the first read and a stale value after a source change), and a value
  written with `set()` is no longer replaced by the next read. `set()` also
  replaces an error state, and `update()` raises it.
- **Async effects must be created inside a running event loop** and raise
  `RuntimeError` otherwise, like resources. Before, such an effect never ran
  and was silently stuck.
- **Writes made by an async effect are no longer batched until it finishes.**
  They notify immediately, like writes outside an effect.
- **`model.dispose()` attempts every cleanup even if one raises**, then raises
  the first exception (further ones are printed). Before, it stopped at the
  first failure and kept the remaining objects registered.
- **Computed signals are no longer `Signal` subclasses.** `Signal` (and
  `LinkedSignal`) are writable; `ComputeSignal` derives from a shared internal
  base and has no `set()` or `update()` at all, so type checkers reject a
  computed where `WritableSignal` is required, and calling either method raises
  `AttributeError`. Before, `computed.update()` was inherited and replaced the
  computed value.
  - `isinstance(x, Signal)` is now `False` for computed and linked signals.
    Check `isinstance(x, (Signal, ComputeSignal))` for "any signal node", or
    annotate with `ReadableSignal[T]` / `WritableSignal[T]`.
  - `linked(source=...)` accepts any `ReadableSignal`, including computed and
    read-only signals, for type checkers too.
- **An effect that writes a signal it read runs again** once its current run
  ends, as in Preact. Before, synchronous effects dropped that change and never
  saw the new value. A synchronous effect that keeps changing its own inputs
  raises `RuntimeError` after 100 iterations of one flush, also when another
  effect started the loop (that error used to be swallowed); effects queued at
  that point stay runnable. Async effects are not bounded this way.
- **Model members live in the instance `__dict__`** (see Fixed). `copy.copy()`
  of a model now shares its signals with the original, and `copy.deepcopy()`
  and `pickle` raise `TypeError`. Before, both "succeeded" by silently
  dropping all reactive state (the copy got fresh default values).
- **`PreviousState[S, T]` has separate source and value types**, as in
  Angular's `linkedSignal<S, D>`: `previous.source` is the source type `S` and
  `previous.value` the linked value type `T`. Before, both used one type, so
  `previous.source` was typed as the value. `PreviousState[X]` still works and
  means both are `X`; annotations whose source and value types differ now need
  two arguments. `linked(source=..., computation=...)` and
  `@linked(computation=...)` infer `S` from the source.
- **The computation of `linked(source=..., computation=...)` cannot write
  signals.** It runs without tracking reads, which used to switch off the write
  check, so it could write. An explicit `untracked()` block inside a computed
  still may write, as in Angular (for example to initialize a signal lazily).
- **`ResourceSnapshot` is frozen.** Assigning to a snapshot's fields raises
  `FrozenInstanceError`. Before, a snapshot was a shared cached object, so one
  reader's assignment changed what every later reader saw.
- **`resource.reload()`, `cancel()` and `dispose()` raise `RuntimeError`
  inside a computed or a `Watcher` notification**, like `set()`. The check runs
  before any state change.
- **`computed[T](...)` and `linked[T](...)` type-check their callback.** The
  function must return `T` (for methods, `(self) -> T`); before, any return
  type was accepted and cast, so `computed[int](lambda: "text")` passed
  Pyright. `linked[T](computation=...)` is unchanged: there the decorated
  function is the source.
- **`ResourceStatus` has a new member, `CANCELLED`.** Code that matches every
  status needs a case for it.
- **`Signal.update()` and linked signals' `set()`/`update()` inside a computed
  now raise `RuntimeError`**, the same as `Signal.set()` always has. Before,
  they skipped this check.
- **Linked signals pass `previous` whenever there was a previous run.** A
  previous value of `None` used to be treated as "no previous state";
  computations now receive `PreviousState(value=None, ...)`.
- **`linked(computation=...)` without a source returns a decorator** instead of
  raising `ValueError`, like `linked(equal=...)` already did.
- **`resource.destroy()` is now an alias of `dispose()`.** It also stops
  parameter tracking and cancels the running load's task; before, it only
  signalled cancellation to the loader.
- `reaktiv` requires `typing-extensions>=4.11` on Python below 3.13 (for the
  `PreviousState` type parameter default), and the package now includes the
  `LICENSE` file.

### Fixed

- A destroyed resource no longer starts new loads when its parameters change.
- When a computed's direct dependency is known to have changed, it no longer
  re-evaluates other dependencies that the new run may not read, for example a
  replaced implementation behind a stable slot.
- `model.dispose()` disposes every registered object, even when two of them
  compare equal with `==`.
- Distinct model instances that compare equal no longer share fields, computed
  values, linked signals, effects or resources.
- A suspended async effect no longer delays every other effect on its thread
  until it finishes. Disposing a running async effect cancels it immediately
  (from another thread, the cancellation runs on the effect's event loop), a
  dependency change during an async run triggers a rerun, and cancellation
  runs each cleanup once.
- Resource transitions (loading, resolved, error, local) are published at
  once, so observers never see a mix such as `resolved` while still loading.
- A resource write rejected inside a computed no longer cancels the running
  load. `resource.update()` no longer subscribes the caller to the resource.
- An async effect or resource load triggered by a write on another thread runs
  on the event loop the effect or resource was created on, and cancelling the
  superseded load happens there too. A change queued from another thread is
  dropped if a newer change, `set()`, `reload()` or `cancel()` came first. Before, the effect was stuck permanently,
  and the resource stayed `loading` or failed to start the new load.
- A rejected `resource.dispose()` no longer leaves the resource marked
  disposed with its load still running, so it can be retried.
- After `resource.reload()`, the next parameter change reports `LOADING`
  instead of `RELOADING`, and the watcher no longer treats unchanged
  parameters as a reload request.
- A resource whose `LOADING` observer disposes or cancels it, or writes a local
  value, no longer starts the loader anyway.
- `to_async_iter()` delivers values written on another thread on the
  iterator's event loop, in write order. Before, such a write could leave a
  waiting consumer suspended forever. Its docstring now states that values are
  buffered without a bound.
- `resource.value` returns the same signal on every access.
- Concurrent `update()` calls on a linked signal from several threads no longer
  lose writes: refreshing, calling the updater and writing are one atomic
  operation, as in `signal.update()`.
- A model is garbage collected even when its own reactive members reference
  it, for example a computed returning `self` or an effect cleanup closing over
  it. Fields, computed and linked signals, effects and resources are now stored
  in the instance `__dict__` (like `functools.cached_property`); only instances
  without a `__dict__` use a weak identity map, which cannot release such cycles.
- A subclass that overrides an eager model member (such as an `@effect`) no
  longer also runs the base class's member.
