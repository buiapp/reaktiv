"""Type-checking fixture for public generic inference.

This file is not a pytest module. It is checked with ty to ensure public
decorators and factory functions preserve their user-visible value types.
"""

from __future__ import annotations

from typing import Optional

from reaktiv import (
    Computed,
    ComputeSignal,
    Effect,
    Linked,
    LinkedSignal,
    ReadableSignal,
    ReactiveModel,
    Resource,
    ResourceLoaderParams,
    Signal,
    WritableSignal,
    computed,
    effect,
    field,
    linked,
    resource,
    untracked,
)


count: Signal[int] = Signal(1)
name: Signal[str] = Signal("Ada")

readonly_count: ReadableSignal[int] = count.as_readonly()
writable_count: WritableSignal[int] = count
untracked_readonly_count: int = untracked(readonly_count)
untracked_name: str = untracked(lambda: name())

factory_computed: ComputeSignal[int] = Computed(lambda: count() + 1)


@computed
def decorated_computed() -> str:
    return name().upper()


decorated_computed_signal: ComputeSignal[str] = decorated_computed


factory_linked: LinkedSignal[int] = Linked(lambda: count() * 2)


@linked
def decorated_linked() -> str:
    return name()


decorated_linked_signal: LinkedSignal[str] = decorated_linked
decorated_linked.set("Grace")


uppercase_effect: Effect = Effect(lambda: decorated_computed())
lowercase_effect: Effect = effect(lambda: decorated_computed())


class CounterModel(ReactiveModel):
    count = field(1)
    name = field[str]("")
    labels = field[list[str]](factory=list)
    optional_name = field[Optional[str]](None)

    @computed
    def doubled(self) -> int:
        return self.count() * 2

    @computed[str]
    def normalized_name(self):
        return self.name().strip().lower()

    @computed[list[int]]
    def repeated_counts(self):
        return [self.count()]

    @computed[str](equal=lambda left, right: left == right)
    def normalized_label(self):
        return self.name().strip()

    @computed[str]
    def loud_name(self):
        return self.name().upper()

    @linked
    def editable_name(self) -> str:
        return self.name()

    @linked[str]
    def lowercase_linked(self):
        return self.name()

    @linked
    def title_name(self) -> str:
        return self.name()

    @effect
    def track(self) -> None:
        self.doubled()

    @effect
    def track_loud_name(self) -> None:
        self.loud_name()

    @resource[dict[str, str], dict[str, str]]
    def user(self):
        return {"name": self.name()}

    @user.loader
    async def load_user(
        self, params: ResourceLoaderParams[dict[str, str]]
    ) -> dict[str, str]:
        return params.params

    @resource[dict[str, str], dict[str, str]]
    def cached_user(self):
        return {"name": self.name()}

    @cached_user.loader
    async def load_cached_user(
        self, params: ResourceLoaderParams[dict[str, str]]
    ) -> dict[str, str]:
        return params.params


model = CounterModel(name="Ada")
model_count: Signal[int] = model.count
model_name_field: Signal[str] = model.name
model_labels: Signal[list[str]] = model.labels
model_optional_name: Signal[Optional[str]] = model.optional_name
model_doubled: ComputeSignal[int] = model.doubled
model_normalized_name: ComputeSignal[str] = model.normalized_name
model_normalized_name_value: str = model.normalized_name()
model_repeated_counts: ComputeSignal[list[int]] = model.repeated_counts
model_repeated_counts_value: list[int] = model.repeated_counts()
model_normalized_label: ComputeSignal[str] = model.normalized_label
model_normalized_label_value: str = model.normalized_label()
model_loud_name: ComputeSignal[str] = model.loud_name
model_loud_name_value: str = model.loud_name()
model_name: LinkedSignal[str] = model.editable_name
model_lowercase_linked: LinkedSignal[str] = model.lowercase_linked
model_lowercase_linked_value: str = model.lowercase_linked()
model_title_name: LinkedSignal[str] = model.title_name
model_effect: Effect = model.track
model_loud_name_effect: Effect = model.track_loud_name
model_resource: Resource[dict[str, str], dict[str, str]] = model.user
model_cached_resource: Resource[dict[str, str], dict[str, str]] = model.cached_user
