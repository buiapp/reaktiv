"""Tests for Effect weak reference behavior.

Effects are weakly referenced by signals, allowing them to be garbage collected
when there are no external strong references to them.
"""

import gc
import pytest
from reaktiv import Signal, Effect


def test_effect_without_reference_immediate_gc():
    """Effects without external references should be garbage collected immediately."""
    signal = Signal(0)
    effect_runs = []
    
    # Create effect without storing reference - should GC immediately after creation
    Effect(lambda: effect_runs.append(signal()))
    
    # Effect ran once during creation
    assert effect_runs == [0]
    
    # Effect should be GC'd, so changing signal doesn't trigger it
    signal.set(1)
    assert effect_runs == [0], "Effect should not run after being garbage collected"


def test_effect_with_reference_stays_alive():
    """Effects with external references should stay alive until reference is removed."""
    signal = Signal(0)
    effect_runs = []
    
    # Keep reference to effect
    effect = Effect(lambda: effect_runs.append(signal()))
    
    assert effect_runs == [0]
    
    # Effect should still be alive
    signal.set(1)
    assert effect_runs == [0, 1]
    
    signal.set(2)
    assert effect_runs == [0, 1, 2]
    
    # Remove reference and force garbage collection
    del effect
    gc.collect()
    
    # Effect should be GC'd now
    signal.set(3)
    assert effect_runs == [0, 1, 2], "Effect should not run after being garbage collected"


def test_multiple_effects_partial_gc():
    """Only effects with references should stay alive."""
    signal = Signal(0)
    runs_a = []
    runs_b = []
    
    # Effect A has a reference
    effect_a = Effect(lambda: runs_a.append(signal()))
    
    # Effect B has no reference
    Effect(lambda: runs_b.append(signal()))
    
    # Both ran initially
    assert runs_a == [0]
    assert runs_b == [0]
    
    # Effect A should still run, Effect B should be GC'd
    signal.set(1)
    assert runs_a == [0, 1], "Effect A should still be alive"
    assert runs_b == [0], "Effect B should be garbage collected"
    
    # Cleanup
    effect_a.dispose()


def test_effect_gc_cleans_up_edges():
    """When an effect is GC'd, it should clean up its edges from signals."""
    signal = Signal(0)
    
    # Create and GC an effect
    Effect(lambda: signal())
    gc.collect()
    
    # The signal's targets list should be empty or have no live effects
    # We can't directly access _targets, but we can verify behavior
    signal.set(1)  # Should not crash
    
    # Create a new effect with reference to verify signal still works
    new_effect_runs = []
    effect = Effect(lambda: new_effect_runs.append(signal()))
    assert new_effect_runs == [1]
    
    signal.set(2)
    assert new_effect_runs == [1, 2]
    
    effect.dispose()


def test_effect_dispose_prevents_future_runs():
    """Disposed effects should not run even if they have references."""
    signal = Signal(0)
    effect_runs = []
    
    effect = Effect(lambda: effect_runs.append(signal()))
    assert effect_runs == [0]
    
    signal.set(1)
    assert effect_runs == [0, 1]
    
    # Dispose the effect
    effect.dispose()
    
    signal.set(2)
    assert effect_runs == [0, 1], "Disposed effect should not run"


def test_effect_weakref_with_batching():
    """Weak references should work correctly with batching."""
    from reaktiv import batch
    
    signal1 = Signal(0)
    signal2 = Signal(0)
    effect_runs = []
    
    # Effect without reference
    Effect(lambda: effect_runs.append((signal1(), signal2())))
    assert effect_runs == [(0, 0)]
    
    # Batch update - effect is already GC'd
    with batch():
        signal1.set(1)
        signal2.set(1)
    
    assert effect_runs == [(0, 0)], "GC'd effect should not run in batch"


def test_effect_weakref_multiple_signals():
    """Effects depending on multiple signals should be properly GC'd."""
    signal1 = Signal(0)
    signal2 = Signal(0)
    effect_runs = []
    
    # Create effect depending on both signals, no reference
    Effect(lambda: effect_runs.append(signal1() + signal2()))
    assert effect_runs == [0]
    
    # Effect should be GC'd
    signal1.set(1)
    assert effect_runs == [0]
    
    signal2.set(1)
    assert effect_runs == [0]


def test_effect_weakref_with_computed():
    """Effects depending on computed signals should be properly GC'd."""
    from reaktiv import ComputeSignal
    
    signal = Signal(0)
    computed = ComputeSignal(lambda: signal() * 2)
    effect_runs = []
    
    # Effect without reference
    Effect(lambda: effect_runs.append(computed()))
    assert effect_runs == [0]
    
    # Effect should be GC'd
    signal.set(1)
    assert effect_runs == [0]
