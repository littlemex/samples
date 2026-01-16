#!/usr/bin/env python3
"""
Offline (batch) inference benchmark script for vLLM.
Supports both GPU (g5) and Neuron (inf2) instances.
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent))

from common.env_info import collect_all_info, save_env_info
from common.metrics import (
    BenchmarkMetrics,
    MLflowMetricsCollector,
    MetricsCollector,
    create_experiment_id,
    MLFLOW_AVAILABLE,
)


# vLLM import (will fail if vLLM is not installed)
try:
    from vllm import LLM, SamplingParams
    VLLM_AVAILABLE = True
except ImportError:
    VLLM_AVAILABLE = False
    print("vLLM not installed. This script requires vLLM to be installed.")


# Default test prompts for different scenarios
DEFAULT_PROMPTS = {
    "short": [
        "Hello, how are you today?",
        "What is the capital of France?",
        "Explain quantum computing briefly.",
        "Write a haiku about the moon.",
    ],
    "medium": [
        "You are a helpful assistant. Please explain the concept of machine learning in simple terms that a beginner could understand. Include examples of how it's used in everyday life.",
        "Write a short story about a robot learning to paint. The story should include a beginning, middle, and end, with at least one plot twist.",
        "Describe the process of photosynthesis in detail, including the light-dependent and light-independent reactions. Use scientific terminology where appropriate.",
        "Create a detailed travel itinerary for a week-long trip to Japan, including recommendations for food, activities, and accommodations in Tokyo and Kyoto.",
    ],
    "long": [
        """You are an expert in artificial intelligence and machine learning. I need you to write a comprehensive guide on transformer architecture. 

Please cover the following topics in detail:
1. The historical context and motivation for transformers
2. Self-attention mechanism and how it works
3. Multi-head attention and its benefits
4. Positional encodings and why they're necessary
5. The encoder-decoder architecture
6. Pre-training and fine-tuning strategies
7. Common applications of transformers
8. Recent advances and variations (like GPT, BERT, T5)
9. Challenges and limitations
10. Future directions and research opportunities

Make sure to include mathematical formulations where appropriate and provide intuitive explanations for complex concepts.""",
    ],
    "prefix_caching": [
        "You are a helpful AI assistant that provides accurate and informative responses. User: What is the capital of France?",
        "You are a helpful AI assistant that provides accurate and informative responses. User: What is the capital of Germany?",
        "You are a helpful AI assistant that provides accurate and informative responses. User: What is the capital of Italy?",
        "You are a helpful AI assistant that provides accurate and informative responses. User: What is the capital of Spain?",
        "You are a helpful AI assistant that provides accurate and informative responses. User: What is the capital of Portugal?",
        "You are a helpful AI assistant that provides accurate and informative responses. User: What is the capital of Netherlands?",
        "You are a helpful AI assistant that provides accurate and informative responses. User: What is the capital of Belgium?",
        "You are a helpful AI assistant that provides accurate and informative responses. User: What is the capital of Austria?",
    ],
}


def detect_hardware_type() -> str:
    """Detect whether running on GPU or Neuron hardware."""
    import subprocess
    
    # Check for NVIDIA GPU
    try:
        result = subprocess.run(
            ['nvidia-smi'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return 'gpu'
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    # Check for Neuron
    try:
        result = subprocess.run(
            ['neuron-ls'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return 'neuron'
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    
    return 'unknown'


def get_instance_type() -> str:
    """Get the EC2 instance type."""
    import subprocess
    
    try:
        result = subprocess.run(
            ['curl', '-s', '--max-time', '2',
             'http://169.254.169.254/latest/meta-data/instance-type'],
            capture_output=True,
            text=True,
            timeout=3
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout.strip()
    except Exception:
        pass
    
    return 'unknown'


def create_llm_engine(
    model_name: str,
    hardware_type: str,
    enable_prefix_caching: bool = False,
    max_model_len: int = 4096,
    **kwargs
) -> LLM:
    """
    Create vLLM engine with appropriate settings for the hardware.
    
    Args:
        model_name: HuggingFace model name
        hardware_type: 'gpu' or 'neuron'
        enable_prefix_caching: Whether to enable prefix caching
        max_model_len: Maximum model context length
        **kwargs: Additional arguments for LLM
    
    Returns:
        Configured LLM instance
    """
    if not VLLM_AVAILABLE:
        raise ImportError("vLLM is not installed")
    
    common_args = {
        'model': model_name,
        'max_model_len': max_model_len,
        'enable_prefix_caching': enable_prefix_caching,
        'trust_remote_code': True,
    }
    
    if hardware_type == 'gpu':
        # GPU-specific settings
        common_args.update({
            'dtype': 'auto',
            'gpu_memory_utilization': 0.9,
        })
    elif hardware_type == 'neuron':
        # Neuron-specific settings
        # Note: Some settings may be handled by vllm-neuron plugin
        common_args.update({
            'device': 'neuron',
        })
    
    # Add any additional kwargs
    common_args.update(kwargs)
    
    print(f"Creating LLM engine with settings: {json.dumps(common_args, indent=2)}")
    
    return LLM(**common_args)


def run_batch_inference(
    llm: LLM,
    prompts: List[str],
    sampling_params: SamplingParams,
) -> Tuple[List[Any], float, Dict[str, Any]]:
    """
    Run batch inference and measure time.
    
    Args:
        llm: vLLM engine
        prompts: List of input prompts
        sampling_params: Sampling parameters
    
    Returns:
        Tuple of (outputs, total_time, timing_details)
    """
    start_time = time.perf_counter()
    
    outputs = llm.generate(prompts, sampling_params)
    
    end_time = time.perf_counter()
    total_time = end_time - start_time
    
    timing_details = {
        'start_time': start_time,
        'end_time': end_time,
        'total_time': total_time,
    }
    
    return outputs, total_time, timing_details


def calculate_metrics(
    outputs: List[Any],
    total_time: float,
    input_prompts: List[str],
) -> Dict[str, Any]:
    """
    Calculate metrics from inference outputs.
    
    Args:
        outputs: vLLM output objects
        total_time: Total inference time
        input_prompts: Original input prompts
    
    Returns:
        Dictionary of calculated metrics
    """
    total_input_tokens = 0
    total_output_tokens = 0
    
    for output in outputs:
        # Get token counts from output
        total_input_tokens += len(output.prompt_token_ids)
        
        for completion in output.outputs:
            total_output_tokens += len(completion.token_ids)
    
    metrics = {
        'total_time': total_time,
        'actual_input_tokens': total_input_tokens,
        'actual_output_tokens': total_output_tokens,
        'num_prompts': len(input_prompts),
        'tokens_per_second': total_output_tokens / total_time if total_time > 0 else 0,
        'time_per_token': (total_time * 1000) / total_output_tokens if total_output_tokens > 0 else 0,
    }
    
    return metrics


def run_scenario(
    llm: LLM,
    scenario_name: str,
    prompts: List[str],
    max_tokens: int,
    temperature: float,
    top_p: float,
    num_runs: int = 3,
) -> List[Dict[str, Any]]:
    """
    Run a benchmark scenario multiple times.
    
    Args:
        llm: vLLM engine
        scenario_name: Name of the scenario
        prompts: List of prompts to process
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature
        top_p: Top-p sampling parameter
        num_runs: Number of runs for averaging
    
    Returns:
        List of metrics dictionaries for each run
    """
    sampling_params = SamplingParams(
        max_tokens=max_tokens,
        temperature=temperature,
        top_p=top_p,
    )
    
    results = []
    
    for run_idx in range(num_runs):
        print(f"  Run {run_idx + 1}/{num_runs}...")
        
        # Warm-up run (first run)
        if run_idx == 0:
            print("    (Warm-up run)")
        
        outputs, total_time, timing = run_batch_inference(
            llm, prompts, sampling_params
        )
        
        metrics = calculate_metrics(outputs, total_time, prompts)
        metrics['run_index'] = run_idx
        metrics['scenario'] = scenario_name
        metrics['is_warmup'] = (run_idx == 0)
        
        results.append(metrics)
        
        print(f"    Time: {total_time:.2f}s, "
              f"Tokens/s: {metrics['tokens_per_second']:.2f}, "
              f"Output tokens: {metrics['actual_output_tokens']}")
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description='vLLM Offline Inference Benchmark'
    )
    
    # Model settings
    parser.add_argument(
        '--model', type=str,
        default='Qwen/Qwen3-0.6B-Instruct',
        help='Model name or path'
    )
    parser.add_argument(
        '--max-model-len', type=int,
        default=4096,
        help='Maximum model context length'
    )
    
    # Benchmark settings
    parser.add_argument(
        '--scenarios', type=str, nargs='+',
        default=['short', 'medium', 'prefix_caching'],
        choices=['short', 'medium', 'long', 'prefix_caching'],
        help='Scenarios to run'
    )
    parser.add_argument(
        '--num-runs', type=int, default=3,
        help='Number of runs per scenario'
    )
    parser.add_argument(
        '--batch-sizes', type=int, nargs='+',
        default=[1, 4],
        help='Batch sizes to test'
    )
    
    # Generation settings
    parser.add_argument(
        '--max-tokens', type=int, default=128,
        help='Maximum tokens to generate'
    )
    parser.add_argument(
        '--temperature', type=float, default=0.7,
        help='Sampling temperature'
    )
    parser.add_argument(
        '--top-p', type=float, default=0.9,
        help='Top-p sampling parameter'
    )
    
    # Prefix caching
    parser.add_argument(
        '--enable-prefix-caching', action='store_true',
        help='Enable prefix caching'
    )
    parser.add_argument(
        '--test-prefix-caching', action='store_true',
        help='Run comparison with and without prefix caching'
    )
    
    # Output settings
    parser.add_argument(
        '--output-dir', type=str,
        default='results',
        help='Directory for output files'
    )
    parser.add_argument(
        '--mlflow-uri', type=str,
        default='http://localhost:5000',
        help='MLflow tracking URI'
    )
    parser.add_argument(
        '--no-mlflow', action='store_true',
        help='Disable MLflow tracking'
    )
    
    args = parser.parse_args()
    
    # Check vLLM availability
    if not VLLM_AVAILABLE:
        print("ERROR: vLLM is not installed. Please install vLLM first.")
        sys.exit(1)
    
    # Detect hardware and instance type
    hardware_type = detect_hardware_type()
    instance_type = get_instance_type()
    
    print(f"Detected hardware type: {hardware_type}")
    print(f"Instance type: {instance_type}")
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Collect environment info
    env_info = collect_all_info()
    env_info['benchmark_config'] = vars(args)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    env_info_path = output_dir / f"env_info_{timestamp}.json"
    save_env_info(str(env_info_path))
    
    # Initialize metrics collector
    use_mlflow = not args.no_mlflow and MLFLOW_AVAILABLE
    
    if use_mlflow:
        collector = MLflowMetricsCollector(
            results_dir=str(output_dir),
            mlflow_tracking_uri=args.mlflow_uri,
            experiment_name="vllm-offline-benchmark",
            use_mlflow=True
        )
    else:
        collector = MetricsCollector(results_dir=str(output_dir))
    
    # Determine prefix caching configurations to test
    if args.test_prefix_caching:
        prefix_caching_configs = [False, True]
    else:
        prefix_caching_configs = [args.enable_prefix_caching]
    
    # Run benchmarks
    for enable_prefix_caching in prefix_caching_configs:
        print(f"\n{'='*60}")
        print(f"Prefix Caching: {'ENABLED' if enable_prefix_caching else 'DISABLED'}")
        print(f"{'='*60}\n")
        
        # Create LLM engine
        print(f"Loading model: {args.model}")
        llm = create_llm_engine(
            model_name=args.model,
            hardware_type=hardware_type,
            enable_prefix_caching=enable_prefix_caching,
            max_model_len=args.max_model_len,
        )
        
        # Run each scenario
        for scenario in args.scenarios:
            print(f"\n--- Scenario: {scenario} ---")
            
            prompts = DEFAULT_PROMPTS.get(scenario, DEFAULT_PROMPTS['short'])
            
            # Test different batch sizes
            for batch_size in args.batch_sizes:
                print(f"\nBatch size: {batch_size}")
                
                # Adjust prompts for batch size
                if batch_size > len(prompts):
                    # Repeat prompts to fill batch
                    batch_prompts = (prompts * ((batch_size // len(prompts)) + 1))[:batch_size]
                else:
                    batch_prompts = prompts[:batch_size]
                
                results = run_scenario(
                    llm=llm,
                    scenario_name=scenario,
                    prompts=batch_prompts,
                    max_tokens=args.max_tokens,
                    temperature=args.temperature,
                    top_p=args.top_p,
                    num_runs=args.num_runs,
                )
                
                # Record metrics (skip warmup for statistics)
                for result in results:
                    experiment_id = create_experiment_id(
                        instance_type, 'offline', scenario
                    )
                    
                    metric = BenchmarkMetrics(
                        experiment_id=experiment_id,
                        timestamp=datetime.now().isoformat(),
                        model_name=args.model,
                        instance_type=instance_type,
                        hardware_type=hardware_type,
                        serving_mode='offline',
                        batch_size=batch_size,
                        input_length=len(batch_prompts[0]) if batch_prompts else 0,
                        max_output_tokens=args.max_tokens,
                        enable_prefix_caching=enable_prefix_caching,
                        temperature=args.temperature,
                        top_p=args.top_p,
                        total_time=result['total_time'],
                        actual_input_tokens=result['actual_input_tokens'],
                        actual_output_tokens=result['actual_output_tokens'],
                        notes=f"scenario={scenario}, run={result['run_index']}, warmup={result['is_warmup']}"
                    )
                    
                    if use_mlflow:
                        collector.add_metric(metric, env_info)
                    else:
                        collector.add_metric(metric)
        
        # Clean up LLM engine
        del llm
    
    # Save results
    results_file = collector.save_to_json(f"offline_results_{timestamp}.json")
    collector.save_summary(f"offline_summary_{timestamp}.json")
    collector.print_summary()
    
    print(f"\nBenchmark complete. Results saved to: {output_dir}")


if __name__ == '__main__':
    main()
