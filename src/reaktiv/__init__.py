"""Signals for Python - inspired by Angular Signals / SolidJS. Reactive Declarative State Management Library for Python - automatic dependency tracking and reactive updates for your application state."""

from .core import (
    Signal,
    ComputeSignal,
    Effect,
    Computed,
    batch,
    untracked,
    signal,
    computed,
    effect,
)
from .utils import to_async_iter
from .operators import filter_signal, debounce_signal, throttle_signal, pairwise_signal

__version__ = "0.15.1"
__all__ = [
    "Signal",
    "ComputeSignal",
    "Computed",
    "Effect",
    "batch",
    "untracked",
    "to_async_iter",
    "filter_signal",
    "debounce_signal",
    "throttle_signal",
    "pairwise_signal",
    "signal",
    "computed",
    "effect",
]
