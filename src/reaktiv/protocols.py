"""Common readable and writable signal interfaces."""

from __future__ import annotations
from typing import Protocol, TypeVar, Callable

T = TypeVar("T", covariant=True)
T_inv = TypeVar("T_inv")  # Invariant for WritableSignal


class ReadableSignal(Protocol[T]):
    """
    Common interface for all readable signals.
    
    This protocol defines the minimal interface that all signal types
    (Signal, ReadonlySignal, ComputeSignal, LinkedSignal) must implement.
    
    Usage:
        def consume_signal(sig: Readable[int]) -> int:
            return sig()  # Read the signal value
        
        # Works with any signal type:
        s = Signal(42)
        c = Computed(lambda: s() * 2)
        r = s.as_readonly()
        l = LinkedSignal(lambda: s())
        
        consume_signal(s)
        consume_signal(c)
        consume_signal(r)
        consume_signal(l)
    """

    def __call__(self) -> T:
        """
        Read the current value of the signal.
        
        This is the primary way to access signal values and automatically
        tracks dependencies in reactive contexts.
        
        Returns:
            The current value of the signal
        """
        ...

    def get(self) -> T:
        """
        Explicit method to read the current value.
        
        Equivalent to calling the signal as a function, but more explicit.
        Some users prefer this style.
        
        Returns:
            The current value of the signal
        """
        ...


class WritableSignal(ReadableSignal[T_inv], Protocol[T_inv]):
    """
    Common interface for all writable signals.
    
    This protocol extends Readable and adds mutation methods (set and update).
    Only writable signals (Signal, LinkedSignal) implement this interface.
    Read-only signals (ReadonlySignal, ComputeSignal) do not.
    
    Usage:
        def increment(sig: Writable[int]) -> None:
            sig.set(sig() + 1)
            # or: sig.update(lambda x: x + 1)
        
        # Works with writable signal types:
        s = Signal(42)
        l = LinkedSignal(lambda: 0)
        
        increment(s)
        increment(l)
        
        # Does NOT work with read-only signals:
        c = Computed(lambda: s() * 2)
        r = s.as_readonly()
        
        increment(c)  # Type error
        increment(r)  # Type error
    """

    def set(self, value: T_inv) -> None:
        """
        Directly set the signal to a new value.
        
        This will trigger reactive updates for any dependents.
        
        Args:
            value: The new value to set
        """
        ...

    def update(self, update_fn: Callable[[T_inv], T_inv]) -> None:
        """
        Update the signal's value based on its current value.
        
        This is useful for atomic updates where you need to read the
        current value and compute a new one based on it.
        
        Args:
            update_fn: A function that takes the current value and returns the new value
            
        Example:
            counter.update(lambda x: x + 1)  # Increment by 1
            name.update(lambda x: x.upper())  # Transform to uppercase
        """
        ...
