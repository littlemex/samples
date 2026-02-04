"""
Tensor Parallel Context for CPU Simulation

This module provides a context manager to simulate distributed GPU communication
on CPU. It maintains the current rank and world size, and provides methods for
collective operations like all-reduce and all-gather.
"""

from typing import List, Optional
import torch
from dataclasses import dataclass


@dataclass
class TensorParallelConfig:
    """Configuration for tensor parallel simulation."""
    world_size: int = 1  # Number of simulated GPUs
    rank: int = 0  # Current rank (0 to world_size-1)


# Global context for tensor parallelism
_TP_CONTEXT: Optional[TensorParallelConfig] = None


def initialize_tensor_parallel(world_size: int, rank: int) -> None:
    """
    Initialize the tensor parallel context.

    Args:
        world_size: Total number of simulated GPUs
        rank: Current rank (0 to world_size-1)
    """
    global _TP_CONTEXT
    assert 0 <= rank < world_size, f"Invalid rank {rank} for world_size {world_size}"
    _TP_CONTEXT = TensorParallelConfig(world_size=world_size, rank=rank)


def get_tensor_parallel_context() -> TensorParallelConfig:
    """Get the current tensor parallel context."""
    if _TP_CONTEXT is None:
        # Default to single GPU mode
        return TensorParallelConfig(world_size=1, rank=0)
    return _TP_CONTEXT


def get_tensor_parallel_world_size() -> int:
    """Get the world size for tensor parallelism."""
    return get_tensor_parallel_context().world_size


def get_tensor_parallel_rank() -> int:
    """Get the current rank for tensor parallelism."""
    return get_tensor_parallel_context().rank


def cleanup_tensor_parallel() -> None:
    """Clean up the tensor parallel context."""
    global _TP_CONTEXT
    _TP_CONTEXT = None


class TensorParallelContext:
    """
    Context manager for tensor parallel simulation.

    Usage:
        with TensorParallelContext(world_size=2, rank=0):
            # Code here runs with rank 0 of 2
            pass
    """

    def __init__(self, world_size: int, rank: int):
        self.world_size = world_size
        self.rank = rank
        self.prev_context = None

    def __enter__(self):
        self.prev_context = _TP_CONTEXT
        initialize_tensor_parallel(self.world_size, self.rank)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _TP_CONTEXT
        _TP_CONTEXT = self.prev_context


def all_reduce(tensor: torch.Tensor, tensors_from_all_ranks: List[torch.Tensor]) -> torch.Tensor:
    """
    Simulate all-reduce operation by averaging tensors from all ranks.

    In real distributed training, this would be a collective communication operation
    that sums tensors across all GPUs and distributes the result back.

    Args:
        tensor: Input tensor from current rank
        tensors_from_all_ranks: List of tensors from all ranks (for simulation)

    Returns:
        Reduced tensor (average across all ranks)
    """
    if len(tensors_from_all_ranks) == 1:
        return tensor

    # Sum all tensors and average
    stacked = torch.stack(tensors_from_all_ranks, dim=0)
    return stacked.mean(dim=0)


def all_gather(tensor: torch.Tensor, tensors_from_all_ranks: List[torch.Tensor], dim: int = -1) -> torch.Tensor:
    """
    Simulate all-gather operation by concatenating tensors from all ranks.

    Args:
        tensor: Input tensor from current rank
        tensors_from_all_ranks: List of tensors from all ranks (for simulation)
        dim: Dimension along which to concatenate

    Returns:
        Concatenated tensor
    """
    if len(tensors_from_all_ranks) == 1:
        return tensor

    return torch.cat(tensors_from_all_ranks, dim=dim)
