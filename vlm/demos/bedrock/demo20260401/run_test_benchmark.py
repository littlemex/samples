#!/usr/bin/env python3
"""
Quick test benchmark for AWS Bedrock VLM OCR

Tests a single image with all models to verify setup.
"""

import json
import os
import sys
from pathlib import Path

# Reuse the main benchmark runner functions
from run_benchmark import (
    load_json_config,
    run_single_test,
    calculate_cer,
    calculate_bleu_1gram
)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Quick test benchmark"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="AWS profile name"
    )
    parser.add_argument(
        "--image",
        type=str,
        default="sign_no_littering",
        help="Image ID to test (default: sign_no_littering)"
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="simple_english",
        help="Prompt ID to use (default: simple_english)"
    )

    args = parser.parse_args()

    # Get AWS profile
    aws_profile = args.profile or os.environ.get("AWS_PROFILE")

    # Load configurations
    print("[INFO] Loading configurations...")
    images = load_json_config("configs/images.json")
    prompts = load_json_config("configs/prompts.json")
    models = load_json_config("configs/models.json")

    # Find requested image and prompt
    image = next((img for img in images if img["id"] == args.image), None)
    if not image:
        print(f"[ERROR] Image '{args.image}' not found in configs/images.json")
        return 1

    prompt = next((p for p in prompts if p["id"] == args.prompt), None)
    if not prompt:
        print(f"[ERROR] Prompt '{args.prompt}' not found in configs/prompts.json")
        return 1

    print(f"[INFO] Testing image: {image['id']}")
    print(f"[INFO] Using prompt: {prompt['id']}")
    print(f"[INFO] Testing {len(models)} models")
    print()

    # Test each model
    results = []
    for idx, model in enumerate(models, 1):
        print(f"[{idx}/{len(models)}] Testing: {model['name']}")

        result = run_single_test(
            image_path=image["path"],
            prompt=prompt["text"],
            model_id=model["model_id"],
            ground_truth=image["ground_truth"],
            aws_profile=aws_profile
        )

        result["model_name"] = model["name"]
        results.append(result)

        if result["success"]:
            print(f"  CER: {result['cer']:.4f}")
            print(f"  BLEU: {result['bleu']:.4f}")
            print(f"  Time: {result['elapsed_time']:.2f}s")
            print(f"  Cost: ¥{result['cost_jpy']:.2f}")
        else:
            print(f"  [ERROR] {result['error']}")
        print()

    # Display summary
    print("=" * 80)
    print("[TEST SUMMARY]")
    print("=" * 80)
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    print(f"Successful: {len(successful)}/{len(models)}")
    print(f"Failed: {len(failed)}/{len(models)}")

    if successful:
        print()
        print(f"{'Model':<40} {'CER':>8} {'BLEU':>8} {'Time(s)':>10} {'Cost(¥)':>10}")
        print("-" * 80)
        for result in successful:
            print(f"{result['model_name']:<40} "
                  f"{result['cer']:>8.4f} "
                  f"{result['bleu']:>8.4f} "
                  f"{result['elapsed_time']:>10.2f} "
                  f"{result['cost_jpy']:>10.2f}")

    print("=" * 80)

    return 0 if len(failed) == 0 else 1


if __name__ == "__main__":
    exit(main())
