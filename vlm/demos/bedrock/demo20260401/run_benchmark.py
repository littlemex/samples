#!/usr/bin/env python3
"""
AWS Bedrock VLM OCR Benchmark Runner

Runs comprehensive benchmarks across multiple models, images, and prompts.
Calculates CER (Character Error Rate) and BLEU scores for accuracy evaluation.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any
import subprocess

try:
    import Levenshtein
except ImportError:
    print("[ERROR] Levenshtein library not found. Installing...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-Levenshtein"])
    import Levenshtein


def load_json_config(path: str) -> Any:
    """Load JSON configuration file."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def calculate_cer(reference: str, hypothesis: str) -> float:
    """
    Calculate Character Error Rate (CER).

    CER = Levenshtein distance / reference length
    """
    if not reference:
        return 0.0 if not hypothesis else 1.0

    distance = Levenshtein.distance(reference, hypothesis)
    return distance / len(reference)


def calculate_bleu_1gram(reference: str, hypothesis: str) -> float:
    """
    Calculate BLEU score with 1-gram (character-level) matching.

    Simplified BLEU with brevity penalty.
    """
    if not reference or not hypothesis:
        return 0.0

    ref_chars = list(reference)
    hyp_chars = list(hypothesis)

    # Count matching characters
    matches = 0
    for char in hyp_chars:
        if char in ref_chars:
            matches += 1
            ref_chars.remove(char)  # Each char can only match once

    # Precision
    precision = matches / len(hyp_chars) if hyp_chars else 0.0

    # Brevity penalty
    if len(hyp_chars) < len(reference):
        bp = len(hyp_chars) / len(reference)
    else:
        bp = 1.0

    return bp * precision


def run_single_test(
    image_path: str,
    prompt: str,
    model_id: str,
    ground_truth: str,
    aws_profile: str = None
) -> Dict[str, Any]:
    """
    Run a single OCR test using vlm_ocr.py.

    Returns:
        Dictionary with extracted text, CER, BLEU, timing, and cost
    """
    cmd = [
        sys.executable,
        "vlm_ocr.py",
        image_path,
        "--model-id", model_id,
        "--prompt", prompt
    ]

    if aws_profile:
        cmd.extend(["--profile", aws_profile])

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        elapsed_time = time.time() - start_time

        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr,
                "elapsed_time": elapsed_time
            }

        # Parse JSON output from vlm_ocr.py
        output = json.loads(result.stdout)

        if not output.get("success"):
            return {
                "success": False,
                "error": output.get("error", "Unknown error"),
                "elapsed_time": elapsed_time
            }

        # Calculate accuracy metrics
        extracted_text = output["output_text"]
        cer = calculate_cer(ground_truth, extracted_text)
        bleu = calculate_bleu_1gram(ground_truth, extracted_text)

        return {
            "success": True,
            "extracted_text": extracted_text,
            "ground_truth": ground_truth,
            "cer": cer,
            "bleu": bleu,
            "elapsed_time": elapsed_time,
            "input_tokens": output["input_tokens"],
            "output_tokens": output["output_tokens"],
            "cost_usd": output["cost_usd"],
            "cost_jpy": output["cost_jpy"]
        }

    except subprocess.TimeoutExpired:
        elapsed_time = time.time() - start_time
        return {
            "success": False,
            "error": "Timeout (120s)",
            "elapsed_time": elapsed_time
        }
    except Exception as e:
        elapsed_time = time.time() - start_time
        return {
            "success": False,
            "error": str(e),
            "elapsed_time": elapsed_time
        }


def run_benchmark(
    images: List[Dict],
    prompts: List[Dict],
    models: List[Dict],
    aws_profile: str = None
) -> Dict[str, Any]:
    """
    Run full benchmark across all combinations.

    Returns:
        Dictionary with all test results and summary statistics
    """
    total_tests = len(images) * len(prompts) * len(models)
    print(f"[INFO] Starting benchmark: {total_tests} tests")
    print(f"[INFO] {len(images)} images x {len(prompts)} prompts x {len(models)} models")
    print(f"[INFO] AWS Profile: {aws_profile or 'default'}")
    print()

    results = []
    test_num = 0

    for image in images:
        for prompt in prompts:
            for model in models:
                test_num += 1
                print(f"[{test_num}/{total_tests}] Testing: {model['name']} | {prompt['id']} | {image['id']}")

                result = run_single_test(
                    image_path=image["path"],
                    prompt=prompt["text"],
                    model_id=model["model_id"],
                    ground_truth=image["ground_truth"],
                    aws_profile=aws_profile
                )

                result["image_id"] = image["id"]
                result["prompt_id"] = prompt["id"]
                result["model_id"] = model["id"]
                result["model_name"] = model["name"]

                results.append(result)

                if result["success"]:
                    print(f"  CER: {result['cer']:.4f} | BLEU: {result['bleu']:.4f} | Time: {result['elapsed_time']:.2f}s | Cost: ¥{result['cost_jpy']:.2f}")
                else:
                    print(f"  [ERROR] {result['error']}")
                print()

    # Calculate summary statistics per model
    model_stats = {}
    for model in models:
        model_id = model["id"]
        model_results = [r for r in results if r["model_id"] == model_id and r["success"]]

        if model_results:
            avg_cer = sum(r["cer"] for r in model_results) / len(model_results)
            avg_bleu = sum(r["bleu"] for r in model_results) / len(model_results)
            avg_time = sum(r["elapsed_time"] for r in model_results) / len(model_results)
            avg_cost_jpy = sum(r["cost_jpy"] for r in model_results) / len(model_results)
            perfect_count = sum(1 for r in model_results if r["cer"] == 0.0)

            model_stats[model_id] = {
                "model_name": model["name"],
                "total_tests": len(model_results),
                "avg_cer": avg_cer,
                "avg_bleu": avg_bleu,
                "avg_time": avg_time,
                "avg_cost_jpy": avg_cost_jpy,
                "perfect_recognitions": perfect_count
            }
        else:
            model_stats[model_id] = {
                "model_name": model["name"],
                "total_tests": 0,
                "avg_cer": None,
                "avg_bleu": None,
                "avg_time": None,
                "avg_cost_jpy": None,
                "perfect_recognitions": 0
            }

    return {
        "timestamp": datetime.now().isoformat(),
        "total_tests": total_tests,
        "successful_tests": sum(1 for r in results if r["success"]),
        "failed_tests": sum(1 for r in results if not r["success"]),
        "results": results,
        "model_statistics": model_stats
    }


def display_summary(benchmark_data: Dict[str, Any]):
    """Display benchmark summary table."""
    print("=" * 120)
    print("[BENCHMARK SUMMARY]")
    print("=" * 120)
    print(f"Timestamp: {benchmark_data['timestamp']}")
    print(f"Total Tests: {benchmark_data['total_tests']}")
    print(f"Successful: {benchmark_data['successful_tests']}")
    print(f"Failed: {benchmark_data['failed_tests']}")
    print()

    print(f"{'Model':<40} {'CER':>8} {'BLEU':>8} {'Time(s)':>10} {'Cost(¥)':>10} {'Perfect':>8}")
    print("-" * 120)

    for model_id, stats in benchmark_data["model_statistics"].items():
        if stats["total_tests"] > 0:
            print(f"{stats['model_name']:<40} "
                  f"{stats['avg_cer']:>8.4f} "
                  f"{stats['avg_bleu']:>8.4f} "
                  f"{stats['avg_time']:>10.2f} "
                  f"{stats['avg_cost_jpy']:>10.2f} "
                  f"{stats['perfect_recognitions']:>8}")
        else:
            print(f"{stats['model_name']:<40} {'N/A':>8} {'N/A':>8} {'N/A':>10} {'N/A':>10} {'0':>8}")

    print("=" * 120)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run AWS Bedrock VLM OCR benchmark"
    )
    parser.add_argument(
        "--profile",
        type=str,
        default=None,
        help="AWS profile name (default: from AWS_PROFILE env var)"
    )

    args = parser.parse_args()

    # Get AWS profile
    aws_profile = args.profile or os.environ.get("AWS_PROFILE")
    if not aws_profile:
        print("[WARNING] No AWS profile specified. Using default credentials.")

    # Load configurations
    print("[INFO] Loading configurations...")
    images = load_json_config("configs/images.json")
    prompts = load_json_config("configs/prompts.json")
    models = load_json_config("configs/models.json")
    print(f"[INFO] Loaded {len(images)} images, {len(prompts)} prompts, {len(models)} models")
    print()

    # Run benchmark
    benchmark_data = run_benchmark(images, prompts, models, aws_profile)

    # Save results
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = logs_dir / f"benchmark_results_{timestamp_str}.json"

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(benchmark_data, f, ensure_ascii=False, indent=2)

    print(f"[INFO] Results saved to: {output_file}")
    print()

    # Display summary
    display_summary(benchmark_data)

    return 0 if benchmark_data["failed_tests"] == 0 else 1


if __name__ == "__main__":
    exit(main())
