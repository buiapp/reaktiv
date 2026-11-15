"""LinkedSignal."""

from __future__ import annotations

import sys
import weakref
from typing import Generic, Optional, Callable, Union, cast, Any, overload

if sys.version_info >= (3, 13):
    from typing import TypeVar
else:  # TypeVar defaults (PEP 696)
    from typing_extensions import TypeVar

from . import graph
from ._descriptor import PerInstanceDescriptor, is_instance_method
from .protocols import ReadableSignal
from .signal import ComputeSignal, _SignalBase, debug_log, _assert_writable
from .context import untracked

T = TypeVar("T")
U = TypeVar("U")
S = TypeVar("S")

# PreviousState's own parameters: source type, then value type. The value type
# defaults to the source type, so ``PreviousState[X]`` keeps meaning "both X".
_PrevSource = TypeVar("_PrevSource")
_PrevValue = TypeVar("_PrevValue", default=_PrevSource)


class PreviousState(Generic[_PrevSource, _PrevValue]):
    """Container for previous state in LinkedSignal computations.

    ``PreviousState[S, T]``: ``S`` is the source type and ``T`` the linked value
    type, as in Angular's ``linkedSignal<S, D>``. ``PreviousState[X]`` means
    both are ``X``.

    Attributes:
        value: The previous value of the LinkedSignal
        source: The previous value of the source signal
    """

    __slots__ = ("value", "source")

    value: _PrevValue
    source: _PrevSource

    def __init__(self, value: _PrevValue, source: _PrevSource):
        """Initialize previous state with value and source."""
        self.value = value
        self.source = source


class LinkedDescriptor(PerInstanceDescriptor["LinkedSignal[T]"], Generic[T]):
    """Descriptor that creates one LinkedSignal per owner instance."""

    def __init__(
        self,
        func: Callable[[Any], T],
        *,
        equal: Optional[Callable[[T, T], bool]] = None,
        computation: Optional[Callable[[Any, Any, Optional[PreviousState[Any, T]]], T]] = None,
    ) -> None:
        super().__init__()
        self._func = func
        self._equal = equal
        self._computation = computation

    def _create(self, instance: object) -> "LinkedSignal[T]":
        try:
            instance_ref = weakref.ref(instance)

            def compute() -> T:
                current = instance_ref()
                if current is None:
                    raise ReferenceError("Reactive owner has been garbage collected")
                return self._func(current)

        except TypeError:
            def instance_ref() -> object:
                return instance

            def compute() -> T:
                return self._func(instance)

        if self._computation is None:
            return LinkedSignal(compute, equal=self._equal)

        def derive(source: Any, previous: Optional[PreviousState[Any, T]]) -> T:
            current = instance_ref()
            if current is None:
                raise ReferenceError("Reactive owner has been garbage collected")
            assert self._computation is not None
            return self._computation(current, source, previous)

        return LinkedSignal(source=compute, computation=derive, equal=self._equal)


class LinkedSignal(ComputeSignal[T], Generic[T]):
    """A writable signal that automatically recomputes when source signals change.
    
    LinkedSignal combines the benefits of computed signals (automatic updates) with
    writable signals (can be set manually). When source signals change, it recomputes.
    When manually set, it holds that value until sources change again.
    
    Perfect for form inputs, UI state, and derived values that users can override.
    
    Args:
        computation_or_source: The computation function (simple pattern) or source signal
        source: Optional source signal or callable (advanced pattern)
        computation: Optional computation function (advanced pattern)
        equal: Optional custom equality function for change detection
        
    Examples:
        Simple pattern (automatic derivation):
        ```python
        from reaktiv import linked, signal
        
        fahrenheit = signal(32)
        
        # Celsius automatically computes from Fahrenheit
        @linked
        def celsius():
            return (fahrenheit() - 32) * 5 / 9
        
        print(celsius())  # 0.0
        
        fahrenheit.set(212)
        print(celsius())  # 100.0
        
        # Can override manually
        celsius.set(25)
        print(celsius())  # 25.0 (manual value)
        
        # Changing source recomputes
        fahrenheit.set(68)
        print(celsius())  # 20.0 (recomputed from source)
        ```
        
        Form input pattern:
        ```python
        from reaktiv import effect, linked, signal
        
        # Server data
        server_name = signal("John Doe")
        
        # Form input linked to server data
        @linked
        def input_value():
            return server_name()
        
        # Track changes (keep reference to prevent GC)
        def print_input():
            print(f"Input: {input_value()}")

        input_effect = effect(print_input)
        # Prints: "Input: John Doe"
        
        # User edits the input
        input_value.set("Jane Smith")
        # Prints: "Input: Jane Smith"
        
        # Server data refreshes
        server_name.set("John Updated")
        # Prints: "Input: John Updated" (reset to server value)
        ```
        
        Advanced pattern (with previous state):
        ```python
        from reaktiv import PreviousState, linked, signal
        
        total_pages = signal(10)
        
        def clamp_page(page_num, prev):
            max_page = total_pages()
            
            if max_page == 0:
                return None
            
            # First time: use the default; otherwise preserve and clamp the override.
            if prev is None:
                return 1
            
            # Clamp to valid range
            return max(1, min(prev.value, max_page))
        
        current_page = linked(
            source=total_pages,
            computation=clamp_page
        )
        
        print(current_page())  # 1 (default)
        
        current_page.set(5)
        print(current_page())  # 5
        
        total_pages.set(3)
        print(current_page())  # 3 (clamped to max)
        ```
        
        As decorator:
        ```python
        from reaktiv import linked, signal
        
        source = signal(0)
        
        @linked
        def derived():
            return source() * 2
        
        print(derived())  # 0
        
        source.set(5)
        print(derived())  # 10
        
        derived.set(100)
        print(derived())  # 100 (manual override)
        ```
    """

    __slots__ = (
        "_source",
        "_source_fn",
        "_computation",
        "_previous_source",
        "_simple_pattern",
        "_has_previous",
        "_previous_value",
    )

    @overload
    def __new__(
        cls,
        func: Callable[[], T],
        /,
    ) -> LinkedSignal[T]: ...

    @overload
    def __new__(
        cls,
        func: Callable[[Any], T],
        /,
    ) -> LinkedDescriptor[T]: ...

    @overload
    def __new__(
        cls,
        func: Callable[[], T],
        /,
        *,
        equal: Callable[[T, T], bool],
    ) -> LinkedSignal[T]: ...

    @overload
    def __new__(
        cls,
        func: Callable[[Any], T],
        /,
        *,
        equal: Callable[[T, T], bool],
    ) -> LinkedDescriptor[T]: ...

    @overload
    def __new__(
        cls,
        /,
        *,
        equal: Callable[[T, T], bool],
    ) -> Callable[
        [Union[Callable[[], T], Callable[[Any], T]]],
        Union[LinkedSignal[T], LinkedDescriptor[T]],
    ]: ...  # Decorator factory

    @overload
    def __new__(
        cls, *, computation: Callable[[Any, S, Optional[PreviousState[S, T]]], T],
        equal: Optional[Callable[[T, T], bool]] = None,
    ) -> Callable[[Callable[[Any], S]], LinkedDescriptor[T]]: ...

    @overload
    def __new__(
        cls,
        computation_or_source: Union[Callable[..., T], ReadableSignal[U], None] = None,
        *,
        source: Optional[Union[ReadableSignal[U], Callable[[], U]]] = None,
        computation: Optional[Callable[[U, Optional[PreviousState[U, T]]], T]] = None,
        equal: Optional[Callable[[T, T], bool]] = None,
    ) -> LinkedSignal[T]: ...

    def __new__(
        cls,
        computation_or_source: Union[Callable[..., T], ReadableSignal[U], None] = None,
        source: Optional[Union[ReadableSignal[U], Callable[[], U]]] = None,
        computation: Optional[Callable[..., T]] = None,
        equal: Optional[Callable[[T, T], bool]] = None,
    ) -> Any:
        if (
            (equal is not None or computation is not None)
            and computation_or_source is None
            and source is None
        ):
            # Parameterized decorator: @linked(equal=..., computation=...).
            # The decorated function is the source; for methods, the computation
            # receives the owner first: computation(self, source, previous).
            def decorator(
                f: Union[Callable[[], T], Callable[[Any], T]],
            ) -> Union[LinkedSignal[T], LinkedDescriptor[T]]:
                return cls(f, equal=equal, computation=computation)

            return decorator

        if (
            computation_or_source is not None
            and callable(computation_or_source)
            and is_instance_method(computation_or_source)
            and source is None
        ):
            return LinkedDescriptor(
                cast(Callable[[Any], T], computation_or_source), equal=equal,
                computation=cast(Any, computation),
            )

        # Direct call: linked(lambda: ...) or @linked decorator
        return super().__new__(cls)

    def __init__(
        self,
        computation_or_source: Union[Callable[..., T], ReadableSignal[U], None] = None,
        *,
        source: Optional[Union[ReadableSignal[U], Callable[[], U]]] = None,
        computation: Optional[Callable[..., T]] = None,
        equal: Optional[Callable[[T, T], bool]] = None,
    ):
        # A parameterized decorator uses its decorated function as the source.
        if source is None and computation is not None and callable(computation_or_source):
            source = cast(Callable[[], U], computation_or_source)
        # Determine pattern
        if source is not None and computation is not None:
            # Advanced pattern
            self._simple_pattern = False
            if isinstance(source, _SignalBase):
                self._source = source
                self._source_fn = cast(Callable[[], U], source.get)
            elif callable(source):
                self._source = None
                self._source_fn = cast(Callable[[], U], source)

            self._computation = computation
        elif computation_or_source is not None and callable(computation_or_source):
            # Simple pattern
            self._simple_pattern = True
            self._source = None
            self._source_fn = None
            self._computation = computation_or_source
        else:
            raise ValueError(
                "LinkedSignal requires either:\n"
                "1. A computation function: linked(lambda: source())\n"
                "2. Source and computation: linked(source=signal, computation=func)"
            )

        # Previous-source tracking (prev.value comes from ComputeSignal _value)
        self._previous_source: Optional[Any] = None
        self._has_previous = False
        self._previous_value: Optional[T] = None

        # Compute function used by ComputeSignal
        def _compute() -> T:
            if self._simple_pattern:
                return cast(Callable[[], T], self._computation)()

            if self._source_fn is None:
                raise RuntimeError("Source function is None in advanced pattern")

            # ComputeSignal stores exceptions in _value after a failed attempt.
            # Keep the last successful value (including a manual override) for recovery.
            if self._has_previous and self._last_error is None:
                self._previous_value = cast(T, self._value)
            src_val = self._source_fn()  # tracked

            prev_state: Optional[PreviousState[Any, T]] = None
            if self._has_previous:
                prev_state = PreviousState(cast(T, self._previous_value), self._previous_source)

            # Only the source is a dependency, so the computation's reads are
            # not tracked. Unlike an explicit untracked() block, it stays a
            # computation: writes are still rejected.
            prev_consumer = graph.set_active_consumer(None)
            try:
                result = cast(
                    Callable[[Any, Optional[PreviousState[Any, T]]], T], self._computation
                )(src_val, prev_state)
            finally:
                graph.set_active_consumer(prev_consumer)

            self._previous_source = src_val
            self._previous_value = result
            self._has_previous = True
            return result

        super().__init__(_compute, equal=equal)
        # Recomputation and manual writes both replace the value, so they share
        # one lock; this also makes update() a single atomic operation.
        self._lock = self._computation_lock
        debug_log(
            lambda: f"LinkedSignal created with simple_pattern={self._simple_pattern}"
        )

    def __repr__(self) -> str:
        try:
            # Compute/display value lazily without capturing dependencies
            with untracked():
                val = super().get()
            return f"LinkedSignal(value={repr(val)})"
        except Exception as e:
            return f"LinkedSignal(error_displaying_value: {str(e)})"

    def __call__(self) -> T:
        return self.get()

    def set(self, new_value: T, /) -> None:
        """Override the linked value until the source changes again.

        Like Angular, pending source changes are applied first, so the written
        value is current and is not replaced by the next read. Writing also
        clears an error state.
        """
        debug_log(lambda: f"LinkedSignal manual set() called with value: {new_value}")
        _assert_writable()  # before refreshing: a rejected write must not evaluate
        if self._lock is not None:
            with self._lock:
                targets = self._refresh_and_override(new_value)
        else:
            targets = self._refresh_and_override(new_value)
        if targets is not None:
            self._notify_targets(targets)

    def update(self, update_fn: Callable[[T], T]) -> None:
        """Override with ``update_fn(current)``, where current is up to date.

        Refreshing, calling ``update_fn`` and writing happen under one lock, so
        concurrent updates from several threads are not lost.
        """
        _assert_writable()  # before calling update_fn: a rejected write runs nothing
        if self._lock is not None:
            with self._lock:
                targets = self._refresh_and_update(update_fn)
        else:
            targets = self._refresh_and_update(update_fn)
        if targets is not None:
            self._notify_targets(targets)

    def _refresh_and_override(self, new_value: T) -> Optional[list[graph._Consumer]]:
        self._refresh()
        return self._set_override(new_value)

    def _refresh_and_update(
        self, update_fn: Callable[[T], T]
    ) -> Optional[list[graph._Consumer]]:
        self._refresh()
        if self._flags & graph.HAS_ERROR:
            assert self._last_error is not None
            raise self._last_error
        return self._set_override(update_fn(cast(T, self._value)))

    def _set_override(self, new_value: T) -> Optional[list[graph._Consumer]]:
        if self._flags & graph.HAS_ERROR:
            # Nothing to compare against: the error is replaced by the override.
            self._flags &= ~graph.HAS_ERROR
            self._last_error = None
            self._value = new_value
            self._version += 1
            graph.global_version += 1
            return graph.snapshot_targets(self)
        return super()._set_internal(new_value)

Linked = LinkedSignal


class _TypedLinkedFactory(Generic[T]):
    """Typed Linked decorator used by ``linked[T]`` syntax."""

    @overload
    def __call__(self, func: Callable[[], T], /) -> LinkedSignal[T]: ...

    @overload
    def __call__(self, func: Callable[[Any], T], /) -> LinkedDescriptor[T]: ...

    @overload
    def __call__(
        self, /, *, equal: Callable[[T, T], bool]
    ) -> Callable[
        [Union[Callable[[], T], Callable[[Any], T]]],
        Union[LinkedSignal[T], LinkedDescriptor[T]],
    ]: ...

    @overload
    def __call__(
        self, /, *, computation: Callable[[Any, S, Optional[PreviousState[S, T]]], T],
        equal: Optional[Callable[[T, T], bool]] = None,
    ) -> Callable[[Callable[[Any], S]], LinkedDescriptor[T]]: ...

    def __call__(
        self,
        func: Optional[Callable[..., object]] = None,
        /,
        *,
        equal: Optional[Callable[[T, T], bool]] = None,
        computation: Optional[Callable[..., T]] = None,
    ) -> Any:
        if func is not None:
            return cast(
                Union[LinkedSignal[T], LinkedDescriptor[T]],
                LinkedSignal(cast(Callable[..., T], func), equal=equal, computation=computation),
            )

        def decorator(
            f: Union[Callable[[], T], Callable[[Any], T]],
        ) -> Union[LinkedSignal[T], LinkedDescriptor[T]]:
            return cast(
                Union[LinkedSignal[T], LinkedDescriptor[T]],
                LinkedSignal(cast(Callable[..., T], f), equal=equal, computation=computation),
            )

        return decorator


class _LinkedFactory:
    """Lowercase decorator-friendly Linked factory."""

    @overload
    def __call__(self, func: Callable[[], T], /) -> LinkedSignal[T]: ...

    @overload
    def __call__(self, func: Callable[[Any], T], /) -> LinkedDescriptor[T]: ...

    @overload
    def __call__(
        self, func: Callable[[], T], /, *, equal: Callable[[T, T], bool]
    ) -> LinkedSignal[T]: ...

    @overload
    def __call__(
        self, func: Callable[[Any], T], /, *, equal: Callable[[T, T], bool]
    ) -> LinkedDescriptor[T]: ...

    @overload
    def __call__(
        self, /, *, equal: Callable[[T, T], bool]
    ) -> Callable[
        [Union[Callable[[], T], Callable[[Any], T]]],
        Union[LinkedSignal[T], LinkedDescriptor[T]],
    ]: ...

    @overload
    def __call__(
        self, *, computation: Callable[[Any, S, Optional[PreviousState[S, T]]], T],
        equal: Optional[Callable[[T, T], bool]] = None,
    ) -> Callable[[Callable[[Any], S]], LinkedDescriptor[T]]: ...

    @overload
    def __call__(
        self,
        computation_or_source: Union[Callable[..., T], ReadableSignal[U], None] = None,
        *,
        source: Optional[Union[ReadableSignal[U], Callable[[], U]]] = None,
        computation: Optional[Callable[[U, Optional[PreviousState[U, T]]], T]] = None,
        equal: Optional[Callable[[T, T], bool]] = None,
    ) -> LinkedSignal[T]: ...

    def __call__(
        self,
        computation_or_source: Union[Callable[..., T], ReadableSignal[U], None] = None,
        *,
        source: Optional[Union[ReadableSignal[U], Callable[[], U]]] = None,
        computation: Optional[Callable[..., T]] = None,
        equal: Optional[Callable[[T, T], bool]] = None,
    ) -> Any:
        return LinkedSignal(
            computation_or_source,
            source=source,
            computation=computation,
            equal=equal,
        )

    @overload
    def __getitem__(self, value_type: type[T]) -> _TypedLinkedFactory[T]: ...

    @overload
    def __getitem__(self, value_type: object) -> _TypedLinkedFactory[Any]: ...

    def __getitem__(self, value_type: object) -> _TypedLinkedFactory[Any]:
        del value_type
        return _TypedLinkedFactory()


linked: _LinkedFactory = _LinkedFactory()
