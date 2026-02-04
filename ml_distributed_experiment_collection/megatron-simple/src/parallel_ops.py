"""
Custom Autograd Functions for Tensor Parallelism

This module implements the f and g operators from the Megatron-LM paper:
- f operator: Identity in forward, All-Reduce in backward
- g operator: All-Reduce in forward, Identity in backward

These operators enable efficient tensor parallelism by minimizing communication.
"""

import torch
from typing import Any, List


class IdentityForward_AllReduceBackward(torch.autograd.Function):
    """
    f operator from Megatron-LM paper.

    Forward pass: Identity (no operation)
    Backward pass: All-Reduce (average gradients across all ranks)

    This is used before column-parallel layers to ensure gradient synchronization.
    """

    @staticmethod
    def forward(ctx: Any, input_tensor: torch.Tensor, tensors_for_all_reduce: List[torch.Tensor]) -> torch.Tensor:
        """
        Forward pass - simply return the input tensor.

        Args:
            ctx: Context object to save information for backward pass
            input_tensor: Input tensor from current rank
            tensors_for_all_reduce: List to collect tensors from all ranks (modified in-place)

        Returns:
            Same as input_tensor (identity operation)
        """
        ctx.tensors_for_all_reduce = tensors_for_all_reduce
        return input_tensor

    @staticmethod
    def backward(ctx: Any, grad_output: torch.Tensor) -> tuple:
        """
        Backward pass - all-reduce the gradients.

        Args:
            ctx: Context object with saved information
            grad_output: Gradient from upstream

        Returns:
            Tuple of (reduced_gradient, None)
        """
        # In simulation, we need to average gradients across all ranks
        tensors = ctx.tensors_for_all_reduce
        if len(tensors) > 0:
            # Average across all ranks
            stacked = torch.stack(tensors, dim=0)
            reduced_grad = stacked.mean(dim=0)
        else:
            # Single rank case
            reduced_grad = grad_output

        return reduced_grad, None


class AllReduceForward_IdentityBackward(torch.autograd.Function):
    """
    g operator from Megatron-LM paper.

    Forward pass: All-Reduce (sum activations across all ranks)
    Backward pass: Identity (no operation)

    This is used after row-parallel layers to aggregate outputs.
    """

    @staticmethod
    def forward(ctx: Any, input_tensor: torch.Tensor, tensors_for_all_reduce: List[torch.Tensor]) -> torch.Tensor:
        """
        Forward pass - all-reduce the input tensor.

        Args:
            ctx: Context object to save information for backward pass
            input_tensor: Input tensor from current rank
            tensors_for_all_reduce: List of tensors from all ranks (for simulation)

        Returns:
            Reduced tensor (sum across all ranks)
        """
        if len(tensors_for_all_reduce) > 1:
            # Sum across all ranks (note: sum, not average, as per Megatron paper)
            stacked = torch.stack(tensors_for_all_reduce, dim=0)
            return stacked.sum(dim=0)
        else:
            # Single rank case
            return input_tensor

    @staticmethod
    def backward(ctx: Any, grad_output: torch.Tensor) -> tuple:
        """
        Backward pass - simply return the gradient.

        Args:
            ctx: Context object with saved information
            grad_output: Gradient from upstream

        Returns:
            Tuple of (grad_output, None)
        """
        return grad_output, None


def copy_to_tensor_parallel_region(input_tensor: torch.Tensor, all_tensors: List[torch.Tensor]) -> torch.Tensor:
    """
    Apply f operator: Identity in forward, All-Reduce in backward.

    This is used at the beginning of tensor parallel regions to ensure
    gradients are synchronized across ranks.

    Args:
        input_tensor: Input tensor from current rank
        all_tensors: List to collect gradients from all ranks during backward

    Returns:
        Same tensor (identity in forward)
    """
    return IdentityForward_AllReduceBackward.apply(input_tensor, all_tensors)


def reduce_from_tensor_parallel_region(input_tensor: torch.Tensor, all_tensors: List[torch.Tensor]) -> torch.Tensor:
    """
    Apply g operator: All-Reduce in forward, Identity in backward.

    This is used at the end of tensor parallel regions to aggregate
    outputs from all ranks.

    Args:
        input_tensor: Input tensor from current rank
        all_tensors: List of tensors from all ranks (for forward all-reduce)

    Returns:
        Reduced tensor (sum across all ranks)
    """
    return AllReduceForward_IdentityBackward.apply(input_tensor, all_tensors)


def gather_from_tensor_parallel_region(input_tensor: torch.Tensor, all_tensors: List[torch.Tensor], dim: int = -1) -> torch.Tensor:
    """
    Gather tensors from all ranks along a specified dimension.

    This is used when we need the full tensor (e.g., for output layer).

    Args:
        input_tensor: Input tensor from current rank
        all_tensors: List of tensors from all ranks
        dim: Dimension along which to concatenate

    Returns:
        Concatenated tensor
    """
    if len(all_tensors) == 1:
        return input_tensor
    return torch.cat(all_tensors, dim=dim)
