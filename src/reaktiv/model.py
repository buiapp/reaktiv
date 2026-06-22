"""Class-based reactive model helpers."""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Generic,
    Optional,
    Protocol,
    TypeVar,
    Union,
    overload,
    runtime_checkable,
)
from weakref import WeakKeyDictionary

from ._descriptor import PerInstanceDescriptor
from .signal import Signal

T = TypeVar("T")


class ReactiveModel:
    """Base class for per-instance reactive state.

    Declare writable state with `field()` and derive model-owned reactive
    members with `@computed`, `@linked`, `@effect`, and `@resource`. Every model
    instance receives its own signals, computed values, effects, and resources.

    Values passed to the constructor override declared field defaults before
    eager effects and resources are initialized:

    ```python
    from reaktiv import ReactiveModel, computed, field


    class CounterModel(ReactiveModel):
        count = field(0)

        @computed
        def doubled(self) -> int:
            return self.count() * 2


    counter = CounterModel(count=5)

    print(counter.count())    # 5
    print(counter.doubled())  # 10
    ```

    Field types are inferred from defaults and factories. Use `field[T]` when
    the type should be explicit:

    ```python
    class UserModel(ReactiveModel):
        name = field[str]("")
        age = field[int](0)
        tags = field[list[str]](factory=list)


    user = UserModel(name="Ada")
    ```

    Every field must provide either a default value or a factory. Constructor
    values override those defaults. Unknown constructor field names raise
    `TypeError`.

    Add an explicit constructor when callers should receive precise parameter
    hints and static type checking:

    ```python
    class CounterModel(ReactiveModel):
        count = field(0)

        def __init__(self, count: int = 0) -> None:
            super().__init__(count=count)
    ```

    When mixing `ReactiveModel` with a class that does not use cooperative
    `super()`, initialize both bases explicitly. Call `ReactiveModel.__init__`
    last, after setting every ordinary attribute that an effect or resource may
    read, because model-owned effects start during reactive initialization:

    ```python
    from reaktiv import ReactiveModel, effect, field


    class NamedService:
        def __init__(self, name: str) -> None:
            self.name = name


    class CounterService(NamedService, ReactiveModel):
        count = field(0)

        def __init__(self, name: str, count: int = 0) -> None:
            NamedService.__init__(self, name)
            ReactiveModel.__init__(self, count=count)

        @effect
        def log_count(self) -> None:
            print(f"{self.name}: {self.count()}")
    ```

    Call `dispose()` when the model is no longer needed. It disposes all effects
    and resources owned by that model instance.

    Args:
        **fields: Initial values for fields declared with `field()`.
    """

    def __init__(self, **fields: object) -> None:
        self._reaktiv_owned: list[object] = []
        declared_fields = self._reaktiv_declared_fields()

        unknown = fields.keys() - declared_fields.keys()
        if unknown:
            names = ", ".join(sorted(unknown))
            raise TypeError(f"Unknown reactive field(s): {names}")

        for name, value in fields.items():
            declared_fields[name].initialize(self, value)
        self._reaktiv_initialize_eager_members()

    def _reaktiv_declared_fields(self) -> dict[str, "SignalField[Any]"]:
        fields: dict[str, SignalField[Any]] = {}
        seen: set[str] = set()
        for cls in type(self).mro():
            for name, member in cls.__dict__.items():
                if name in seen:
                    continue
                seen.add(name)
                if isinstance(member, SignalField):
                    fields[name] = member
        return fields

    def _reaktiv_initialize_eager_members(self) -> None:
        seen: set[str] = set()
        for cls in reversed(type(self).mro()):
            for name, member in tuple(cls.__dict__.items()):
                if name in seen:
                    continue
                seen.add(name)
                if (
                    isinstance(member, PerInstanceDescriptor)
                    and member.initialize_eagerly
                ):
                    member.initialize(self)

    def _reaktiv_retain(self, value: object) -> None:
        if not hasattr(self, "_reaktiv_owned"):
            self._reaktiv_owned = []
        if value not in self._reaktiv_owned:
            self._reaktiv_owned.append(value)

    def dispose(self) -> None:
        """Dispose model-owned effects and resources."""
        for value in reversed(self._reaktiv_owned):
            if isinstance(value, Disposable):
                value.dispose()
                continue
            if isinstance(value, Destroyable):
                value.destroy()
        self._reaktiv_owned.clear()


@runtime_checkable
class Disposable(Protocol):
    def dispose(self) -> None: ...


@runtime_checkable
class Destroyable(Protocol):
    def destroy(self) -> None: ...


class SignalField(Generic[T]):
    """Descriptor that creates one writable Signal per model instance."""

    @overload
    def __init__(self, default: T, /) -> None: ...

    @overload
    def __init__(self, *, factory: Callable[[], T]) -> None: ...

    def __init__(
        self,
        *defaults: T,
        factory: Optional[Callable[[], T]] = None,
    ) -> None:
        if len(defaults) == 1 and factory is None:
            default = defaults[0]
            self._initial_value = lambda: default
        elif not defaults and factory is not None:
            self._initial_value = factory
        else:
            raise TypeError("field() requires exactly one default value or a factory")
        self._cache: WeakKeyDictionary[object, Signal[T]] = WeakKeyDictionary()
        self._storage_name: Optional[str] = None

    def __set_name__(self, owner: type, name: str) -> None:
        self._storage_name = f"__reaktiv_field_{owner.__name__}_{name}"

    @overload
    def __get__(self, instance: None, owner: Optional[type] = None) -> "SignalField[T]": ...

    @overload
    def __get__(self, instance: object, owner: Optional[type] = None) -> Signal[T]: ...

    def __get__(
        self, instance: Optional[object], owner: Optional[type] = None
    ) -> Union[Signal[T], "SignalField[T]"]:
        if instance is None:
            return self
        return self._get_or_create(instance)

    def __set__(self, instance: object, value: T) -> None:
        self._get_or_create(instance).set(value)

    def initialize(self, instance: object, value: T) -> Signal[T]:
        signal = self._get_existing(instance)
        if signal is not None:
            signal.set(value)
            return signal

        signal = Signal(value)
        self._store(instance, signal)
        return signal

    def _get_or_create(self, instance: object) -> Signal[T]:
        signal = self._get_existing(instance)
        if signal is not None:
            return signal

        signal = Signal(self._initial_value())
        self._store(instance, signal)
        return signal

    def _get_existing(self, instance: object) -> Optional[Signal[T]]:
        try:
            return self._cache[instance]
        except KeyError:
            return None
        except TypeError:
            return self._get_from_instance_dict(instance)

    def _store(self, instance: object, signal: Signal[T]) -> None:
        try:
            self._cache[instance] = signal
        except TypeError:
            self._set_on_instance_dict(instance, signal)

    def _get_from_instance_dict(self, instance: object) -> Optional[Signal[T]]:
        if self._storage_name is None:
            return None
        try:
            value = vars(instance).get(self._storage_name)
        except TypeError:
            return None
        if value is None:
            return None
        if not isinstance(value, Signal):
            raise TypeError(f"Invalid reactive field storage: {self._storage_name}")
        return value

    def _set_on_instance_dict(self, instance: object, value: Signal[T]) -> None:
        if self._storage_name is None or not hasattr(instance, "__dict__"):
            raise TypeError(
                "Reactive model fields require weak-referenceable instances or "
                "instances with a __dict__"
            )
        vars(instance)[self._storage_name] = value


field = SignalField
