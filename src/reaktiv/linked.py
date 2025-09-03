"""LinkedSignal."""

from typing import Generic, TypeVar, Optional, Callable, Union, cast, Any
from .signal import Signal, ComputeSignal, debug_log
from .context import untracked

T = TypeVar("T")
U = TypeVar("U")


class PreviousState(Generic[T]):
    """Container for previous state in LinkedSignal computations."""

    __slots__ = ("value", "source")

    def __init__(self, value: T, source: T):
        """Initialize previous state with value and source."""
        self.value = value
        self.source = source


class LinkedSignal(ComputeSignal[T], Generic[T]):
    """A writable signal that automatically resets when source signals change.

    Implementation based on ComputeSignal.
    """

    __slots__ = (
        "_source",
        "_source_fn",
        "_computation",
        "_previous_source",
        "_simple_pattern",
    )

    def __init__(
        self,
        computation_or_source: Union[Callable[[], T], Signal[U], None] = None,
        *,
        source: Optional[Union[Signal[U], Callable[[], U]]] = None,
        computation: Optional[Callable[[U, Optional[PreviousState[T]]], T]] = None,
        equal: Optional[Callable[[T, T], bool]] = None,
    ):
        # Determine pattern
        
        if source is not None and computation is not None:
            # Advanced pattern
            self._simple_pattern = False
            if isinstance(source, Signal):
                self._source = source
                self._source_fn = source.get
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
                "1. A computation function: LinkedSignal(lambda: source())\n"
                "2. Source and computation: LinkedSignal(source=signal, computation=func)"
            )

        # Previous-source tracking (prev.value comes from ComputeSignal _value)
        self._previous_source: Optional[Any] = None

        # Compute function used by ComputeSignal
        def _compute() -> T:
            if self._simple_pattern:
                return cast(Callable[[], T], self._computation)()

            if self._source_fn is None:
                raise RuntimeError("Source function is None in advanced pattern")

            src_val = self._source_fn()  # tracked

            prev_state: Optional[PreviousState[T]] = None
            try:
                prev_val = cast(Optional[T], self._value)
            except Exception:
                prev_val = None
            if prev_val is not None:
                prev_state = PreviousState(prev_val, cast(Any, self._previous_source))

            with untracked():
                result = cast(
                    Callable[[Any, Optional[PreviousState[T]]], T], self._computation
                )(src_val, prev_state)

            self._previous_source = src_val
            return result

        super().__init__(_compute, equal=equal)
        debug_log(f"LinkedSignal created with simple_pattern={self._simple_pattern}")

        # Eagerly compute once to establish dependencies and a baseline value.
        try:
            # Perform initial compute without creating external dependencies
            # (this only tracks internal sources for change detection).
            super()._refresh()
        except Exception:
            # Defer error surfacing to the first public get(); keep behavior lazy.
            pass

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

    def set(self, new_value: T) -> None:
        debug_log(f"LinkedSignal manual set() called with value: {new_value}")
        super()._set_internal(new_value)

    def update(self, update_fn: Callable[[T], T]) -> None:
        self.set(update_fn(cast(T, self._value)))
