"""LinkedSignal."""

from __future__ import annotations

from typing import Generic, TypeVar, Optional, Callable, Union, cast, Any, overload

from typing_extensions import Self

from .signal import Signal, ComputeSignal, debug_log
from .context import untracked

T = TypeVar("T")
U = TypeVar("U")


class PreviousState(Generic[T]):
    """Container for previous state in LinkedSignal computations.
    
    Attributes:
        value: The previous value of the LinkedSignal
        source: The previous value of the source signal
    """

    __slots__ = ("value", "source")

    def __init__(self, value: T, source: T):
        """Initialize previous state with value and source."""
        self.value = value
        self.source = source


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
        from reaktiv import Signal, LinkedSignal
        
        fahrenheit = Signal(32)
        
        # Celsius automatically computes from Fahrenheit
        celsius = LinkedSignal(lambda: (fahrenheit() - 32) * 5/9)
        
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
        from reaktiv import Signal, LinkedSignal, Effect
        
        # Server data
        server_name = Signal("John Doe")
        
        # Form input linked to server data
        input_value = LinkedSignal(lambda: server_name())
        
        # Track changes (keep reference to prevent GC)
        effect = Effect(lambda: print(f"Input: {input_value()}"))
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
        from reaktiv import Signal, LinkedSignal, PreviousState
        
        total_pages = Signal(10)
        
        def clamp_page(page_num, prev):
            max_page = total_pages()
            
            if max_page == 0:
                return None
            
            # First time or source changed - use default
            if prev is None or prev.source != max_page:
                return 1
            
            # Clamp to valid range
            return max(1, min(prev.value, max_page))
        
        current_page = LinkedSignal(
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
        from reaktiv import Signal, LinkedSignal
        
        source = Signal(0)
        
        @LinkedSignal
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
    )

    @overload
    def __new__(
        cls,
        func: Callable[[], T],
        /,
    ) -> Self: ...

    @overload
    def __new__(
        cls,
        func: Callable[[], T],
        /,
        *,
        equal: Callable[[T, T], bool],
    ) -> Self: ...

    @overload
    def __new__(
        cls,
        /,
        *,
        equal: Callable[[T, T], bool],
    ) -> Callable[[Callable[[], T]], Self]: ...  # Decorator factory

    @overload
    def __new__(
        cls,
        computation_or_source: Union[Callable[[], T], Signal[U], None] = None,
        *,
        source: Optional[Union[Signal[U], Callable[[], U]]] = None,
        computation: Optional[Callable[[U, Optional[PreviousState[T]]], T]] = None,
        equal: Optional[Callable[[T, T], bool]] = None,
    ) -> Self: ...

    def __new__(
        cls,
        computation_or_source: Union[Callable[[], T], Signal[U], None] = None,
        source: Optional[Union[Signal[U], Callable[[], U]]] = None,
        computation: Optional[Callable[[U, Optional[PreviousState[T]]], T]] = None,
        equal: Optional[Callable[[T, T], bool]] = None,
    ) -> Union[Self, Callable[[Callable[[], T]], Self]]:
        if (
            equal is not None
            and computation_or_source is None
            and source is None
            and computation is None
        ):
            # Parameterized decorator: @Linked(equal=...)
            def decorator(f: Callable[[], T]) -> Self:
                return cls(f, equal=equal)

            return decorator

        # Direct call: Linked(lambda: ...) or @Linked decorator
        return super().__new__(cls)

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
        # If never computed, trigger initial computation to establish dependencies
        if self._version == 0:
            super()._refresh()
        super()._set_internal(new_value)

    def update(self, update_fn: Callable[[T], T]) -> None:
        self.set(update_fn(cast(T, self._value)))


Linked = LinkedSignal
