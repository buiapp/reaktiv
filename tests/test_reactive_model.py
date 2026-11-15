import asyncio
import gc
import weakref
from typing import Optional

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


def test_typed_fields_support_defaults_and_factories() -> None:
    class Profile(ReactiveModel):
        name = field[str]("")
        age = field[int](0)
        tags = field[list[str]](factory=list)
        nickname = field[Optional[str]](None)

        def __init__(self, name: str, age: int = 0) -> None:
            self.observed: list[tuple[str, int]] = []
            super().__init__(name=name, age=age)

        @effect
        def observe(self) -> None:
            self.observed.append((self.name(), self.age()))

    profile = Profile("Ada", age=37)

    assert profile.name() == "Ada"
    assert profile.age() == 37
    assert profile.tags() == []
    assert profile.nickname() is None
    assert profile.observed == [("Ada", 37)]


def test_fields_require_a_default_or_factory() -> None:
    with pytest.raises(TypeError, match="requires exactly one default value"):
        field()

    with pytest.raises(TypeError, match="requires exactly one default value"):
        field[str]()


def test_reactive_model_rejects_unknown_fields() -> None:
    class User(ReactiveModel):
        name = field[str]("")

    with pytest.raises(TypeError, match="Unknown reactive field.*nmae"):
        User(name="Ada", nmae="Grace")


def test_subclass_attribute_can_override_inherited_field() -> None:
    class Base(ReactiveModel):
        value = field(1)

    class Child(Base):
        value = "fixed"

    child = Child()

    assert child.value == "fixed"
    with pytest.raises(TypeError, match="Unknown reactive field.*value"):
        Child(value=2)


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


def test_effect_method_can_return_cleanup() -> None:
    class Counter(ReactiveModel):
        count = field(0)
        runs = field[list[int]](factory=list)
        cleanups = field[list[int]](factory=list)

        @effect
        def track_count(self):
            value = self.count()
            self.runs().append(value)
            return lambda: self.cleanups().append(value)

    counter = Counter()

    counter.count.set(1)
    assert counter.runs() == [0, 1]
    assert counter.cleanups() == [0]

    counter.dispose()
    assert counter.cleanups() == [0, 1]


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


def test_field_accepts_custom_equality_for_defaults_and_explicit_initial_values():
    class Model(ReactiveModel):
        amount = field(1.0, equal=lambda previous, current: abs(previous - current) < 0.1)

    for model in [Model(), Model(amount=1.0)]:
        model.amount.set(1.05)
        assert model.amount() == 1.0
        model.amount.set(2.0)
        assert model.amount() == 2.0
        model.dispose()


def test_equal_model_instances_keep_separate_reactive_state():
    import gc

    from reaktiv import ReactiveModel, computed, effect, field, linked

    runs = []

    class Point(ReactiveModel):
        x = field(0)

        @computed
        def double(self):
            return self.x() * 2

        @linked
        def chosen(self):
            return self.x()

        @effect
        def log(self):
            runs.append(self.x())

        def __eq__(self, other):
            return isinstance(other, Point)

        def __hash__(self):
            return 1

    first, second = Point(), Point()
    first.x.set(1)
    second.x.set(2)
    assert (first.x(), second.x()) == (1, 2)
    assert (first.double(), second.double()) == (2, 4)
    assert (first.chosen(), second.chosen()) == (1, 2)
    assert first.log is not second.log
    import weakref

    refs = [weakref.ref(first), weakref.ref(second)]
    first.dispose()
    second.dispose()
    del first, second
    gc.collect()
    assert [ref() for ref in refs] == [None, None]


def test_subclass_overrides_of_eager_members_replace_the_base_member():
    from reaktiv import ReactiveModel, effect, field

    log = []

    class Base(ReactiveModel):
        x = field(0)

        @effect
        def watch(self):
            log.append(("base", self.x()))

        @effect
        def kept(self):
            log.append(("kept", self.x()))

    class Child(Base):
        @effect
        def watch(self):
            log.append(("child", self.x()))

    class Plain(Base):
        watch = None  # overriding with a non-reactive member disables the effect

    child = Child()
    child.watch
    assert sorted(log) == [("child", 0), ("kept", 0)]
    log.clear()
    plain = Plain()
    assert log == [("kept", 0)]
    child.dispose()
    plain.dispose()


def test_model_dispose_attempts_every_cleanup_and_raises_the_first_error(capsys):
    from reaktiv import ReactiveModel

    order = []

    class Cleanup:
        def __init__(self, name, error=None):
            self.name, self.error = name, error

        def dispose(self):
            order.append(self.name)
            if self.error:
                raise self.error

    model = ReactiveModel()
    model.own(Cleanup("first"))
    model.own(Cleanup("second", RuntimeError("second failed")))
    model.own(Cleanup("third", ValueError("third failed")))
    with pytest.raises(ValueError, match="third failed"):
        model.dispose()
    assert order == ["third", "second", "first"]
    assert "second failed" in capsys.readouterr().err
    model.dispose()  # ownership was cleared: nothing runs twice
    assert order == ["third", "second", "first"]


def test_models_referenced_by_their_own_reactive_members_are_collected():
    import gc
    import weakref

    from reaktiv import ReactiveModel, computed, effect, field, linked

    class Node(ReactiveModel):
        value = field(0)

        @computed
        def me(self):
            self.value()
            return self  # the cached result references the owner

        @linked
        def chosen(self):
            return (self, self.value())

        @effect
        def watch(self, on_cleanup):
            self.value()
            on_cleanup(lambda: self.value)  # the cleanup closes over the owner

    node = Node()
    assert node.me() is node
    node.chosen()
    ref = weakref.ref(node)
    del node
    gc.collect()
    assert ref() is None


def test_slotted_owners_without_dict_keep_separate_reactive_state():
    import gc
    import weakref

    from reaktiv import computed, field

    class Slotted:
        __slots__ = ("__weakref__",)
        x = field(1)

        @computed
        def double(self):
            return self.x() * 2

    first, second = Slotted(), Slotted()
    second.x.set(5)
    assert (first.double(), second.double()) == (2, 10)
    ref = weakref.ref(first)
    del first
    gc.collect()
    assert ref() is None


def test_objects_registered_after_dispose_are_disposed_immediately():
    import asyncio

    from reaktiv import ReactiveModel, field, resource

    class Handle:
        def __init__(self) -> None:
            self.disposed = 0

        def dispose(self) -> None:
            self.disposed += 1

    class Store(ReactiveModel):
        user_id = field(1)

        @resource[int, int]
        def user(self):
            return self.user_id()

        @user.loader
        async def load_user(self, params):
            calls.append(params.params)
            return params.params

    calls: list[int] = []

    async def main() -> None:
        store = Store()
        store.dispose()

        late = Handle()
        assert store.own(late) is late
        assert late.disposed == 1  # nothing would ever clean it up otherwise

        user = store.user  # first access after disposal: created disposed
        await asyncio.sleep(0.01)
        assert calls == []
        assert user.is_loading() is False

        store.dispose()  # idempotent
        assert late.disposed == 1

    asyncio.run(main())
