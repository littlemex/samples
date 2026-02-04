"""
Parallel Transformer Block

This module implements tensor-parallel Transformer blocks following the Megatron-LM paper.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional
import math

from .parallel_layers import ColumnParallelLinear, RowParallelLinear
from .parallel_context import get_tensor_parallel_world_size, get_tensor_parallel_rank


class ParallelSelfAttention(nn.Module):
    """
    Tensor-parallel multi-head self-attention.

    Attention heads are partitioned across ranks. Each rank computes a subset
    of attention heads independently.

    Communication pattern:
    - Q, K, V projections: Column-parallel (no communication in forward)
    - Output projection: Row-parallel (all-reduce in forward)
    """

    def __init__(
        self,
        hidden_size: int,
        num_attention_heads: int,
        dropout: float = 0.1,
    ):
        """
        Initialize parallel self-attention.

        Args:
            hidden_size: Hidden size of the model
            num_attention_heads: Number of attention heads (divided across ranks)
            dropout: Dropout probability
        """
        super().__init__()

        self.hidden_size = hidden_size
        self.num_attention_heads = num_attention_heads

        # Get tensor parallel configuration
        world_size = get_tensor_parallel_world_size()
        self.world_size = world_size

        # Ensure heads can be divided by world size
        assert num_attention_heads % world_size == 0, \
            f"num_attention_heads ({num_attention_heads}) must be divisible by world_size ({world_size})"

        self.num_attention_heads_per_partition = num_attention_heads // world_size
        self.head_dim = hidden_size // num_attention_heads
        self.hidden_size_per_partition = self.num_attention_heads_per_partition * self.head_dim

        # Q, K, V projections (column-parallel)
        self.query_key_value = ColumnParallelLinear(
            in_features=hidden_size,
            out_features=3 * hidden_size,  # Q, K, V concatenated
            bias=True,
            gather_output=False,
        )

        # Output projection (row-parallel)
        self.dense = RowParallelLinear(
            in_features=hidden_size,
            out_features=hidden_size,
            bias=True,
            input_is_parallel=True,
            reduce_results=True,
        )

        self.dropout = nn.Dropout(dropout)
        self.scale = 1.0 / math.sqrt(self.head_dim)

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        all_input_tensors_qkv: Optional[list] = None,
        all_qkv_tensors: Optional[list] = None,
        all_output_tensors: Optional[list] = None,
    ) -> torch.Tensor:
        """
        Forward pass of parallel self-attention.

        Args:
            hidden_states: Input tensor of shape [batch_size, seq_len, hidden_size]
            attention_mask: Attention mask of shape [batch_size, 1, 1, seq_len]
            all_input_tensors_qkv: List for collecting input tensors (f operator)
            all_qkv_tensors: List for collecting QKV tensors
            all_output_tensors: List for collecting output tensors (g operator)

        Returns:
            Output tensor of shape [batch_size, seq_len, hidden_size]
        """
        batch_size, seq_len, _ = hidden_states.shape

        # Q, K, V projection (column-parallel)
        mixed_qkv = self.query_key_value(
            hidden_states,
            all_input_tensors=all_input_tensors_qkv,
            all_output_tensors=all_qkv_tensors,
        )

        # Split into Q, K, V
        # Shape: [batch_size, seq_len, 3 * hidden_size_per_partition]
        qkv_size = self.hidden_size_per_partition
        query, key, value = torch.split(mixed_qkv, qkv_size, dim=-1)

        # Reshape for multi-head attention
        # Shape: [batch_size, num_heads_per_partition, seq_len, head_dim]
        query = query.view(batch_size, seq_len, self.num_attention_heads_per_partition, self.head_dim).transpose(1, 2)
        key = key.view(batch_size, seq_len, self.num_attention_heads_per_partition, self.head_dim).transpose(1, 2)
        value = value.view(batch_size, seq_len, self.num_attention_heads_per_partition, self.head_dim).transpose(1, 2)

        # Compute attention scores
        # Shape: [batch_size, num_heads_per_partition, seq_len, seq_len]
        attention_scores = torch.matmul(query, key.transpose(-2, -1)) * self.scale

        # Apply attention mask if provided
        if attention_mask is not None:
            attention_scores = attention_scores + attention_mask

        # Attention probabilities
        attention_probs = F.softmax(attention_scores, dim=-1)
        attention_probs = self.dropout(attention_probs)

        # Weighted sum of values
        # Shape: [batch_size, num_heads_per_partition, seq_len, head_dim]
        context = torch.matmul(attention_probs, value)

        # Reshape back
        # Shape: [batch_size, seq_len, hidden_size_per_partition]
        context = context.transpose(1, 2).contiguous().view(batch_size, seq_len, self.hidden_size_per_partition)

        # Output projection (row-parallel, includes all-reduce)
        output = self.dense(context, all_output_tensors=all_output_tensors)

        return output


class ParallelMLP(nn.Module):
    """
    Tensor-parallel MLP (Feed-Forward Network).

    The MLP consists of two linear layers with GeLU activation in between.
    The intermediate dimension is partitioned across ranks.

    Communication pattern:
    - First layer: Column-parallel (no communication in forward)
    - Second layer: Row-parallel (all-reduce in forward)
    """

    def __init__(
        self,
        hidden_size: int,
        intermediate_size: int,
        dropout: float = 0.1,
    ):
        """
        Initialize parallel MLP.

        Args:
            hidden_size: Hidden size of the model
            intermediate_size: Intermediate size (divided across ranks)
            dropout: Dropout probability
        """
        super().__init__()

        self.hidden_size = hidden_size
        self.intermediate_size = intermediate_size

        # First layer: column-parallel (expand)
        self.dense_h_to_4h = ColumnParallelLinear(
            in_features=hidden_size,
            out_features=intermediate_size,
            bias=True,
            gather_output=False,
        )

        # Second layer: row-parallel (contract)
        self.dense_4h_to_h = RowParallelLinear(
            in_features=intermediate_size,
            out_features=hidden_size,
            bias=True,
            input_is_parallel=True,
            reduce_results=True,
        )

        self.dropout = nn.Dropout(dropout)

    def forward(
        self,
        hidden_states: torch.Tensor,
        all_input_tensors_1: Optional[list] = None,
        all_intermediate_tensors: Optional[list] = None,
        all_output_tensors: Optional[list] = None,
    ) -> torch.Tensor:
        """
        Forward pass of parallel MLP.

        Args:
            hidden_states: Input tensor of shape [batch_size, seq_len, hidden_size]
            all_input_tensors_1: List for collecting input tensors (f operator, first layer)
            all_intermediate_tensors: List for collecting intermediate tensors
            all_output_tensors: List for collecting output tensors (g operator)

        Returns:
            Output tensor of shape [batch_size, seq_len, hidden_size]
        """
        # First layer (column-parallel)
        intermediate = self.dense_h_to_4h(
            hidden_states,
            all_input_tensors=all_input_tensors_1,
            all_output_tensors=all_intermediate_tensors,
        )

        # GeLU activation (local, no communication)
        intermediate = F.gelu(intermediate)

        # Second layer (row-parallel, includes all-reduce)
        output = self.dense_4h_to_h(
            intermediate,
            all_output_tensors=all_output_tensors,
        )

        output = self.dropout(output)

        return output


class ParallelTransformerBlock(nn.Module):
    """
    Complete parallel Transformer block.

    Combines parallel self-attention and parallel MLP with layer normalization
    and residual connections.
    """

    def __init__(
        self,
        hidden_size: int,
        num_attention_heads: int,
        intermediate_size: int,
        dropout: float = 0.1,
        layer_norm_eps: float = 1e-5,
    ):
        """
        Initialize parallel transformer block.

        Args:
            hidden_size: Hidden size of the model
            num_attention_heads: Number of attention heads (divided across ranks)
            intermediate_size: MLP intermediate size (divided across ranks)
            dropout: Dropout probability
            layer_norm_eps: Epsilon for layer normalization
        """
        super().__init__()

        self.attention = ParallelSelfAttention(
            hidden_size=hidden_size,
            num_attention_heads=num_attention_heads,
            dropout=dropout,
        )

        self.mlp = ParallelMLP(
            hidden_size=hidden_size,
            intermediate_size=intermediate_size,
            dropout=dropout,
        )

        self.ln_1 = nn.LayerNorm(hidden_size, eps=layer_norm_eps)
        self.ln_2 = nn.LayerNorm(hidden_size, eps=layer_norm_eps)

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        all_input_tensors_attn: Optional[list] = None,
        all_qkv_tensors: Optional[list] = None,
        all_attn_output_tensors: Optional[list] = None,
        all_input_tensors_mlp: Optional[list] = None,
        all_intermediate_tensors: Optional[list] = None,
        all_mlp_output_tensors: Optional[list] = None,
    ) -> torch.Tensor:
        """
        Forward pass of parallel transformer block.

        Args:
            hidden_states: Input tensor of shape [batch_size, seq_len, hidden_size]
            attention_mask: Attention mask
            Various all_*_tensors: Lists for collecting tensors across ranks

        Returns:
            Output tensor of shape [batch_size, seq_len, hidden_size]
        """
        # Self-attention with residual connection
        residual = hidden_states
        hidden_states = self.ln_1(hidden_states)
        attention_output = self.attention(
            hidden_states,
            attention_mask=attention_mask,
            all_input_tensors_qkv=all_input_tensors_attn,
            all_qkv_tensors=all_qkv_tensors,
            all_output_tensors=all_attn_output_tensors,
        )
        hidden_states = residual + attention_output

        # MLP with residual connection
        residual = hidden_states
        hidden_states = self.ln_2(hidden_states)
        mlp_output = self.mlp(
            hidden_states,
            all_input_tensors_1=all_input_tensors_mlp,
            all_intermediate_tensors=all_intermediate_tensors,
            all_output_tensors=all_mlp_output_tensors,
        )
        hidden_states = residual + mlp_output

        return hidden_states
