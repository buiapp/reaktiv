"""Protocol types used across the library to avoid circular imports."""

from __future__ import annotations
from typing import Protocol


class DependencyTracker(Protocol):
    """Objects that can track dependencies on signals."""

    def add_dependency(self, signal: object) -> None: ...


class Subscriber(Protocol):
    """Objects that can subscribe to signals and receive notifications."""

    def notify(self) -> None: ...
