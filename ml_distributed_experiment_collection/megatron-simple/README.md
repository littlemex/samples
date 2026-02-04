# Megatron-LM Tensor Parallelism - Simple CPU Implementation

A minimal implementation of tensor parallelism from the Megatron-LM paper, running on CPU for educational purposes.

## Overview

This project implements the core concepts from the paper ["Megatron-LM: Training Multi-Billion Parameter Language Models Using Model Parallelism"](https://arxiv.org/abs/1909.08053) by NVIDIA researchers.

### Key Features

- **Tensor Parallelism**: Implements column-parallel and row-parallel linear layers
- **Custom Operators**: f and g operators for efficient communication
- **CPU Simulation**: Simulates distributed GPU training on CPU
- **Educational Focus**: Clean, readable code with extensive comments

## Architecture

The implementation includes:

1. **Parallel Operators** (`src/parallel_ops.py`)
   - `f` operator: Identity in forward, All-Reduce in backward
   - `g` operator: All-Reduce in forward, Identity in backward

2. **Parallel Layers** (`src/parallel_layers.py`)
   - `ColumnParallelLinear`: Weight matrix split along output dimension
   - `RowParallelLinear`: Weight matrix split along input dimension

3. **Transformer Components** (`src/transformer.py`)
   - `ParallelSelfAttention`: Attention heads split across ranks
   - `ParallelMLP`: Intermediate dimension split across ranks
   - `ParallelTransformerBlock`: Complete transformer layer

4. **Model** (`src/model.py`)
   - `ParallelGPTModel`: Simple GPT-style language model

## Installation

No special dependencies required! Just PyTorch:

```bash
pip install torch
```

## Usage

### Running Tests

Test the parallel operators:
```bash
python tests/test_parallel_ops.py
```

Test the parallel layers:
```bash
python tests/test_parallel_layers.py
```

### Training

Simulate distributed training with 2 ranks:
```bash
python examples/simple_train.py --mode simulate --world-size 2
```

Compare single vs parallel training:
```bash
python examples/simple_train.py --mode compare
```

## How It Works

### Tensor Parallelism

The key insight from Megatron-LM is that by carefully partitioning weight matrices and using custom communication operators, we can minimize communication overhead.

**MLP Layer Pattern:**
```
Input (replicated)
    ↓
f operator (identity fwd, all-reduce bwd)
    ↓
Column-Parallel Linear (split output dimension)
    ↓
GeLU (local, no communication)
    ↓
Row-Parallel Linear (split input dimension)
    ↓
g operator (all-reduce fwd, identity bwd)
    ↓
Output (replicated)
```

**Communication Cost:**
- Forward: 1 All-Reduce per layer
- Backward: 1 All-Reduce per layer
- Total: 2 All-Reduce operations per layer

### CPU Simulation

Since this runs on CPU, we simulate multiple GPUs by:
1. Running each rank sequentially
2. Collecting tensors from all ranks
3. Manually performing all-reduce (averaging) and all-gather (concatenation)

This is purely for educational purposes - in production, you'd use `torch.distributed` with real GPUs.

## Model Configuration

Default configuration:
- Vocabulary size: 1000 tokens
- Hidden size: 256
- Number of layers: 4
- Attention heads: 4 (split across ranks)
- Intermediate size: 1024 (split across ranks)
- Max sequence length: 128

## References

- [Megatron-LM Paper](https://arxiv.org/abs/1909.08053)
- [NVIDIA Megatron-LM Repository](https://github.com/NVIDIA/Megatron-LM)
- [Original note.com article](https://note.com/littlemex63454/n/n64508de8af37)

## License

MIT License - Free for educational and research purposes.
