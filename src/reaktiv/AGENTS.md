# reaktiv: guide for coding agents

Instructions for writing application code with reaktiv. This guide ships with
the package and describes this installed version; its examples run in
reaktiv's test suite. Follow it over patterns from other signal libraries or
older reaktiv versions.

## Mental model

State is a graph. **Signals** hold values you write. **Computed** values are
pure functions of other signals: lazy, cached, recomputed only when a
dependency changed. **Effects** are the edge of the graph, where changes leave
it as side effects. Dependencies are tracked automatically: whatever a
computed or effect *reads* while running becomes a dependency, and the set is
rebuilt on every run.

Write code that **declares relationships**, not code that pushes updates
around. If a value can be derived, derive it with `computed`; never copy
it into another signal and keep it in sync by hand. Think of a spreadsheet:
signals are input cells, computed values are formulas, effects are what you
do with the results.

### Push, then pull

A write runs in two phases:

1. **Push (notify).** `set()` stores the value and marks everything downstream
   as *possibly stale*. Nothing is recomputed yet; effects are only queued.
2. **Pull (recompute on read).** When an effect runs or anyone reads a
   computed, it checks whether its sources really changed and recomputes only
   then, sources first.

Consequences to rely on:

- **Lazy:** a computed nobody reads never runs, however often its inputs
  change. Several writes before the next read cost one recomputation.
- **Glitch-free:** in a diamond (`b` and `c` both derived from `a`, an effect
  reading all three) the effect runs once and sees consistent values, never a
  mix of old and new.
- **Equality cut-off:** if a computed recomputes to an *equal* value, its
  dependents are not rerun. The default comparison is identity (`is`), which
  only catches the same object (and, by accident, small cached ints). For a
  filter in front of expensive work, compare values explicitly:
  `computed(lambda: len(items()), equal=lambda a, b: a == b)`.
- **Effects run after the push**, once per change (or once per outermost
  `batch()`), usually on the thread that wrote (see "Threads and async").

## Choose the primitive

| Need | Use |
|---|---|
| State you write | `signal(value)`, or `field(value)` on a `ReactiveModel` |
| A value derived from other state | `computed(fn)` |
| Derived state the user can override until the source changes | `linked(fn)` |
| A side effect when state changes (I/O, logging, UI) | `effect(fn)` |
| Async loading driven by state, with status and cancellation | `resource(params=..., loader=...)` |
| Consume changes in `async for` | `to_async_iter(sig)` |
| A framework that schedules its own work | `reaktiv.subtle.Watcher` (not for app code) |

Use the lowercase factories (`signal`, `computed`, `linked`, `effect`,
`resource`, `field`). Uppercase names (`Signal`, `ComputeSignal`, ...) are for
type annotations; annotate parameters with `ReadableSignal[T]` or
`WritableSignal[T]` from `reaktiv`.

## Core example

```python
from reaktiv import batch, computed, effect, signal

price = signal(10.0)
quantity = signal(2)
total = computed(lambda: price() * quantity())  # derived, not stored

log = []
logger = effect(lambda: log.append(total()))  # keep the reference!

with batch():  # several writes, one effect run
    price.set(12.0)
    quantity.update(lambda q: q + 1)

assert total() == 36.0
assert log == [20.0, 36.0]
logger.dispose()
```

## Rules

1. **Read by calling**: `count()`. Write with `count.set(v)` or
   `count.update(lambda v: v + 1)`. Only `signal`, `field` and `linked` are
   writable; computed signals have no `set`/`update`.
2. **Keep computations pure.** No I/O, no writes, no mutation inside
   `computed` or `linked` functions. Writing a signal there raises
   `RuntimeError`. Put side effects in effects. (An explicit `untracked()`
   block lifts the check, as in Angular, for rare cases such as initializing
   a signal lazily on first read; do not use it to hide side effects.)
3. **Keep every effect referenced** (variable, attribute, or model member) and
   `dispose()` it when done. Signals hold effects weakly: an unreferenced
   effect is garbage collected and silently stops running. Effects declared
   with `@effect` on a `ReactiveModel` are retained by the model.
4. **Replace values, do not mutate them.** Default equality is identity
   (`is`): mutating a list in place and setting the same object notifies
   nobody. Write new objects: `items.update(lambda xs: [*xs, item])`.
5. **Equality is "same value, keep the old one".** Pass `equal=` for value
   comparison: `signal([], equal=lambda a, b: a == b)`. When `equal` returns
   `True`, the previous value is kept and nobody is notified, for signals,
   computed and linked alike.
6. **Read reactive inputs first, then act** (see "Effects: read, then act").
   Tracking is dynamic: a signal read only in a branch that was not taken is
   not a dependency until that branch runs, which is correct. What breaks
   effects is a read that never happens because the code raised or returned
   before it, or a hidden read inside a helper the effect calls.
7. **Use `untracked` to read without subscribing**:
   `untracked(other)` or `with untracked(): ...`.
8. **Use `batch()` to group writes** so effects run once with the final
   values. It is not a transaction: writes apply immediately and are not
   rolled back if the block raises.
9. **Avoid effects that write their own inputs.** An effect that writes a
   signal it read runs again. For synchronous effects, a loop that keeps
   changing its inputs raises `RuntimeError` after 100 runs within one
   flush; an async effect doing the same is not bounded and keeps
   rescheduling itself. Prefer `computed` or `linked`.
10. **Errors propagate through reads.** A failing computed raises on read and
    keeps raising the same error, without rerunning, until a dependency
    changes. An exception inside an effect is printed, not raised.

## Effects: read, then act

Structure every effect in two parts. First read all the signals it reacts to
(that is the tracking phase). Then perform the side effect without tracking,
so helpers and callbacks it calls cannot subscribe the effect to signals by
accident. Keep decisions in `computed` values so the effect only acts.

```python
from reaktiv import computed, effect, signal, untracked

user = signal("ada")
theme = signal("dark")
log_level = signal("info")  # read by the logging helper below
sent = []

def send(message: str) -> None:  # a helper that happens to read a signal
    sent.append(f"[{log_level()}] {message}")

greeting = computed(lambda: f"hi {user()} ({theme()})")  # decide in computed

def notify_user():
    message = greeting()  # 1. read: the only dependency
    with untracked():     # 2. act: reads in here do not subscribe
        send(message)

notifier = effect(notify_user)
log_level.set("debug")  # not a dependency: no rerun
user.set("grace")       # reruns once
assert sent == ["[info] hi ada (dark)", "[debug] hi grace (dark)"]
notifier.dispose()
```

- One effect per side-effect concern; split an effect that does unrelated
  things, so each reruns only for its own inputs.
- Return a cleanup callable (or accept an `on_cleanup` parameter) for
  subscriptions, timers and handles; it runs before the next run and on
  `dispose()`.
- Do not use an effect to compute a value for other code. If something should
  read it, it is a `computed`.

## Designing state

- **Store the minimum, derive the rest.** Keep only source-of-truth values
  in signals; `total`, `is_valid`, `visible_items` are `computed`.
- **Make signals granular.** One signal per independently changing value
  (`first_name`, `last_name`), not one dict for a whole form, so a change
  reruns only what reads it. Group with a `ReactiveModel`, not a big value.
- **Prefer immutable values** (tuples, frozen dataclasses), so replacing is
  natural and default identity equality is cheap and correct.
- **Expose read-only views** of internal state with `sig.as_readonly()`, and
  change state through methods that write (with `batch()` for several
  writes).
- **Test through values**: write signals, then assert on computed values;
  dispose effects and models at the end of each test.

## Patterns

Group related state in a model. Members are created per instance; `@effect`
members start when the model is created; `dispose()` stops everything, for
good: anything registered with `model.own(obj)` afterwards is disposed at
once. Do not copy models (`copy.copy` shares their signals); construct a new
one from the values.

```python
from reaktiv import ReactiveModel, computed, effect, field, linked

class Cart(ReactiveModel):
    items = field[tuple[str, ...]]((), equal=lambda a, b: a == b)  # immutable
    page_size = field(10)

    @computed
    def count(self) -> int:
        return len(self.items())

    @linked
    def page(self) -> int:  # user-selectable; resets to 1 when items change
        return 1 if self.items() else 0

    @effect
    def report(self):
        print(f"{self.count()} items")
        return lambda: None  # optional cleanup, runs before the next run

cart = Cart()  # prints "0 items" (model effects start immediately)
cart.items.update(lambda xs: (*xs, "apple"))  # prints "1 items"
cart.page.set(3)
cart.items.update(lambda xs: (*xs, "pear"))  # prints "2 items"
assert (cart.count(), cart.page()) == (2, 1)
cart.dispose()
```

Derived state that the user may override, but which should keep or adapt the
override when the source changes, uses `linked` with a computation. `previous`
is `None` on the first run; `previous.source` has the source's type and
`previous.value` the linked value's type:

```python
from typing import Optional
from reaktiv import PreviousState, linked, signal

options = signal(["s", "m", "l"])

def keep_valid(opts: list[str], previous: Optional[PreviousState[list[str], str]]) -> str:
    if previous is not None and previous.value in opts:
        return previous.value  # keep the user's choice while it is still valid
    return opts[0]

size = linked(source=options, computation=keep_valid)
size.set("l")
options.set(["m", "l", "xl"])
assert size() == "l"
options.set(["xs"])
assert size() == "xs"
```

Load async data from reactive parameters with `resource`. Create it while an
event loop is running. Returning `None` from `params` means "nothing to
load" (status `IDLE`). A parameter change cancels the previous load.

```python
import asyncio
from reaktiv import ResourceStatus, resource, signal

async def main() -> None:
    user_id = signal(1)

    async def load_user(request):
        await asyncio.sleep(0.01)
        if request.cancellation.is_set():  # superseded by a newer request
            return None
        return {"id": request.params, "name": f"user {request.params}"}

    user = resource(params=lambda: user_id(), loader=load_user)
    await asyncio.sleep(0.05)
    current = user.value()  # raises while status is ERROR; None until loaded
    if current is not None:
        assert current["id"] == 1
    user_id.set(2)  # status LOADING, then RESOLVED
    await asyncio.sleep(0.05)
    assert user.status() == ResourceStatus.RESOLVED
    user.dispose()

asyncio.run(main())
```

Read a resource with `status()`, `value()`, `error()`, `is_loading()`,
`has_value()`, or one consistent record with `snapshot()()` (immutable).
`value()` is typed `Optional`: check it for `None` (type checkers do not
narrow it after `has_value()`). A loaded value of `None` counts as "no value". Use `reload()` to refetch,
`set()` for a local value, `cancel()` to stop the current load, and `dispose()`
to stop the resource.

## Threads and async

- Thread safety is on by default; signals can be read and written from any
  thread. An effect runs on the thread that first schedules it: usually the
  writing thread, but an effect already waiting in another thread's
  `batch()` runs there, once, when that batch ends.
- Async effects and resources belong to the event loop they were created on;
  changes from other threads are handed to that loop. Call a resource's own
  methods (`set`, `reload`, `cancel`, `dispose`) on its loop.
- Prefer `resource` or a sync effect that starts a task over `async def`
  effects, which are experimental.

## Avoid

- Copying derived values into signals from effects (`total.set(a() + b())`):
  use `computed`.
- Calling `effect(...)` without keeping the result.
- Reading a signal without calling it (`if flag:` is always true; write
  `if flag():`).
- Mutating containers stored in signals.
- Using `subtle.Watcher`, `current_consumer` or `signal_version` in
  application code; they exist for framework integrations.
