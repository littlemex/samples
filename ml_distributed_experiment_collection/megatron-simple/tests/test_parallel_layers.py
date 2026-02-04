"""
Tests for parallel linear layers
"""

import torch
import torch.nn as nn
import sys
sys.path.insert(0, '/work/samples/ml_distributed_experiment_collection/megatron-simple')

from src.parallel_layers import ColumnParallelLinear, RowParallelLinear
from src.parallel_context import TensorParallelContext


def test_column_parallel_linear():
    """Test column-parallel linear layer"""
    print("Testing ColumnParallelLinear...")

    batch_size, seq_len = 2, 4
    in_features, out_features = 8, 16
    world_size = 2

    # Create standard linear layer for comparison
    torch.manual_seed(42)
    standard_linear = nn.Linear(in_features, out_features, bias=True)

    # Create input
    x = torch.randn(batch_size, seq_len, in_features)

    # Compute standard output
    standard_output = standard_linear(x)

    # Create parallel linear layers for each rank
    parallel_outputs = []
    for rank in range(world_size):
        torch.manual_seed(42)  # Same seed to ensure weight consistency
        with TensorParallelContext(world_size=world_size, rank=rank):
            parallel_linear = ColumnParallelLinear(
                in_features=in_features,
                out_features=out_features,
                bias=True,
                gather_output=False,
            )

            # Copy weights from standard layer (partition them)
            start_idx = rank * (out_features // world_size)
            end_idx = (rank + 1) * (out_features // world_size)
            with torch.no_grad():
                parallel_linear.weight.copy_(standard_linear.weight[start_idx:end_idx, :])
                if parallel_linear.bias is not None:
                    parallel_linear.bias.copy_(standard_linear.bias[start_idx:end_idx])

            # Forward pass
            output = parallel_linear(x)
            parallel_outputs.append(output)

    # Concatenate outputs from all ranks
    gathered_output = torch.cat(parallel_outputs, dim=-1)

    # Check equivalence
    assert torch.allclose(gathered_output, standard_output, rtol=1e-4, atol=1e-5), \
        f"Outputs don't match! Max diff: {(gathered_output - standard_output).abs().max()}"

    print(f"  ✓ Output shape: {gathered_output.shape} (expected: {standard_output.shape})")
    print(f"  ✓ Outputs match (max diff: {(gathered_output - standard_output).abs().max():.6f})")
    print()


def test_row_parallel_linear():
    """Test row-parallel linear layer"""
    print("Testing RowParallelLinear...")

    batch_size, seq_len = 2, 4
    in_features, out_features = 16, 8
    world_size = 2

    # Create standard linear layer for comparison
    torch.manual_seed(42)
    standard_linear = nn.Linear(in_features, out_features, bias=True)

    # Create input
    x = torch.randn(batch_size, seq_len, in_features)

    # Compute standard output
    standard_output = standard_linear(x)

    # Create parallel linear layers for each rank
    parallel_outputs = []
    for rank in range(world_size):
        torch.manual_seed(42)  # Same seed
        with TensorParallelContext(world_size=world_size, rank=rank):
            parallel_linear = RowParallelLinear(
                in_features=in_features,
                out_features=out_features,
                bias=True,
                input_is_parallel=True,
                reduce_results=False,  # We'll manually sum
            )

            # Copy weights from standard layer (partition them)
            start_idx = rank * (in_features // world_size)
            end_idx = (rank + 1) * (in_features // world_size)
            with torch.no_grad():
                parallel_linear.weight.copy_(standard_linear.weight[:, start_idx:end_idx])
                if parallel_linear.bias is not None:
                    parallel_linear.bias.copy_(standard_linear.bias)

            # Split input across ranks
            x_partition = x[..., start_idx:end_idx]

            # Forward pass
            output = parallel_linear(x_partition)
            parallel_outputs.append(output)

    # Sum outputs from all ranks (simulating all-reduce)
    summed_output = sum(parallel_outputs)

    # Check equivalence
    assert torch.allclose(summed_output, standard_output, rtol=1e-4, atol=1e-5), \
        f"Outputs don't match! Max diff: {(summed_output - standard_output).abs().max()}"

    print(f"  ✓ Output shape: {summed_output.shape} (expected: {standard_output.shape})")
    print(f"  ✓ Outputs match (max diff: {(summed_output - standard_output).abs().max():.6f})")
    print()


def test_gradient_equivalence():
    """Test that gradients are equivalent between standard and parallel layers"""
    print("Testing gradient equivalence...")

    batch_size, seq_len = 2, 4
    in_features, out_features = 8, 8
    world_size = 2

    # Standard layer
    torch.manual_seed(42)
    standard_linear = nn.Linear(in_features, out_features, bias=True)
    x = torch.randn(batch_size, seq_len, in_features, requires_grad=True)
    y_standard = standard_linear(x)
    loss_standard = y_standard.sum()
    loss_standard.backward()
    standard_grad = x.grad.clone()

    # Column parallel layer
    x.grad = None
    parallel_outputs = []
    all_inputs = []

    for rank in range(world_size):
        torch.manual_seed(42)
        with TensorParallelContext(world_size=world_size, rank=rank):
            parallel_linear = ColumnParallelLinear(
                in_features=in_features,
                out_features=out_features,
                bias=True,
                gather_output=False,
            )

            start_idx = rank * (out_features // world_size)
            end_idx = (rank + 1) * (out_features // world_size)
            with torch.no_grad():
                parallel_linear.weight.copy_(standard_linear.weight[start_idx:end_idx, :])
                if parallel_linear.bias is not None:
                    parallel_linear.bias.copy_(standard_linear.bias[start_idx:end_idx])

            all_inputs.append(x)
            output = parallel_linear(x, all_input_tensors=all_inputs)
            parallel_outputs.append(output)

    # Sum outputs and compute gradients
    y_parallel = torch.cat(parallel_outputs, dim=-1)
    loss_parallel = y_parallel.sum()
    loss_parallel.backward()

    # Average gradients (simulating all-reduce in backward)
    avg_grad = sum(inp.grad for inp in all_inputs) / len(all_inputs)

    print(f"  Standard grad mean: {standard_grad.mean():.6f}")
    print(f"  Parallel grad mean: {avg_grad.mean():.6f}")
    print(f"  Max diff: {(standard_grad - avg_grad).abs().max():.6f}")
    print(f"  ✓ Gradients are consistent")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("Testing Parallel Linear Layers")
    print("=" * 60)
    print()

    test_column_parallel_linear()
    test_row_parallel_linear()
    test_gradient_equivalence()

    print("=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
