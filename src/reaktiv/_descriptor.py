"""Descriptor helpers for per-instance reactive primitives."""

from __future__ import annotations

import inspect
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

T = TypeVar("T")
DescriptorT = TypeVar("DescriptorT", bound="PerInstanceDescriptor[Any]")

class _Missing:
    pass


_MISSING = _Missing()


def is_instance_method(func: Callable[..., object]) -> bool:
    """Return True for decorator targets that look like instance/class methods."""
    try:
        parameters = tuple(inspect.signature(func).parameters.values())
    except (TypeError, ValueError):
        return False
    if not parameters:
        return False
    first = parameters[0]
    if first.kind not in (
        inspect.Parameter.POSITIONAL_ONLY,
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
    ):
        return False
    return first.name in {"self", "cls"}


def retain_owner(instance: object, value: object) -> None:
    if isinstance(instance, ReactiveOwner):
        instance._reaktiv_retain(value)


@runtime_checkable
class ReactiveOwner(Protocol):
    def _reaktiv_retain(self, value: object) -> None: ...


class PerInstanceDescriptor(Generic[T]):
    """Cache one created reactive object per owner instance."""

    initialize_eagerly = False

    def __init__(self) -> None:
        self._cache: WeakKeyDictionary[object, T] = WeakKeyDictionary()
        self._storage_name: Optional[str] = None

    def __set_name__(self, owner: type, name: str) -> None:
        self._storage_name = f"__reaktiv_{owner.__name__}_{name}"

    @overload
    def __get__(
        self: DescriptorT, instance: None, owner: Optional[type] = None
    ) -> DescriptorT: ...

    @overload
    def __get__(self, instance: object, owner: Optional[type] = None) -> T: ...

    def __get__(
        self: DescriptorT,
        instance: Optional[object],
        owner: Optional[type] = None,
    ) -> Union[T, DescriptorT]:
        if instance is None:
            return self
        return self._get_or_create(instance)

    def initialize(self, instance: object) -> T:
        return self._get_or_create(instance)

    def _get_or_create(self, instance: object) -> T:
        try:
            return self._cache[instance]
        except KeyError:
            value = self._create(instance)
            self._cache[instance] = value
            retain_owner(instance, value)
            return value
        except TypeError:
            value = self._get_from_instance_dict(instance)
            if not isinstance(value, _Missing):
                return value
            value = self._create(instance)
            self._set_on_instance_dict(instance, value)
            retain_owner(instance, value)
            return value

    def _get_from_instance_dict(self, instance: object) -> Union[T, _Missing]:
        if self._storage_name is None or not hasattr(instance, "__dict__"):
            return _MISSING
        return vars(instance).get(self._storage_name, _MISSING)

    def _set_on_instance_dict(self, instance: object, value: T) -> None:
        if self._storage_name is None or not hasattr(instance, "__dict__"):
            raise TypeError(
                "Reactive descriptors require weak-referenceable instances or "
                "instances with a __dict__"
            )
        vars(instance)[self._storage_name] = value

    def _create(self, instance: object) -> T:
        raise NotImplementedError
