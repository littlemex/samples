"""
Megatron-LM Tensor Parallelism - Simple CPU Implementation

This package implements the core concepts from the Megatron-LM paper:
"Megatron-LM: Training Multi-Billion Parameter Language Models Using Model Parallelism"
https://arxiv.org/abs/1909.08053

Key concepts implemented:
- Tensor parallelism with column and row partitioning
- Custom f/g operators for efficient communication
- Parallel Transformer blocks (Self-Attention and MLP)
"""

__version__ = "0.1.0"
