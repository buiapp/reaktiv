"""Signals for Python - inspired by Angular Signals / SolidJS. Reactive Declarative State Management Library for Python - automatic dependency tracking and reactive updates for your application state."""

from .context import untracked
from .scheduler import batch
from .signal import Signal, Computed, computed, ComputeSignal, ReadonlySignal
from .linked import LinkedSignal, Linked, linked, PreviousState
from .effect import Effect, effect
from .model import ReactiveModel, field
from .utils import to_async_iter
from .thread_safety import set_thread_safety, is_thread_safety_enabled
from .protocols import ReadableSignal, WritableSignal
from .resource import (
    Resource,
    resource,
    ResourceStatus,
    ResourceLoaderParams,
    PreviousResourceState,
    ResourceSnapshot,
)

from typing import TypeVar

T = TypeVar("T")


__version__ = "0.23.0"
__all__ = [
    "Signal",
    "ReadonlySignal",
    "ComputeSignal",
    "Computed",
    "computed",
    "Effect",
    "effect",
    "ReactiveModel",
    "field",
    "LinkedSignal",
    "Linked",
    "linked",
    "PreviousState",
    "ReadableSignal",
    "WritableSignal",
    "Resource",
    "resource",
    "ResourceStatus",
    "ResourceLoaderParams",
    "PreviousResourceState",
    "ResourceSnapshot",    
    "batch",
    "untracked",
    "to_async_iter",
    "set_thread_safety",
    "is_thread_safety_enabled",
]
