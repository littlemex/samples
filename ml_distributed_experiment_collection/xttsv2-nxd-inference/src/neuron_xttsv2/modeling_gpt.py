"""NeuronGPTTransformer: XTTSv2 GPT-2 model for AWS Neuron

This module implements the GPT-2 Transformer from XTTSv2 using NxD Inference patterns.
Only the Transformer layers are compiled for Neuron; embeddings and heads remain on CPU.
"""

import math
import torch
import torch.nn as nn

from neuronx_distributed.parallel_layers.layers import (
    ColumnParallelLinear,
    RowParallelLinear,
)
from neuronx_distributed.parallel_layers import parallel_state
from neuronx_distributed_inference.models.model_wrapper import BaseModelInstance


def ceil_div(a, b):
    """Ceiling division"""
    return (a + b - 1) // b


class NeuronMLP(nn.Module):
    """MLP with Tensor Parallelism support.

    Follows GPT-2's MLP structure: Linear(d_model, 4*d_model) + GELU + Linear(4*d_model, d_model)
    """

    def __init__(self, hidden_size, intermediate_size, dtype):
        super().__init__()
        self.up_proj = ColumnParallelLinear(
            hidden_size,
            intermediate_size,
            bias=True,
            gather_output=False,
            dtype=dtype,
        )
        self.down_proj = RowParallelLinear(
            intermediate_size,
            hidden_size,
            bias=True,
            input_is_parallel=True,
            dtype=dtype,
        )
        self.act = nn.GELU()

    def forward(self, x):
        x = self.up_proj(x)
        x = self.act(x)
        x = self.down_proj(x)
        return x


class NeuronGPTAttention(nn.Module):
    """Self-Attention with KV-Cache for XTTSv2 GPT.

    Implements the attention mechanism with:
    - KV-Cache stored as nn.Parameter
    - torch.scatter for cache updates
    - Prefill and Decode modes
    """

    def __init__(self, n_state, n_head, batch_size, seq_len, dtype, kvcache=True):
        super().__init__()
        self.n_state = n_state
        self.n_head = n_head
        self.head_dim = n_state // n_head

        # Tensor Parallelism: split heads across cores
        tp_degree = parallel_state.get_tensor_model_parallel_group().size() if parallel_state.model_parallel_is_initialized() else 1
        self.n_heads_per_core = ceil_div(n_head, tp_degree)
        self.n_kv_heads = self.n_heads_per_core  # For now, no GQA

        # Q/K/V projections
        self.query = ColumnParallelLinear(
            n_state, n_state, bias=True, gather_output=False, dtype=dtype
        )
        self.key = ColumnParallelLinear(
            n_state, n_state, bias=True, gather_output=False, dtype=dtype
        )
        self.value = ColumnParallelLinear(
            n_state, n_state, bias=True, gather_output=False, dtype=dtype
        )
        self.out = RowParallelLinear(
            n_state, n_state, bias=True, input_is_parallel=True, dtype=dtype
        )

        # KV-Cache as nn.Parameter (updated via aliases)
        self.cache_k = nn.Parameter(
            torch.zeros(
                (batch_size, self.n_kv_heads, seq_len, self.head_dim),
                dtype=dtype,
            ),
            requires_grad=False,
        ) if kvcache else None

        self.cache_v = nn.Parameter(
            torch.zeros(
                (batch_size, self.n_kv_heads, seq_len, self.head_dim),
                dtype=dtype,
            ),
            requires_grad=False,
        ) if kvcache else None

    def forward(self, x, last_pos=None, mask=None):
        """
        Args:
            x: Input tensor [batch_size, seq_len, n_state]
            last_pos: Position to update cache (for Decode mode) [batch_size]
            mask: Attention mask [batch_size, seq_len]

        Returns:
            output: [batch_size, seq_len, n_state]
            updated_kcache: [batch_size, n_kv_heads, max_seq_len, head_dim]
            updated_vcache: [batch_size, n_kv_heads, max_seq_len, head_dim]
        """
        bsz, seq_len, _ = x.shape

        # Q/K/V projections
        q = self.query(x).view(bsz, seq_len, self.n_heads_per_core, self.head_dim).transpose(1, 2)
        k = self.key(x).view(bsz, seq_len, self.n_kv_heads, self.head_dim).transpose(1, 2)
        v = self.value(x).view(bsz, seq_len, self.n_kv_heads, self.head_dim).transpose(1, 2)

        # Update KV-Cache
        if self.cache_k is not None and self.cache_v is not None:
            if seq_len > 1:
                # Prefill: update all positions from 0 to seq_len-1
                # .contiguous() required: expand() returns a non-contiguous tensor
                indices = torch.arange(0, seq_len, dtype=torch.int64, device=x.device).view(1, 1, seq_len, 1)
                indices = indices.expand(bsz, self.n_kv_heads, seq_len, self.head_dim).contiguous()
            else:
                # Decode: update only last_pos
                # .to(torch.int64).contiguous() required: scatter index must be int64 and contiguous
                if last_pos is not None:
                    indices = last_pos.view(bsz, 1, 1, 1).expand(bsz, self.n_kv_heads, 1, self.head_dim).to(torch.int64).contiguous()
                else:
                    indices = torch.zeros((bsz, self.n_kv_heads, 1, self.head_dim), dtype=torch.int64, device=x.device)

            updated_kcache = torch.scatter(self.cache_k, 2, indices, k)
            updated_vcache = torch.scatter(self.cache_v, 2, indices, v)

            # Use updated cache for attention
            k = updated_kcache
            v = updated_vcache
        else:
            updated_kcache = k
            updated_vcache = v

        # Scaled dot-product attention
        scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.head_dim)

        # Apply mask if provided
        if mask is not None:
            if seq_len > 1:
                # Prefill: causal mask (lower triangular)
                # scores: [batch, n_heads, seq_len, max_seq_len]
                # query position i must only attend to key positions j <= i
                max_seq = scores.shape[-1]
                causal_mask = torch.zeros(seq_len, max_seq, dtype=scores.dtype, device=scores.device)
                causal_part = torch.tril(torch.ones(seq_len, seq_len, dtype=scores.dtype, device=scores.device))
                causal_mask[:, :seq_len] = causal_part
                # Also apply key validity mask (zero out padding positions)
                key_valid = mask[:, :max_seq].to(scores.dtype)  # [batch, max_seq]
                causal_mask = causal_mask.unsqueeze(0) * key_valid.unsqueeze(1)  # [batch, seq_len, max_seq]
                causal_mask = causal_mask.unsqueeze(1)  # [batch, 1, seq_len, max_seq]
                scores = scores + (1.0 - causal_mask) * torch.finfo(scores.dtype).min
            else:
                # Decode: all valid cached positions are visible (non-causal key mask)
                mask_2d = mask.unsqueeze(1).unsqueeze(2).to(scores.dtype)
                scores = scores + (1.0 - mask_2d) * torch.finfo(scores.dtype).min

        # Softmax + weighted sum
        attn_weights = torch.nn.functional.softmax(scores, dim=-1)
        output = torch.matmul(attn_weights, v)

        # Reshape and project
        output = output.transpose(1, 2).contiguous().view(bsz, seq_len, -1)
        output = self.out(output)

        return output, updated_kcache, updated_vcache


class NeuronGPTBlock(nn.Module):
    """GPT-2 Transformer Block"""

    def __init__(self, n_state, n_head, batch_size, seq_len, dtype):
        super().__init__()
        self.ln_1 = nn.LayerNorm(n_state, dtype=dtype)
        self.attn = NeuronGPTAttention(n_state, n_head, batch_size, seq_len, dtype)
        self.ln_2 = nn.LayerNorm(n_state, dtype=dtype)
        self.mlp = NeuronMLP(n_state, n_state * 4, dtype)

    def forward(self, x, last_pos=None, mask=None):
        """
        Args:
            x: [batch_size, seq_len, n_state]
            last_pos: [batch_size]
            mask: [batch_size, seq_len]

        Returns:
            x: [batch_size, seq_len, n_state]
            cache_k: [batch_size, n_kv_heads, max_seq_len, head_dim]
            cache_v: [batch_size, n_kv_heads, max_seq_len, head_dim]
        """
        # Pre-LN architecture (like GPT-2)
        attn_output, cache_k, cache_v = self.attn(self.ln_1(x), last_pos=last_pos, mask=mask)
        x = x + attn_output
        x = x + self.mlp(self.ln_2(x))
        return x, cache_k, cache_v


class NeuronGPTTransformer(nn.Module):
    """XTTSv2 GPT Transformer (Neuron version).

    This corresponds to the HuggingFace GPT2Model, but only includes the
    Transformer blocks. Embeddings and output heads remain on CPU.

    Args:
        n_layer: Number of transformer layers (30)
        n_state: Model dimension (1024)
        n_head: Number of attention heads (16)
        batch_size: Batch size for inference
        seq_len: Maximum sequence length (1081)
        dtype: Tensor dtype (torch.float16 or torch.float32)
    """

    def __init__(self, n_layer, n_state, n_head, batch_size, seq_len, dtype):
        super().__init__()
        self.n_layer = n_layer
        self.n_state = n_state
        self.n_head = n_head

        self.blocks = nn.ModuleList([
            NeuronGPTBlock(n_state, n_head, batch_size, seq_len, dtype)
            for _ in range(n_layer)
        ])

    def forward(self, hidden_states, last_pos, mask):
        """
        Args:
            hidden_states: [batch_size, seq_len, n_state] - Embeddings from CPU
            last_pos: [batch_size] - Position to update cache (Decode mode)
            mask: [batch_size, seq_len] - Attention mask

        Returns:
            hidden_states: [batch_size, seq_len, n_state]
            *kv_caches: List of (cache_k, cache_v) for each layer
        """
        all_cache_k = []
        all_cache_v = []

        for block in self.blocks:
            hidden_states, cache_k, cache_v = block(hidden_states, last_pos=last_pos, mask=mask)
            all_cache_k.append(cache_k)
            all_cache_v.append(cache_v)

        # Return hidden_states + all KV caches
        # NOTE: "return a, *list_b" is not supported by torch.jit.script.
        # Use explicit tuple concatenation for XLA/Neuron compatibility.
        return (hidden_states,) + tuple(all_cache_k) + tuple(all_cache_v)


class NeuronGPTInstance(BaseModelInstance):
    """BaseModelInstance for NeuronGPTTransformer.

    Provides:
    - load_module(): Initialize the NeuronGPTTransformer
    - get(): Return module and aliases dict for KV-Cache management
    """

    def __init__(self, config):
        # Do not call super().__init__() here: BaseModelInstance.__init__ requires
        # (module_cls, input_output_aliases) which are not known at this stage.
        # Set self.input_output_aliases to satisfy any framework code that accesses it.
        self.module = None
        self.input_output_aliases = [{}]
        self.config = config
        self.neuron_config = config.neuron_config

    def load_module(self):
        """Initialize NeuronGPTTransformer"""
        self.module = NeuronGPTTransformer(
            n_layer=self.config.gpt_layers,
            n_state=self.config.gpt_n_model_channels,
            n_head=self.config.gpt_n_heads,
            batch_size=self.neuron_config.batch_size,
            seq_len=self.config.max_seq_len,
            dtype=self.neuron_config.torch_dtype,
        )

    def get(self, bucket_rank=None, **kwargs):
        """Return module and aliases.

        aliases: {nn.Parameter: output_index} mapping
        - output_index 0: hidden_states
        - output_index 1..N: cache_k for layers 0..N-1
        - output_index N+1..2N: cache_v for layers 0..N-1
        """
        aliases = {}
        output_index = 1  # 0 is hidden_states

        # Aliases for cache_k
        for layer in self.module.blocks:
            aliases[layer.attn.cache_k] = output_index
            output_index += 1

        # Aliases for cache_v
        for layer in self.module.blocks:
            aliases[layer.attn.cache_v] = output_index
            output_index += 1

        return self.module, aliases
