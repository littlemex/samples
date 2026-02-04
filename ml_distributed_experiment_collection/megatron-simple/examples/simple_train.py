"""
Simple training script for parallel GPT model

This script demonstrates end-to-end training with tensor parallelism on CPU.
"""

import torch
import torch.nn as nn
import sys
sys.path.insert(0, '/work/samples/ml_distributed_experiment_collection/megatron-simple')

from src.model import ParallelGPTModel, ModelConfig
from src.parallel_context import TensorParallelContext
import time


def create_synthetic_data(batch_size, seq_len, vocab_size, num_batches):
    """Create synthetic training data"""
    data = []
    for _ in range(num_batches):
        input_ids = torch.randint(0, vocab_size, (batch_size, seq_len))
        target_ids = torch.randint(0, vocab_size, (batch_size, seq_len))
        data.append((input_ids, target_ids))
    return data


def train_single_rank(rank, world_size, config, num_epochs=3, num_batches=10):
    """Train model on a single rank"""
    print(f"\n{'='*60}")
    print(f"Rank {rank}/{world_size} - Starting Training")
    print(f"{'='*60}\n")

    # Set random seed for reproducibility
    torch.manual_seed(42 + rank)

    # Initialize tensor parallel context
    with TensorParallelContext(world_size=world_size, rank=rank):
        # Create model
        model = ParallelGPTModel(config)
        print(f"Rank {rank} - Model created")
        print(f"  Total params: {model.get_num_params():,}")
        print(f"  Params per rank: {model.get_num_params_per_rank():,}")
        print()

        # Create optimizer
        optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

        # Create synthetic data
        train_data = create_synthetic_data(
            batch_size=4,
            seq_len=config.max_seq_len,
            vocab_size=config.vocab_size,
            num_batches=num_batches,
        )

        # Loss function
        criterion = nn.CrossEntropyLoss()

        # Training loop
        for epoch in range(num_epochs):
            epoch_loss = 0.0
            epoch_start = time.time()

            for batch_idx, (input_ids, target_ids) in enumerate(train_data):
                # Forward pass
                logits = model(input_ids)

                # Compute loss
                loss = criterion(
                    logits.view(-1, config.vocab_size),
                    target_ids.view(-1)
                )

                # Backward pass
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()

                if (batch_idx + 1) % 5 == 0:
                    print(f"Rank {rank} - Epoch {epoch+1}/{num_epochs}, "
                          f"Batch {batch_idx+1}/{num_batches}, "
                          f"Loss: {loss.item():.4f}")

            avg_loss = epoch_loss / num_batches
            epoch_time = time.time() - epoch_start

            print(f"\nRank {rank} - Epoch {epoch+1} Summary:")
            print(f"  Average Loss: {avg_loss:.4f}")
            print(f"  Time: {epoch_time:.2f}s")
            print()

    print(f"Rank {rank} - Training completed!\n")
    return model


def simulate_distributed_training(world_size=2):
    """Simulate distributed training by running multiple ranks sequentially"""
    print("\n" + "="*60)
    print(f"Simulating Distributed Training with {world_size} ranks")
    print("="*60)

    # Model configuration
    config = ModelConfig(
        vocab_size=1000,
        hidden_size=256,
        num_layers=4,
        num_attention_heads=4,
        intermediate_size=1024,
        max_seq_len=128,
        dropout=0.1,
    )

    print("\nModel Configuration:")
    print(f"  Vocabulary size: {config.vocab_size}")
    print(f"  Hidden size: {config.hidden_size}")
    print(f"  Number of layers: {config.num_layers}")
    print(f"  Attention heads: {config.num_attention_heads}")
    print(f"  Intermediate size: {config.intermediate_size}")
    print(f"  Max sequence length: {config.max_seq_len}")

    # Train each rank
    models = []
    for rank in range(world_size):
        model = train_single_rank(
            rank=rank,
            world_size=world_size,
            config=config,
            num_epochs=3,
            num_batches=10,
        )
        models.append(model)

    print("\n" + "="*60)
    print("All ranks completed training!")
    print("="*60)


def compare_single_vs_parallel():
    """Compare single-GPU vs parallel training"""
    print("\n" + "="*60)
    print("Comparing Single vs Parallel Training")
    print("="*60)

    config = ModelConfig(
        vocab_size=1000,
        hidden_size=128,
        num_layers=2,
        num_attention_heads=4,
        intermediate_size=512,
        max_seq_len=64,
        dropout=0.1,
    )

    # Single GPU
    print("\n[1] Training on single 'GPU' (world_size=1)...")
    model_single = train_single_rank(
        rank=0,
        world_size=1,
        config=config,
        num_epochs=2,
        num_batches=5,
    )

    # Parallel (2 GPUs)
    print("\n[2] Training on 2 'GPUs' (world_size=2)...")
    print("\n--- Rank 0 ---")
    model_parallel_0 = train_single_rank(
        rank=0,
        world_size=2,
        config=config,
        num_epochs=2,
        num_batches=5,
    )

    print("\n--- Rank 1 ---")
    model_parallel_1 = train_single_rank(
        rank=1,
        world_size=2,
        config=config,
        num_epochs=2,
        num_batches=5,
    )

    print("\n" + "="*60)
    print("Comparison complete!")
    print("="*60)
    print(f"\nSingle GPU params: {model_single.get_num_params():,}")
    print(f"Parallel (per rank): {model_parallel_0.get_num_params_per_rank():,}")
    print(f"Memory reduction: ~{model_single.get_num_params() / model_parallel_0.get_num_params_per_rank():.1f}x")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Train parallel GPT model")
    parser.add_argument(
        "--mode",
        type=str,
        default="simulate",
        choices=["simulate", "compare"],
        help="Training mode: 'simulate' for distributed training, 'compare' for single vs parallel"
    )
    parser.add_argument(
        "--world-size",
        type=int,
        default=2,
        help="Number of parallel ranks (default: 2)"
    )

    args = parser.parse_args()

    if args.mode == "simulate":
        simulate_distributed_training(world_size=args.world_size)
    else:
        compare_single_vs_parallel()
