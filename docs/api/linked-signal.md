# LinkedSignal

`LinkedSignal` is a writable, derived signal that automatically resets to a computed value whenever its source dependencies change, while still allowing manual overrides in between.

Use it when you want a value that normally follows from other signals, but can be manually set by the user or system. When the source data changes, the linked value resets based on your computation.

## Key properties

- Writable: you can call `set()` or `update()` to override the value
- Auto-reset: when the source changes, it recomputes and overwrites manual overrides
- Previous state awareness: your computation receives the previous linked value and previous source value
- Works with effects and other computed values
- Can be disposed when no longer needed

## Initialization patterns

LinkedSignal supports two patterns:

1) Simple computation pattern

```python
from reaktiv import Signal, LinkedSignal

source = Signal("initial")
linked = LinkedSignal(lambda: source().upper())

print(linked())  # INITIAL

# Manual override
linked.set("MANUAL")
print(linked())  # MANUAL

# Source change resets to computed value
source.set("changed")
print(linked())  # CHANGED
```

2) Advanced pattern with explicit source and computation

```python
from reaktiv import Signal, LinkedSignal, PreviousState

options = Signal(["A", "B", "C"])

selected = LinkedSignal(
    source=options,
    computation=lambda new_opts, prev: (
        prev.value if prev and prev.value in new_opts else new_opts[0]
    ),
)

print(selected())  # A

# Manual choice preserved if still valid
selected.set("B")
options.set(["X", "B", "Y"])  # B still present
print(selected())  # B

# Fallback when previous value is no longer valid
options.set(["X", "Y", "Z"])  # B missing
print(selected())  # X
```

The `computation` in the advanced pattern receives:
- `new_source_value`: current value of the source
- `prev`: an optional `PreviousState` with fields:
  - `value`: the previous linked value (including manual overrides)
  - `source`: the previous source value

## API

```python
LinkedSignal(
    computation_or_source: Callable[[], T] | None = None,
    *,
    source: Signal[U] | Callable[[], U] | None = None,
    computation: Callable[[U, PreviousState[T] | None], T] | None = None,
    equal: Callable[[T, T], bool] | None = None,
)
```

- Provide either a simple computation function, or both `source` and `computation`.
- Optional `equal` controls value comparison; when provided, updates that compare equal are skipped.

Methods:
- `__call__() -> T` / `get() -> T`: read the current value
- `set(new_value: T) -> None`: manually override the value
- `update(fn: Callable[[T], T]) -> None`: update based on current value
- `dispose() -> None`: stop reacting to source changes and freeze current value

## Integration with effects and computed values

```python
from reaktiv import Signal, Effect, Computed, LinkedSignal

counter = Signal(0)
linked = LinkedSignal(lambda: counter() * 2)

# Works with Computed
label = Computed(lambda: f"Value: {linked()}")
print(label())  # Value: 0

# Works with Effects (keep a reference!)
log = []
link_effect = Effect(lambda: log.append(linked()))

linked.set(99)    # manual override -> effect runs
counter.set(5)    # source change -> resets to 10 -> effect runs

print(log)  # ... includes 99, then 10
```

## Previous state access

```python
from reaktiv import Signal, LinkedSignal

src = Signal(1)

history = []
linked = LinkedSignal(
    source=src,
    computation=lambda new_val, prev: (
        history.append({
            "new": new_val,
            "prev_value": prev.value if prev else None,
            "prev_source": prev.source if prev else None,
        }) or (new_val * 10)
    ),
)

print(linked())  # 10
src.set(2)
print(linked())  # 20
# history contains previous linked and source values
```

## Batching

LinkedSignal participates in batching like other signals:

```python
from reaktiv import Signal, Effect, batch, LinkedSignal

src = Signal(1)
lnk = LinkedSignal(lambda: src() * 10)

runs = []
_ef = Effect(lambda: runs.append(lnk()))

with batch():
    lnk.set(50)
    lnk.update(lambda x: x + 1)

print(runs[-1])  # 51 (single batched run)

with batch():
    src.set(2)
    src.set(3)

print(runs[-1])  # 30 (resets to final computed value in batch)
```

## Custom equality

```python
from reaktiv import Signal, LinkedSignal

src = Signal(1.0)
lnk = LinkedSignal(lambda: src() * 3.0, equal=lambda a, b: abs(a - b) < 0.1)

src.set(1.02)  # small change may be ignored due to equality
src.set(1.5)   # larger change triggers update
```

## Disposal

```python
from reaktiv import Signal, LinkedSignal

src = Signal(1)
lnk = LinkedSignal(lambda: src() * 2)

lnk.dispose()

lnk.set(99)     # ignored after dispose
src.set(10)     # source updates no longer affect lnk
```

## Notes

- Keep a reference to any `Effect` using your LinkedSignal to prevent it from being garbage collected.
- In the advanced pattern, only the provided `source` drives resets; other signals read in effects won’t cause resets unless included in the LinkedSignal’s computation.
- Computations are evaluated lazily and memoized like other computed signals.

## Practical use cases

### 1) Selection that persists when valid

```python
from reaktiv import Signal, Effect
from reaktiv.linked import LinkedSignal

items = Signal([
    {"id": 1, "name": "Item A"},
    {"id": 2, "name": "Item B"},
    {"id": 3, "name": "Item C"},
])

selected_item = LinkedSignal(
    source=items,
    computation=lambda new_items, prev: (
        # Preserve previous selection by id if still present
        next((it for it in new_items if prev and prev.value and it["id"] == prev.value["id"]), None)
        or (new_items[0] if new_items else None)
    ),
)

def render():
    current = selected_item()
    print("Selected:", current["name"] if current else "<none>")

_ = Effect(render)

# User picks Item B manually
selected_item.set(items()[1])

# Data updates – keeps selection if still valid
items.set([
    {"id": 2, "name": "Item B"},
    {"id": 4, "name": "Item D"},
])

# Data updates – fall back to first when selection no longer valid
items.set([
    {"id": 5, "name": "Item E"},
    {"id": 6, "name": "Item F"},
])
```

### 2) Wizard flow that snaps to valid step

```python
from reaktiv import Signal
from reaktiv.linked import LinkedSignal

current_step_index = Signal(0)
available_steps = Signal(["info", "details", "confirm"])  # dynamic

# Track both steps and step index as the source so either can trigger resets
active_step = LinkedSignal(
    source=lambda: (available_steps(), current_step_index()),
    computation=lambda src, prev: (
        # Preserve previous selection only when the steps list changes
        prev.value
        if (
            prev
            and isinstance(prev.source, tuple)
            and prev.source[0] != src[0]  # steps list changed
            and prev.value in src[0]
        )
        else (src[0][min(src[1], len(src[0]) - 1)] if src[0] else None)
    ),
)

print(active_step())  # info
current_step_index.set(1)
print(active_step())  # details

# Steps change – snaps to closest valid
available_steps.set(["confirm"])  # only last step remains
print(active_step())  # confirm
```

### 3) Form field with defaulting to server schema

```python
from reaktiv import Signal, LinkedSignal

schema = Signal({"timeout": 30, "retries": 3})

user_timeout = LinkedSignal(
    source=schema,
    computation=lambda new_schema, prev: prev.value if prev else new_schema["timeout"],
)

print(user_timeout())   # 30 (default from schema)
user_timeout.set(60)    # user overrides
print(user_timeout())   # 60

schema.set({"timeout": 45, "retries": 5})  # server updates schema
print(user_timeout())   # 45 (resets to new default)
```

### 4) Pagination that clamps to valid page

```python
from reaktiv import Signal
from reaktiv.linked import LinkedSignal

# Total pages comes from server; user can pick a page manually.
total_pages = Signal(5)

current_page = LinkedSignal(
    source=total_pages,
    computation=lambda total, prev: (
        # If user picked a page before, keep it but clamp to [1, total]
        min(max(prev.value, 1), total)
        if (prev and isinstance(prev.value, int) and total > 0)
        else (1 if total > 0 else None)
    ),
)

print(current_page())  # 1 (default)

# User navigates to page 3
current_page.set(3)
print(current_page())  # 3

# Server reduces total pages -> page clamps to last valid
total_pages.set(2)
print(current_page())  # 2

# No pages available
total_pages.set(0)
print(current_page())  # None

# Pages appear again -> reset to default
total_pages.set(10)
print(current_page())  # 1
```
