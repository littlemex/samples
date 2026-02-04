"""
Tensor Parallel Linear Layers

This module implements column-parallel and row-parallel linear layers
as described in the Megatron-LM paper.
"""

import torch
import torch.nn as nn
from typing import Optional
import math

from .parallel_context import get_tensor_parallel_world_size, get_tensor_parallel_rank
from .parallel_ops import copy_to_tensor_parallel_region, reduce_from_tensor_parallel_region


class ColumnParallelLinear(nn.Module):
    """
    Column-parallel linear layer.

    The weight matrix is partitioned along the output dimension (columns).
    Each rank holds a slice of the weight matrix.

    For input X and weight W, output Y = XW where W is column-partitioned:
    W = [W_0, W_1, ..., W_n] where n = world_size

    Each rank computes: Y_i = X @ W_i

    Communication pattern:
    - Forward: No communication (unless gather_output=True)
    - Backward: All-Reduce gradients via f operator
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        bias: bool = True,
        gather_output: bool = False,
        init_method: Optional[callable] = None,
    ):
        """
        Initialize column-parallel linear layer.

        Args:
            in_features: Size of input features
            out_features: Size of output features (will be divided by world_size)
            bias: If True, add bias term
            gather_output: If True, gather outputs from all ranks
            init_method: Weight initialization method
        """
        super().__init__()

        self.in_features = in_features
        self.out_features = out_features
        self.gather_output = gather_output

        # Get tensor parallel configuration
        world_size = get_tensor_parallel_world_size()
        self.world_size = world_size

        # Ensure output features can be divided by world size
        assert out_features % world_size == 0, \
            f"out_features ({out_features}) must be divisible by world_size ({world_size})"

        self.out_features_per_partition = out_features // world_size

        # Create weight parameter (only holds a slice)
        self.weight = nn.Parameter(torch.empty(self.out_features_per_partition, in_features))

        # Create bias parameter (only for this partition)
        if bias:
            self.bias = nn.Parameter(torch.empty(self.out_features_per_partition))
        else:
            self.register_parameter('bias', None)

        # Initialize weights
        if init_method is None:
            # Use standard Kaiming initialization
            nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
            if self.bias is not None:
                fan_in, _ = nn.init._calculate_fan_in_and_fan_out(self.weight)
                bound = 1 / math.sqrt(fan_in) if fan_in > 0 else 0
                nn.init.uniform_(self.bias, -bound, bound)
        else:
            init_method(self.weight)
            if self.bias is not None:
                self.bias.data.zero_()

    def forward(
        self,
        input_tensor: torch.Tensor,
        all_input_tensors: Optional[list] = None,
        all_output_tensors: Optional[list] = None,
    ) -> torch.Tensor:
        """
        Forward pass of column-parallel linear layer.

        Args:
            input_tensor: Input tensor of shape [..., in_features]
            all_input_tensors: List to collect input tensors from all ranks (for f operator)
            all_output_tensors: List to collect output tensors from all ranks (for gathering)

        Returns:
            Output tensor of shape [..., out_features_per_partition] or [..., out_features] if gather_output=True
        """
        # Apply f operator: identity in forward, all-reduce in backward
        if all_input_tensors is not None:
            input_parallel = copy_to_tensor_parallel_region(input_tensor, all_input_tensors)
        else:
            input_parallel = input_tensor

        # Linear transformation: Y = XW^T + b
        output = torch.matmul(input_parallel, self.weight.t())

        if self.bias is not None:
            output = output + self.bias

        # Gather outputs if requested
        if self.gather_output and all_output_tensors is not None and len(all_output_tensors) > 0:
            output = torch.cat(all_output_tensors, dim=-1)

        return output


class RowParallelLinear(nn.Module):
    """
    Row-parallel linear layer.

    The weight matrix is partitioned along the input dimension (rows).
    Each rank holds a slice of the weight matrix.

    For input X and weight W, output Y = XW where W is row-partitioned:
    W = [W_0; W_1; ...; W_n] where n = world_size

    Input X is also partitioned: X = [X_0; X_1; ...; X_n]

    Each rank computes: Y_i = X_i @ W_i
    Final output: Y = sum_i(Y_i) via all-reduce

    Communication pattern:
    - Forward: All-Reduce outputs via g operator
    - Backward: No communication (gradients are already local)
    """

    def __init__(
        self,
        in_features: int,
        out_features: int,
        bias: bool = True,
        input_is_parallel: bool = True,
        reduce_results: bool = True,
        init_method: Optional[callable] = None,
    ):
        """
        Initialize row-parallel linear layer.

        Args:
            in_features: Size of input features (will be divided by world_size)
            out_features: Size of output features
            bias: If True, add bias term (only on rank 0 to avoid duplication)
            input_is_parallel: If True, input is already partitioned
            reduce_results: If True, reduce outputs across ranks
            init_method: Weight initialization method
        """
        super().__init__()

        self.in_features = in_features
        self.out_features = out_features
        self.input_is_parallel = input_is_parallel
        self.reduce_results = reduce_results

        # Get tensor parallel configuration
        world_size = get_tensor_parallel_world_size()
        rank = get_tensor_parallel_rank()
        self.world_size = world_size
        self.rank = rank

        # Ensure input features can be divided by world size
        assert in_features % world_size == 0, \
            f"in_features ({in_features}) must be divisible by world_size ({world_size})"

        self.in_features_per_partition = in_features // world_size

        # Create weight parameter (only holds a slice)
        self.weight = nn.Parameter(torch.empty(out_features, self.in_features_per_partition))

        # Create bias parameter (only on rank 0 to avoid duplication)
        if bias:
            if rank == 0:
                self.bias = nn.Parameter(torch.empty(out_features))
            else:
                self.register_parameter('bias', None)
        else:
            self.register_parameter('bias', None)

        # Initialize weights
        if init_method is None:
            # Use standard Kaiming initialization
            nn.init.kaiming_uniform_(self.weight, a=math.sqrt(5))
            if self.bias is not None:
                fan_in, _ = nn.init._calculate_fan_in_and_fan_out(self.weight)
                bound = 1 / math.sqrt(fan_in) if fan_in > 0 else 0
                nn.init.uniform_(self.bias, -bound, bound)
        else:
            init_method(self.weight)
            if self.bias is not None:
                self.bias.data.zero_()

    def forward(
        self,
        input_tensor: torch.Tensor,
        all_output_tensors: Optional[list] = None,
    ) -> torch.Tensor:
        """
        Forward pass of row-parallel linear layer.

        Args:
            input_tensor: Input tensor of shape [..., in_features_per_partition]
            all_output_tensors: List to collect output tensors from all ranks (for g operator)

        Returns:
            Output tensor of shape [..., out_features]
        """
        # Linear transformation: Y = XW^T
        output = torch.matmul(input_tensor, self.weight.t())

        # Apply g operator: all-reduce in forward, identity in backward
        if self.reduce_results and all_output_tensors is not None:
            output = reduce_from_tensor_parallel_region(output, all_output_tensors)

        # Add bias (only on rank 0)
        if self.bias is not None:
            output = output + self.bias

        return output
