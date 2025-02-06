"""
Reactive signals for Python with first-class async support
"""

from .core import Signal, ComputeSignal, Effect, batch

__version__ = "0.6.0"
__all__ = ["Signal", "ComputeSignal", "Effect", "batch"]