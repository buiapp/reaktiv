import pytest
from unittest.mock import Mock, call
from reaktiv import Signal, ComputeSignal, Effect

import reaktiv.core as rc

rc.set_debug(True) 

@pytest.mark.asyncio
async def test_lazy_initialization():
    """Test that computation only happens on first access"""
    compute_fn = Mock(return_value=42)
    computed = ComputeSignal(compute_fn)
    
    # Computation shouldn't happen at creation
    compute_fn.assert_not_called()
    
    # First access triggers computation
    assert computed.get() == 42
    compute_fn.assert_called_once()
    
    # Subsequent access uses cached value
    assert computed.get() == 42
    compute_fn.assert_called_once()  # Still only one call

def test_dependency_tracking():
    """Test dependencies are only tracked after first access"""
    source = Signal(10)
    compute_fn = Mock(side_effect=lambda: source.get() * 2)
    computed = ComputeSignal(compute_fn)
    
    # No dependencies before access
    assert len(computed._dependencies) == 0
    
    # First access establishes dependencies
    assert computed.get() == 20
    compute_fn.assert_called_once()
    assert len(computed._dependencies) == 1
    assert source in computed._dependencies

def test_recomputation_on_dependency_change():
    """Test value updates only when accessed after change"""
    source = Signal(5)
    computed = ComputeSignal(lambda: source.get() * 3)
    
    # Initial access
    assert computed.get() == 15
    
    # Change dependency
    source.set(10)
    
    # Value should update on next access
    assert computed.get() == 30

def test_multiple_dependencies():
    """Test complex dependency graph only computes when accessed"""
    a = Signal(1)
    b = Signal(2)
    compute_fn = Mock(side_effect=lambda: a.get() + b.get())
    computed = ComputeSignal(compute_fn)
    
    # No computation before access
    compute_fn.assert_not_called()
    
    # First access
    assert computed.get() == 3
    compute_fn.assert_called_once()
    
    # Modify either dependency
    a.set(10)
    b.set(20)
    
    # No recomputation until accessed
    compute_fn.assert_called_once()
    
    # Access triggers recomputation
    assert computed.get() == 30
    assert compute_fn.call_count == 2

def test_error_handling():
    """Test errors in computation are handled and cached"""
    compute_fn = Mock(side_effect=RuntimeError("Oops"))
    computed = ComputeSignal(compute_fn, default=0)
    
    # First access should catch error and return default
    assert computed.get() == 0
    compute_fn.assert_called_once()
    
    # Subsequent access continues returning cached value
    assert computed.get() == 0
    compute_fn.assert_called_once()

def test_nested_computations():
    """Test nested computed signals only compute when needed"""
    a = Signal(1)
    compute_b_fn = Mock(side_effect=lambda: a.get() * 2)
    b = ComputeSignal(compute_b_fn)
    compute_c_fn = Mock(side_effect=lambda: b.get() + 5)
    c = ComputeSignal(compute_c_fn)
    
    # No computations yet
    compute_b_fn.assert_not_called()
    compute_c_fn.assert_not_called()
    
    # Access outer computed signal
    assert c.get() == 7
    
    # Both should be initialized now
    compute_b_fn.assert_called_once()
    compute_c_fn.assert_called_once()
    
    # Update source
    a.set(3)
    
    # No recomputations until access
    assert compute_b_fn.call_count == 1
    assert compute_c_fn.call_count == 1
    
    # Access should trigger recomputation
    assert c.get() == 11
    assert compute_b_fn.call_count == 2
    assert compute_c_fn.call_count == 2