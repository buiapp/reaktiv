"""Class-based reactive model helpers."""

from __future__ import annotations

from typing import Callable, Generic, Optional, Protocol, TypeVar, Union, overload, runtime_checkable
from weakref import WeakKeyDictionary

from ._descriptor import PerInstanceDescriptor
from .signal import Signal

T = TypeVar("T")

class _Missing:
    pass


_MISSING = _Missing()


class ReactiveModel:
    """Base class for class-based reactive state models."""

    def __init__(self, **fields: object) -> None:
        self._reaktiv_owned: list[object] = []
        for name, value in fields.items():
            setattr(self, name, value)
        self._reaktiv_initialize_eager_members()

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

    def __init__(
        self,
        default: Union[T, _Missing] = _MISSING,
        *,
        factory: Optional[Callable[[], T]] = None,
    ) -> None:
        if not isinstance(default, _Missing) and factory is not None:
            raise ValueError("field() accepts either a default or a factory, not both")
        self._default = default
        self._factory = factory
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

    def _get_or_create(self, instance: object) -> Signal[T]:
        try:
            return self._cache[instance]
        except KeyError:
            signal = Signal(self._initial_value())
            self._cache[instance] = signal
            return signal
        except TypeError:
            signal = self._get_from_instance_dict(instance)
            if not isinstance(signal, _Missing):
                return signal
            signal = Signal(self._initial_value())
            self._set_on_instance_dict(instance, signal)
            return signal

    def _initial_value(self) -> T:
        if self._factory is not None:
            return self._factory()
        if isinstance(self._default, _Missing):
            raise ValueError("field() requires a default or factory")
        return self._default

    def _get_from_instance_dict(self, instance: object) -> Union[Signal[T], _Missing]:
        if self._storage_name is None or not hasattr(instance, "__dict__"):
            return _MISSING
        return vars(instance).get(self._storage_name, _MISSING)

    def _set_on_instance_dict(self, instance: object, value: Signal[T]) -> None:
        if self._storage_name is None or not hasattr(instance, "__dict__"):
            raise TypeError(
                "Reactive model fields require weak-referenceable instances or "
                "instances with a __dict__"
            )
        vars(instance)[self._storage_name] = value


@overload
def field(default: T) -> SignalField[T]: ...


@overload
def field(*, factory: Callable[[], T]) -> SignalField[T]: ...


def field(
    default: Union[T, _Missing] = _MISSING,
    *,
    factory: Optional[Callable[[], T]] = None,
) -> SignalField[T]:
    """Declare a per-instance Signal field on a ReactiveModel."""
    return SignalField(default, factory=factory)
