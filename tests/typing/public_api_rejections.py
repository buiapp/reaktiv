"""Type-checking fixture: uses the public API must reject.

Checked with Pyright, not pytest. Every ``# pyright: ignore[...]`` below marks
a line that has to be an error; ``reportUnnecessaryTypeIgnoreComment`` turns a line
that type-checks into a failure, so these rejections cannot silently regress.
"""

# pyright: reportUnnecessaryTypeIgnoreComment=true

from __future__ import annotations

from typing import Optional

from reaktiv import (
    PreviousState,
    ReactiveModel,
    ReadableSignal,
    WritableSignal,
    computed,
    field,
    linked,
    signal,
)

count = signal(0)
readonly: ReadableSignal[int] = count.as_readonly()
readonly.set(1)  # pyright: ignore[reportAttributeAccessIssue]

label = computed(lambda: f"count={count()}")
label_length: int = label()  # pyright: ignore[reportAssignmentType]

count.set("one")  # pyright: ignore[reportArgumentType]
count.update(lambda value: str(value))  # pyright: ignore[reportArgumentType]

selected = linked(lambda: count() * 2)
selected.set("two")  # pyright: ignore[reportArgumentType]

# Explicitly typed factories check the callback's result against the type.
computed[int](lambda: "text")  # pyright: ignore[reportArgumentType, reportCallIssue]
linked[int](lambda: "text")  # pyright: ignore[reportArgumentType, reportCallIssue]


@computed[int](equal=lambda a, b: a == b)  # pyright: ignore[reportArgumentType]
def typed_label() -> str:
    return "text"


class Model:
    @computed[int]  # pyright: ignore[reportArgumentType, reportCallIssue]
    def label(self) -> str:
        return "text"

    @linked[int]  # pyright: ignore[reportArgumentType, reportCallIssue]
    def chosen(self) -> str:
        return "text"


# Capabilities: only signal and linked are writable.
def overwrite(target: WritableSignal[int]) -> None:
    target.set(99)


def read(source: ReadableSignal[int]) -> int:
    return source()


doubled = computed(lambda: count() * 2)
editable = linked(lambda: count() * 2)

overwrite(doubled)  # pyright: ignore[reportArgumentType]
overwrite(count.as_readonly())  # pyright: ignore[reportArgumentType]
doubled.set(1)  # pyright: ignore[reportAttributeAccessIssue]
doubled.update(lambda value: value + 1)  # pyright: ignore[reportAttributeAccessIssue]

overwrite(count)
overwrite(editable)
for node in (count, doubled, editable, count.as_readonly()):
    read(node)

# Any readable signal can be a linked source.
from_computed = linked(source=doubled, computation=lambda value, previous: value + 1)
from_readonly = linked(source=count.as_readonly(), computation=lambda value, previous: value)


# PreviousState[S, T]: the previous source has the source type, not the value type.
items = signal(["a", "b"])


def summarize(source: list[str], previous: Optional[PreviousState[list[str], str]]) -> str:
    if previous is not None:
        previous.source.upper()  # pyright: ignore[reportAttributeAccessIssue]
        previous.value.upper()
    return ",".join(source)


summary = linked(source=items, computation=summarize)
summary_text: str = summary()


def wrong_source_type(source: int, previous: Optional[PreviousState[int, str]]) -> str:
    return str(source)


linked(source=items, computation=wrong_source_type)  # pyright: ignore[reportArgumentType]


def keep_previous_length(source: list[str], previous: Optional[PreviousState[list[str], int]]) -> int:
    if previous is None:
        return len(source)
    source_length: int = len(previous.source)
    return previous.value + source_length


lengths = linked(source=items, computation=keep_previous_length)
length_value: int = lengths()
wrong_length: str = lengths()  # pyright: ignore[reportAssignmentType]


# A single parameter still means "source and value share the type".
def same_type(source: int, previous: Optional[PreviousState[int]]) -> int:
    if previous is None:
        return source
    both: tuple[int, int] = (previous.source, previous.value)
    return max(both)


same = linked(source=count, computation=same_type)


class Pages(ReactiveModel):
    total = field(3)

    def clamp(self, source: int, previous: Optional[PreviousState[int, str]]) -> str:
        return previous.value if previous is not None else str(source)

    @linked(computation=clamp)
    def page(self) -> int:
        return self.total()

    @linked(computation=clamp)  # pyright: ignore[reportArgumentType]
    def wrong_page(self) -> str:
        return "1"
