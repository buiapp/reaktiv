import asyncio
import gc
import weakref

import pytest

from reaktiv import (
    Signal,
    Effect,
    ReactiveModel,
    ResourceLoaderParams,
    ResourceStatus,
    computed,
    effect,
    field,
    linked,
    resource,
)


def test_effect_free_function_decorator_creates_effect() -> None:
    values: list[int] = []

    count = Signal(0)

    @effect
    def track_count() -> None:
        values.append(count())

    try:
        assert isinstance(track_count, Effect)
        assert values == [0]
        count.set(1)
        assert values == [0, 1]
    finally:
        track_count.dispose()


def test_reactive_model_fields_are_per_instance() -> None:
    class Counter(ReactiveModel):
        count = field(0)
        items = field(factory=list)

    left = Counter()
    right = Counter()

    left.count.set(10)
    left.items.set(["left"])

    assert left.count() == 10
    assert right.count() == 0
    assert left.items() == ["left"]
    assert right.items() == []


def test_computed_and_linked_method_decorators_are_per_instance() -> None:
    class Cart(ReactiveModel):
        price = field(10)
        quantity = field(2)

        @computed
        def subtotal(self) -> int:
            return self.price() * self.quantity()

        @linked
        def selected_quantity(self) -> int:
            return self.quantity()

    left = Cart()
    right = Cart()

    left.price.set(20)
    left.quantity.set(3)
    left.selected_quantity.set(99)

    assert left.subtotal() == 60
    assert right.subtotal() == 20
    assert left.selected_quantity() == 99
    assert right.selected_quantity() == 2

    left.quantity.set(4)
    assert left.selected_quantity() == 4
    assert right.selected_quantity() == 2


def test_typed_computed_decorator_does_not_require_return_annotation() -> None:
    class Search(ReactiveModel):
        query = field(" Notebook ")

        @computed[str]
        def normalized_query(self):
            return self.query().strip().lower()

        @computed[str](equal=lambda left, right: left == right)
        def label(self):
            return self.query().strip()

    search = Search()

    assert search.normalized_query() == "notebook"
    assert search.label() == "Notebook"

    search.query.set(" Desk ")

    assert search.normalized_query() == "desk"
    assert search.label() == "Desk"


def test_method_decorator_equality_options_are_preserved() -> None:
    computed_equal_calls = 0
    linked_equal_calls = 0

    def computed_equal(left: dict[str, int], right: dict[str, int]) -> bool:
        nonlocal computed_equal_calls
        computed_equal_calls += 1
        return left == right

    def linked_equal(left: str, right: str) -> bool:
        nonlocal linked_equal_calls
        linked_equal_calls += 1
        return left == right

    class Profile(ReactiveModel):
        name = field("Ada")

        @computed(equal=computed_equal)
        def summary(self) -> dict[str, int]:
            return {"length": len(self.name())}

        @linked(equal=linked_equal)
        def label(self) -> str:
            return self.name()

    profile = Profile()

    assert profile.summary() == {"length": 3}
    profile.name.set("Bob")
    assert profile.summary() == {"length": 3}
    assert computed_equal_calls >= 1

    profile.label.set("Custom")
    profile.label.set("Custom")
    assert profile.label() == "Custom"
    assert linked_equal_calls >= 1


def test_effect_method_decorator_is_owned_and_disposed() -> None:
    class Counter(ReactiveModel):
        count = field(0)

        def __init__(self) -> None:
            self.values: list[int] = []
            super().__init__()

        @effect
        def track_count(self) -> None:
            self.values.append(self.count())

    counter = Counter()
    assert counter.values == [0]

    counter.count.set(1)
    assert counter.values == [0, 1]

    counter.dispose()
    counter.count.set(2)
    assert counter.values == [0, 1]


def test_descriptor_cache_does_not_keep_instances_alive() -> None:
    class Counter(ReactiveModel):
        count = field(1)

        @computed
        def doubled(self) -> int:
            return self.count() * 2

    counter = Counter()
    assert counter.doubled() == 2

    ref = weakref.ref(counter)
    del counter
    gc.collect()

    assert ref() is None


@pytest.mark.asyncio
async def test_resource_method_decorator_is_per_instance_and_disposed() -> None:
    class UserModel(ReactiveModel):
        user_id = field("ada")

        @resource
        def user(self) -> dict[str, str]:
            return {"id": self.user_id()}

        @user.loader
        async def load_user(
            self, params: ResourceLoaderParams[dict[str, str]]
        ) -> dict[str, str]:
            await asyncio.sleep(0)
            return {"id": params.params["id"], "name": params.params["id"].title()}

    left = UserModel()
    right = UserModel()
    right.user_id.set("grace")

    try:
        await _wait_for(lambda: left.user.status() == ResourceStatus.RESOLVED)
        await _wait_for(lambda: right.user.status() == ResourceStatus.RESOLVED)

        assert left.user.value() == {"id": "ada", "name": "Ada"}
        assert right.user.value() == {"id": "grace", "name": "Grace"}
        assert left.user is left.user
        assert left.user is not right.user
    finally:
        left.dispose()
        right.dispose()
        await asyncio.sleep(0)


async def _wait_for(predicate, timeout: float = 1.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.001)
    raise AssertionError("condition was not reached before timeout")
