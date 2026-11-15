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
import weakref

T = TypeVar("T")
DescriptorT = TypeVar("DescriptorT", bound="PerInstanceDescriptor[Any]")

class _Missing:
    pass


_MISSING = _Missing()


class IdentityWeakMap(Generic[T]):
    """Map objects to values by identity, without keeping the objects alive.

    Unlike ``WeakKeyDictionary`` it never uses ``__eq__``/``__hash__``, so two
    distinct owners that compare equal get separate entries. ``set`` raises
    ``TypeError`` for objects that cannot be weakly referenced.
    """

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[int, tuple["weakref.ref[Any]", T]] = {}

    def get(self, key: object) -> Union[T, _Missing]:
        entry = self._entries.get(id(key))
        if entry is not None and entry[0]() is key:
            return entry[1]
        return _MISSING

    def set(self, key: object, value: T) -> None:
        entries = self._entries
        key_id = id(key)

        def remove(ref: "weakref.ref[Any]") -> None:
            entry = entries.get(key_id)
            if entry is not None and entry[0] is ref:
                del entries[key_id]

        entries[key_id] = (weakref.ref(key, remove), value)


class InstanceStorage(Generic[T]):
    """Per-instance values for one descriptor, owned by the instance.

    Values live in the instance ``__dict__``, as with ``functools.cached_property``,
    so they are released together with the instance even when they reference it
    (a computed returning ``self``, a cleanup closing over it). Only instances
    without a ``__dict__`` fall back to an identity-keyed weak map, which keeps
    the value alive as long as the instance exists.
    """

    __slots__ = ("_key", "_fallback")

    def __init__(self) -> None:
        self._key = f"_reaktiv_{id(self):x}"
        self._fallback: Optional[IdentityWeakMap[T]] = None

    def set_name(self, name: str) -> None:
        """Include the member name in the storage key, for readable ``vars()``."""
        self._key = f"_reaktiv_{name}_{id(self):x}"

    def get(self, instance: object) -> Union[T, _Missing]:
        values = getattr(instance, "__dict__", None)
        if values is not None:
            return values.get(self._key, _MISSING)
        if self._fallback is None:
            return _MISSING
        return self._fallback.get(instance)

    def set(self, instance: object, value: T) -> None:
        values = getattr(instance, "__dict__", None)
        if values is not None:
            values[self._key] = value
            return
        if self._fallback is None:
            self._fallback = IdentityWeakMap()
        try:
            self._fallback.set(instance, value)
        except TypeError:
            raise TypeError(
                "Reactive descriptors require instances with a __dict__ or "
                "weak-referenceable instances"
            ) from None


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
        self._storage: InstanceStorage[T] = InstanceStorage()

    def __set_name__(self, owner: type, name: str) -> None:
        self._storage.set_name(name)

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
        value = self._storage.get(instance)
        if not isinstance(value, _Missing):
            return value
        created = self._create(instance)
        self._storage.set(instance, created)
        retain_owner(instance, created)
        return created

    def _create(self, instance: object) -> T:
        raise NotImplementedError
