"""
Simple GPT-style Language Model with Tensor Parallelism

This module implements a simple language model using parallel Transformer blocks.
"""

import torch
import torch.nn as nn
from typing import Optional, List
from dataclasses import dataclass

from .transformer import ParallelTransformerBlock
from .parallel_context import get_tensor_parallel_world_size


@dataclass
class ModelConfig:
    """Configuration for the parallel GPT model."""
    vocab_size: int = 1000  # Vocabulary size
    hidden_size: int = 256  # Hidden dimension
    num_layers: int = 4  # Number of transformer layers
    num_attention_heads: int = 4  # Number of attention heads
    intermediate_size: int = 1024  # MLP intermediate size (4 * hidden_size)
    max_seq_len: int = 128  # Maximum sequence length
    dropout: float = 0.1  # Dropout probability
    layer_norm_eps: float = 1e-5  # Layer normalization epsilon


class ParallelGPTModel(nn.Module):
    """
    Simple GPT-style model with tensor parallelism.

    This model uses parallel Transformer blocks to demonstrate the Megatron-LM
    tensor parallelism approach.
    """

    def __init__(self, config: ModelConfig):
        """
        Initialize parallel GPT model.

        Args:
            config: Model configuration
        """
        super().__init__()
        self.config = config

        # Token embeddings (replicated across all ranks)
        self.token_embeddings = nn.Embedding(config.vocab_size, config.hidden_size)

        # Position embeddings (replicated across all ranks)
        self.position_embeddings = nn.Embedding(config.max_seq_len, config.hidden_size)

        self.dropout = nn.Dropout(config.dropout)

        # Stack of parallel transformer blocks
        self.blocks = nn.ModuleList([
            ParallelTransformerBlock(
                hidden_size=config.hidden_size,
                num_attention_heads=config.num_attention_heads,
                intermediate_size=config.intermediate_size,
                dropout=config.dropout,
                layer_norm_eps=config.layer_norm_eps,
            )
            for _ in range(config.num_layers)
        ])

        # Final layer norm
        self.ln_f = nn.LayerNorm(config.hidden_size, eps=config.layer_norm_eps)

        # Output layer (replicated - not parallelized for simplicity)
        self.lm_head = nn.Linear(config.hidden_size, config.vocab_size, bias=False)

        # Initialize weights
        self.apply(self._init_weights)

    def _init_weights(self, module):
        """Initialize model weights."""
        if isinstance(module, (nn.Linear, nn.Embedding)):
            module.weight.data.normal_(mean=0.0, std=0.02)
            if isinstance(module, nn.Linear) and module.bias is not None:
                module.bias.data.zero_()
        elif isinstance(module, nn.LayerNorm):
            module.bias.data.zero_()
            module.weight.data.fill_(1.0)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        all_tensors_per_layer: Optional[List[dict]] = None,
    ) -> torch.Tensor:
        """
        Forward pass of the model.

        Args:
            input_ids: Input token IDs of shape [batch_size, seq_len]
            attention_mask: Attention mask of shape [batch_size, seq_len]
            all_tensors_per_layer: List of dicts containing tensors from all ranks for each layer

        Returns:
            Logits of shape [batch_size, seq_len, vocab_size]
        """
        batch_size, seq_len = input_ids.shape
        device = input_ids.device

        # Get embeddings
        token_embeds = self.token_embeddings(input_ids)
        position_ids = torch.arange(seq_len, dtype=torch.long, device=device).unsqueeze(0)
        position_embeds = self.position_embeddings(position_ids)

        hidden_states = self.dropout(token_embeds + position_embeds)

        # Prepare attention mask
        if attention_mask is not None:
            # Extend attention mask dimensions for multi-head attention
            # Shape: [batch_size, 1, 1, seq_len]
            attention_mask = attention_mask.unsqueeze(1).unsqueeze(2)
            # Convert to attention bias (0 for valid positions, large negative for masked)
            attention_mask = (1.0 - attention_mask) * -10000.0

        # Pass through transformer blocks
        for i, block in enumerate(self.blocks):
            if all_tensors_per_layer is not None and i < len(all_tensors_per_layer):
                layer_tensors = all_tensors_per_layer[i]
            else:
                layer_tensors = {}

            hidden_states = block(
                hidden_states,
                attention_mask=attention_mask,
                all_input_tensors_attn=layer_tensors.get('input_attn', None),
                all_qkv_tensors=layer_tensors.get('qkv', None),
                all_attn_output_tensors=layer_tensors.get('attn_output', None),
                all_input_tensors_mlp=layer_tensors.get('input_mlp', None),
                all_intermediate_tensors=layer_tensors.get('intermediate', None),
                all_mlp_output_tensors=layer_tensors.get('mlp_output', None),
            )

        # Final layer norm
        hidden_states = self.ln_f(hidden_states)

        # Output projection
        logits = self.lm_head(hidden_states)

        return logits

    def get_num_params(self) -> int:
        """Get total number of parameters in the model."""
        return sum(p.numel() for p in self.parameters())

    def get_num_params_per_rank(self) -> int:
        """
        Get approximate number of parameters per rank.

        Note: This is approximate because some parameters (embeddings, layer norms)
        are replicated across all ranks.
        """
        world_size = get_tensor_parallel_world_size()

        # Count parameters that are partitioned
        partitioned_params = 0
        replicated_params = 0

        for name, param in self.named_parameters():
            if any(x in name for x in ['query_key_value', 'dense_h_to_4h', 'dense_4h_to_h', 'dense']):
                # These are partitioned
                partitioned_params += param.numel()
            else:
                # Embeddings, layer norms, etc. are replicated
                replicated_params += param.numel()

        return (partitioned_params // world_size) + replicated_params
