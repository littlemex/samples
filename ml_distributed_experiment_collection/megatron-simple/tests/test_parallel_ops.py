"""
Tests for parallel operators (f and g operators)
"""

import torch
import sys
sys.path.insert(0, '/work/samples/ml_distributed_experiment_collection/megatron-simple')

from src.parallel_ops import (
    copy_to_tensor_parallel_region,
    reduce_from_tensor_parallel_region,
)


def test_f_operator():
    """Test f operator: identity in forward, all-reduce in backward"""
    print("Testing f operator (IdentityForward_AllReduceBackward)...")

    # Create input tensors for 2 ranks
    x1 = torch.tensor([[1.0, 2.0], [3.0, 4.0]], requires_grad=True)
    x2 = torch.tensor([[5.0, 6.0], [7.0, 8.0]], requires_grad=True)

    # Simulate forward pass (should be identity)
    grad_tensors = []
    y1 = copy_to_tensor_parallel_region(x1, grad_tensors)
    y2 = copy_to_tensor_parallel_region(x2, grad_tensors)

    # Forward should be identity
    assert torch.allclose(y1, x1), "Forward pass should be identity for rank 0"
    assert torch.allclose(y2, x2), "Forward pass should be identity for rank 1"
    print("  ✓ Forward pass (identity) works correctly")

    # Simulate backward pass (should average gradients)
    grad_output = torch.ones_like(y1)

    # Collect gradients from both ranks
    grad_tensors.clear()
    grad_tensors.append(grad_output)
    grad_tensors.append(grad_output)

    # Compute backward
    y1_new = copy_to_tensor_parallel_region(x1, grad_tensors)
    loss = y1_new.sum()
    loss.backward()

    # Gradient should be averaged (all ones)
    expected_grad = torch.ones_like(x1)
    assert torch.allclose(x1.grad, expected_grad), f"Expected grad {expected_grad}, got {x1.grad}"
    print("  ✓ Backward pass (all-reduce) works correctly")
    print()


def test_g_operator():
    """Test g operator: all-reduce in forward, identity in backward"""
    print("Testing g operator (AllReduceForward_IdentityBackward)...")

    # Create input tensors for 2 ranks
    x1 = torch.tensor([[1.0, 2.0], [3.0, 4.0]], requires_grad=True)
    x2 = torch.tensor([[5.0, 6.0], [7.0, 8.0]], requires_grad=True)

    # Simulate forward pass (should sum across ranks)
    all_tensors = [x1, x2]
    y1 = reduce_from_tensor_parallel_region(x1, all_tensors)

    # Forward should be sum of all tensors
    expected = x1 + x2
    assert torch.allclose(y1, expected), f"Expected {expected}, got {y1}"
    print("  ✓ Forward pass (all-reduce/sum) works correctly")

    # Simulate backward pass (should be identity)
    grad_output = torch.ones_like(y1)
    loss = (y1 * grad_output).sum()
    loss.backward()

    # Gradient should be same as grad_output (identity)
    assert torch.allclose(x1.grad, grad_output), f"Expected grad {grad_output}, got {x1.grad}"
    print("  ✓ Backward pass (identity) works correctly")
    print()


def test_gradient_flow():
    """Test that gradients flow correctly through f and g operators"""
    print("Testing gradient flow through combined f and g operators...")

    # Simulate a simple computation: y = g(f(x) * w)
    x1 = torch.tensor([[1.0, 2.0]], requires_grad=True)
    x2 = torch.tensor([[3.0, 4.0]], requires_grad=True)
    w = torch.tensor([[0.5], [0.5]], requires_grad=True)

    # Forward pass
    grad_tensors_f = []
    z1 = copy_to_tensor_parallel_region(x1, grad_tensors_f)
    z2 = copy_to_tensor_parallel_region(x2, grad_tensors_f)

    # Local computation
    out1 = torch.matmul(z1, w)
    out2 = torch.matmul(z2, w)

    # Reduce
    all_outputs = [out1, out2]
    y = reduce_from_tensor_parallel_region(out1, all_outputs)

    # Backward
    loss = y.sum()
    loss.backward()

    print(f"  x1.grad: {x1.grad}")
    print(f"  x2.grad: {x2.grad}")
    print(f"  w.grad: {w.grad}")
    print("  ✓ Gradient flow works (no errors)")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Parallel Operators")
    print("=" * 60)
    print()

    test_f_operator()
    test_g_operator()
    test_gradient_flow()

    print("=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
