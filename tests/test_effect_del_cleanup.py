"""Test that Effect.__del__ runs cleanup functions on garbage collection."""

import gc
import weakref
from reaktiv import Signal, Effect


def test_cleanup_runs_on_gc():
    """Cleanup function should run when Effect is garbage collected."""
    cleanup_ran = []
    signal = Signal(0)
    
    def effect_fn():
        signal()
        def cleanup():
            cleanup_ran.append("cleanup executed")
        return cleanup
    
    # Create effect and immediately lose reference
    effect = Effect(effect_fn)
    effect_weakref = weakref.ref(effect)
    
    # Delete the effect and force garbage collection
    del effect
    gc.collect()
    
    # Verify effect was garbage collected
    assert effect_weakref() is None, "Effect should be GC'd"
    
    # Verify cleanup function ran
    assert len(cleanup_ran) == 1, "Cleanup should run on GC"
    assert cleanup_ran[0] == "cleanup executed"


def test_cleanup_with_on_cleanup_parameter():
    """Cleanup registered via on_cleanup should run on GC."""
    cleanup_ran = []
    signal = Signal(0)
    
    def effect_fn(on_cleanup):
        signal()
        on_cleanup(lambda: cleanup_ran.append("on_cleanup executed"))
    
    effect = Effect(effect_fn)
    effect_weakref = weakref.ref(effect)
    
    del effect
    gc.collect()
    
    assert effect_weakref() is None, "Effect should be GC'd"
    assert len(cleanup_ran) == 1, "on_cleanup should run on GC"
    assert cleanup_ran[0] == "on_cleanup executed"


def test_multiple_cleanups_all_run():
    """All cleanup functions should run on GC."""
    cleanup_ran = []
    signal = Signal(0)
    
    def effect_fn(on_cleanup):
        signal()
        on_cleanup(lambda: cleanup_ran.append("cleanup1"))
        on_cleanup(lambda: cleanup_ran.append("cleanup2"))
        on_cleanup(lambda: cleanup_ran.append("cleanup3"))
    
    effect = Effect(effect_fn)
    del effect
    gc.collect()
    
    assert len(cleanup_ran) == 3, "All cleanups should run"
    assert "cleanup1" in cleanup_ran
    assert "cleanup2" in cleanup_ran
    assert "cleanup3" in cleanup_ran


def test_cleanup_exception_doesnt_break_gc():
    """Exception in cleanup should not prevent GC."""
    cleanup_ran = []
    signal = Signal(0)
    
    def effect_fn():
        signal()
        def cleanup():
            cleanup_ran.append("before exception")
            raise ValueError("Cleanup error")
        return cleanup
    
    effect = Effect(effect_fn)
    effect_weakref = weakref.ref(effect)
    
    # Should not raise, even though cleanup raises
    del effect
    gc.collect()
    
    assert effect_weakref() is None, "Effect should still be GC'd"
    assert len(cleanup_ran) == 1, "Cleanup should have been attempted"


def test_cleanup_on_rerun_then_gc():
    """Cleanup should run on rerun, then again on GC."""
    cleanup_ran = []
    signal = Signal(0)
    
    def effect_fn():
        value = signal()
        def cleanup():
            cleanup_ran.append(f"cleanup for value {value}")
        return cleanup
    
    effect = Effect(effect_fn)
    
    # Trigger rerun - should run cleanup from first run
    signal.set(1)
    assert len(cleanup_ran) == 1, "First cleanup on rerun"
    assert cleanup_ran[0] == "cleanup for value 0"
    
    # GC should run cleanup from second run
    effect_weakref = weakref.ref(effect)
    del effect
    gc.collect()
    
    assert effect_weakref() is None, "Effect should be GC'd"
    assert len(cleanup_ran) == 2, "Second cleanup on GC"
    assert cleanup_ran[1] == "cleanup for value 1"


def test_dispose_then_gc_no_double_cleanup():
    """Calling dispose() then GC should not run cleanup twice."""
    cleanup_ran = []
    signal = Signal(0)
    
    def effect_fn():
        signal()
        def cleanup():
            cleanup_ran.append("cleanup")
        return cleanup
    
    effect = Effect(effect_fn)
    effect.dispose()
    
    assert len(cleanup_ran) == 1, "Cleanup runs on dispose"
    
    # GC should not run cleanup again
    del effect
    gc.collect()
    
    assert len(cleanup_ran) == 1, "Cleanup should not run twice"


def test_nested_effects_with_cleanup():
    """Nested effects with cleanup should all clean up properly."""
    outer_cleanup_ran = []
    inner_cleanup_ran = []
    signal = Signal(0)
    
    def outer_effect():
        signal()
        
        def inner_effect():
            signal()
            def inner_cleanup():
                inner_cleanup_ran.append("inner")
            return inner_cleanup
        
        # Inner effect is not stored, will be GC'd
        Effect(inner_effect)
        
        def outer_cleanup():
            outer_cleanup_ran.append("outer")
        return outer_cleanup
    
    outer = Effect(outer_effect)
    
    # Force GC of inner effect
    gc.collect()
    assert len(inner_cleanup_ran) == 1, "Inner cleanup should run on GC"
    
    # GC outer effect
    del outer
    gc.collect()
    assert len(outer_cleanup_ran) == 1, "Outer cleanup should run on GC"


def test_no_cleanup_function_no_error():
    """Effects without cleanup should GC cleanly."""
    signal = Signal(0)
    
    effect = Effect(lambda: signal())
    effect_weakref = weakref.ref(effect)
    
    # Should not raise
    del effect
    gc.collect()
    
    assert effect_weakref() is None, "Effect should be GC'd"
