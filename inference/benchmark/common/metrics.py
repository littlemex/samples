"""
Metrics collection and storage module for vLLM benchmarking.
Handles performance metrics recording and normalization.
Supports both JSON file storage and MLflow tracking.
"""
import json
import os
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

# Optional MLflow import
try:
    import mlflow
    from mlflow.tracking import MlflowClient
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    print("MLflow not installed. Install with: pip install mlflow")


@dataclass
class BenchmarkMetrics:
    """Metrics for a single benchmark run."""
    # Experiment metadata
    experiment_id: str
    timestamp: str
    model_name: str
    instance_type: str
    hardware_type: str  # 'gpu' or 'neuron'
    serving_mode: str  # 'online' or 'offline'
    
    # Configuration
    batch_size: int
    input_length: int
    max_output_tokens: int
    enable_prefix_caching: bool
    temperature: float
    top_p: float
    
    # Raw measurements
    total_time: float  # seconds
    prefill_time: Optional[float] = None  # seconds
    decode_time: Optional[float] = None  # seconds
    first_token_latency: Optional[float] = None  # seconds (TTFT)
    
    # Token counts
    actual_input_tokens: int = 0
    actual_output_tokens: int = 0
    
    # Normalized metrics (computed)
    tokens_per_second: Optional[float] = None
    time_per_token: Optional[float] = None  # milliseconds
    inter_token_latency: Optional[float] = None  # milliseconds (avg time between tokens)
    
    # Resource utilization
    memory_used_mb: Optional[float] = None
    peak_memory_mb: Optional[float] = None
    
    # Prefix caching metrics
    cache_hit_rate: Optional[float] = None
    
    # Additional metadata
    error: Optional[str] = None
    notes: Optional[str] = None
    
    def compute_derived_metrics(self):
        """Compute derived metrics from raw measurements."""
        if self.actual_output_tokens > 0 and self.total_time > 0:
            self.tokens_per_second = self.actual_output_tokens / self.total_time
            self.time_per_token = (self.total_time * 1000) / self.actual_output_tokens  # ms
        
        if self.decode_time and self.actual_output_tokens > 1:
            # Inter-token latency (excluding first token)
            self.inter_token_latency = (self.decode_time * 1000) / (self.actual_output_tokens - 1)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class MetricsCollector:
    """Collects and manages benchmark metrics."""
    
    def __init__(self, results_dir: str = "results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.metrics: List[BenchmarkMetrics] = []
    
    def add_metric(self, metric: BenchmarkMetrics):
        """Add a metric to the collection."""
        metric.compute_derived_metrics()
        self.metrics.append(metric)
    
    def save_to_json(self, filename: Optional[str] = None) -> str:
        """
        Save metrics to a JSON file.
        
        Args:
            filename: Optional filename. If None, uses timestamp.
        
        Returns:
            Path to saved file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"benchmark_results_{timestamp}.json"
        
        filepath = self.results_dir / filename
        
        data = {
            'metadata': {
                'total_runs': len(self.metrics),
                'generated_at': datetime.now().isoformat()
            },
            'results': [m.to_dict() for m in self.metrics]
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Metrics saved to: {filepath}")
        return str(filepath)
    
    def save_summary(self, filename: Optional[str] = None) -> str:
        """
        Save a summary of metrics grouped by configuration.
        
        Args:
            filename: Optional filename. If None, uses timestamp.
        
        Returns:
            Path to saved file
        """
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"benchmark_summary_{timestamp}.json"
        
        filepath = self.results_dir / filename
        
        # Group by key dimensions
        groups: Dict[str, List[BenchmarkMetrics]] = {}
        
        for metric in self.metrics:
            key = (
                f"{metric.instance_type}_{metric.serving_mode}_"
                f"bs{metric.batch_size}_in{metric.input_length}_"
                f"out{metric.max_output_tokens}_"
                f"cache{metric.enable_prefix_caching}"
            )
            
            if key not in groups:
                groups[key] = []
            groups[key].append(metric)
        
        # Compute statistics for each group
        summary = {}
        for key, metrics_list in groups.items():
            if not metrics_list:
                continue
            
            tokens_per_sec = [m.tokens_per_second for m in metrics_list if m.tokens_per_second]
            time_per_token = [m.time_per_token for m in metrics_list if m.time_per_token]
            first_token_lat = [m.first_token_latency for m in metrics_list if m.first_token_latency]
            
            summary[key] = {
                'count': len(metrics_list),
                'instance_type': metrics_list[0].instance_type,
                'serving_mode': metrics_list[0].serving_mode,
                'batch_size': metrics_list[0].batch_size,
                'input_length': metrics_list[0].input_length,
                'max_output_tokens': metrics_list[0].max_output_tokens,
                'enable_prefix_caching': metrics_list[0].enable_prefix_caching,
                'tokens_per_second': {
                    'mean': sum(tokens_per_sec) / len(tokens_per_sec) if tokens_per_sec else None,
                    'min': min(tokens_per_sec) if tokens_per_sec else None,
                    'max': max(tokens_per_sec) if tokens_per_sec else None,
                },
                'time_per_token_ms': {
                    'mean': sum(time_per_token) / len(time_per_token) if time_per_token else None,
                    'min': min(time_per_token) if time_per_token else None,
                    'max': max(time_per_token) if time_per_token else None,
                },
                'first_token_latency_sec': {
                    'mean': sum(first_token_lat) / len(first_token_lat) if first_token_lat else None,
                    'min': min(first_token_lat) if first_token_lat else None,
                    'max': max(first_token_lat) if first_token_lat else None,
                },
            }
        
        data = {
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'total_configurations': len(summary)
            },
            'summary': summary
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Summary saved to: {filepath}")
        return str(filepath)
    
    def print_summary(self):
        """Print a summary of collected metrics."""
        if not self.metrics:
            print("No metrics collected yet.")
            return
        
        print(f"\n{'='*80}")
        print(f"Benchmark Summary ({len(self.metrics)} runs)")
        print(f"{'='*80}\n")
        
        # Group by instance type and serving mode
        groups: Dict[str, List[BenchmarkMetrics]] = {}
        for metric in self.metrics:
            key = f"{metric.instance_type}_{metric.serving_mode}"
            if key not in groups:
                groups[key] = []
            groups[key].append(metric)
        
        for key, metrics_list in sorted(groups.items()):
            print(f"\n{key}:")
            print(f"{'-'*80}")
            
            for metric in metrics_list:
                prefix_cache_str = "✓" if metric.enable_prefix_caching else "✗"
                print(
                    f"  BS={metric.batch_size:2d} | "
                    f"In={metric.input_length:4d} | "
                    f"Out={metric.actual_output_tokens:3d}/{metric.max_output_tokens:3d} | "
                    f"Cache:{prefix_cache_str} | "
                    f"{metric.tokens_per_second:6.2f} tok/s | "
                    f"{metric.time_per_token:6.2f} ms/tok"
                )
        
        print(f"\n{'='*80}\n")


def create_experiment_id(instance_type: str, serving_mode: str, scenario: str) -> str:
    """Create a unique experiment ID."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{instance_type}_{serving_mode}_{scenario}_{timestamp}"


class MLflowTracker:
    """MLflow tracking integration for benchmark metrics."""
    
    def __init__(
        self,
        tracking_uri: str = "http://localhost:5000",
        experiment_name: str = "vllm-benchmark"
    ):
        """
        Initialize MLflow tracker.
        
        Args:
            tracking_uri: MLflow tracking server URI
            experiment_name: Name of the MLflow experiment
        """
        if not MLFLOW_AVAILABLE:
            raise ImportError("MLflow is not installed. Install with: pip install mlflow")
        
        self.tracking_uri = tracking_uri
        self.experiment_name = experiment_name
        
        # Set tracking URI
        mlflow.set_tracking_uri(tracking_uri)
        
        # Create or get experiment
        self.client = MlflowClient()
        experiment = self.client.get_experiment_by_name(experiment_name)
        
        if experiment is None:
            self.experiment_id = self.client.create_experiment(experiment_name)
            print(f"Created new MLflow experiment: {experiment_name}")
        else:
            self.experiment_id = experiment.experiment_id
            print(f"Using existing MLflow experiment: {experiment_name}")
        
        mlflow.set_experiment(experiment_name)
    
    def log_metric(self, metric: BenchmarkMetrics, env_info: Optional[Dict[str, Any]] = None):
        """
        Log a single benchmark metric to MLflow.
        
        Args:
            metric: Benchmark metrics to log
            env_info: Optional environment information to log as parameters
        """
        # Ensure derived metrics are computed
        metric.compute_derived_metrics()
        
        with mlflow.start_run(run_name=metric.experiment_id):
            # Log parameters (configuration)
            mlflow.log_params({
                'model_name': metric.model_name,
                'instance_type': metric.instance_type,
                'hardware_type': metric.hardware_type,
                'serving_mode': metric.serving_mode,
                'batch_size': metric.batch_size,
                'input_length': metric.input_length,
                'max_output_tokens': metric.max_output_tokens,
                'enable_prefix_caching': metric.enable_prefix_caching,
                'temperature': metric.temperature,
                'top_p': metric.top_p,
            })
            
            # Log metrics
            metrics_to_log = {
                'total_time': metric.total_time,
                'actual_input_tokens': metric.actual_input_tokens,
                'actual_output_tokens': metric.actual_output_tokens,
            }
            
            # Add optional metrics if available
            if metric.tokens_per_second is not None:
                metrics_to_log['tokens_per_second'] = metric.tokens_per_second
            if metric.time_per_token is not None:
                metrics_to_log['time_per_token_ms'] = metric.time_per_token
            if metric.prefill_time is not None:
                metrics_to_log['prefill_time'] = metric.prefill_time
            if metric.decode_time is not None:
                metrics_to_log['decode_time'] = metric.decode_time
            if metric.first_token_latency is not None:
                metrics_to_log['first_token_latency'] = metric.first_token_latency
            if metric.inter_token_latency is not None:
                metrics_to_log['inter_token_latency_ms'] = metric.inter_token_latency
            if metric.memory_used_mb is not None:
                metrics_to_log['memory_used_mb'] = metric.memory_used_mb
            if metric.peak_memory_mb is not None:
                metrics_to_log['peak_memory_mb'] = metric.peak_memory_mb
            if metric.cache_hit_rate is not None:
                metrics_to_log['cache_hit_rate'] = metric.cache_hit_rate
            
            mlflow.log_metrics(metrics_to_log)
            
            # Log tags
            mlflow.set_tags({
                'experiment_id': metric.experiment_id,
                'timestamp': metric.timestamp,
            })
            
            if metric.error:
                mlflow.set_tag('error', metric.error)
            if metric.notes:
                mlflow.set_tag('notes', metric.notes)
            
            # Log environment info if provided
            if env_info:
                # Log as artifact
                env_info_path = f"/tmp/env_info_{metric.experiment_id}.json"
                with open(env_info_path, 'w') as f:
                    json.dump(env_info, f, indent=2)
                mlflow.log_artifact(env_info_path, "environment")
                os.remove(env_info_path)
        
        print(f"Logged metric to MLflow: {metric.experiment_id}")
    
    def log_multiple_metrics(
        self, 
        metrics: List[BenchmarkMetrics], 
        env_info: Optional[Dict[str, Any]] = None
    ):
        """
        Log multiple benchmark metrics to MLflow.
        
        Args:
            metrics: List of benchmark metrics to log
            env_info: Optional environment information to log
        """
        for metric in metrics:
            self.log_metric(metric, env_info)
    
    def get_all_runs(self) -> List[Dict[str, Any]]:
        """
        Get all runs from the current experiment.
        
        Returns:
            List of run data dictionaries
        """
        runs = self.client.search_runs(
            experiment_ids=[self.experiment_id],
            order_by=["start_time DESC"]
        )
        
        return [
            {
                'run_id': run.info.run_id,
                'run_name': run.info.run_name,
                'status': run.info.status,
                'start_time': run.info.start_time,
                'params': run.data.params,
                'metrics': run.data.metrics,
                'tags': run.data.tags,
            }
            for run in runs
        ]
    
    def compare_runs(
        self, 
        metric_names: List[str] = None
    ) -> Dict[str, Any]:
        """
        Compare all runs and return a summary.
        
        Args:
            metric_names: List of metric names to compare. 
                         If None, uses default metrics.
        
        Returns:
            Dictionary with comparison results
        """
        if metric_names is None:
            metric_names = [
                'tokens_per_second',
                'time_per_token_ms',
                'first_token_latency',
                'total_time'
            ]
        
        runs = self.get_all_runs()
        
        comparison = {
            'total_runs': len(runs),
            'metric_comparison': {}
        }
        
        for metric_name in metric_names:
            values = [
                run['metrics'].get(metric_name)
                for run in runs
                if metric_name in run['metrics']
            ]
            
            if values:
                comparison['metric_comparison'][metric_name] = {
                    'min': min(values),
                    'max': max(values),
                    'mean': sum(values) / len(values),
                    'count': len(values)
                }
        
        return comparison


class MLflowMetricsCollector(MetricsCollector):
    """
    Extended MetricsCollector with MLflow integration.
    Automatically logs metrics to both JSON files and MLflow.
    """
    
    def __init__(
        self,
        results_dir: str = "results",
        mlflow_tracking_uri: str = "http://localhost:5000",
        experiment_name: str = "vllm-benchmark",
        use_mlflow: bool = True
    ):
        super().__init__(results_dir)
        
        self.use_mlflow = use_mlflow and MLFLOW_AVAILABLE
        self.mlflow_tracker = None
        
        if self.use_mlflow:
            try:
                self.mlflow_tracker = MLflowTracker(
                    tracking_uri=mlflow_tracking_uri,
                    experiment_name=experiment_name
                )
            except Exception as e:
                print(f"Failed to initialize MLflow: {e}")
                print("Falling back to JSON-only storage.")
                self.use_mlflow = False
    
    def add_metric(
        self, 
        metric: BenchmarkMetrics, 
        env_info: Optional[Dict[str, Any]] = None
    ):
        """
        Add a metric and optionally log to MLflow.
        
        Args:
            metric: Benchmark metrics to add
            env_info: Optional environment information
        """
        # Call parent to add to list
        super().add_metric(metric)
        
        # Log to MLflow if enabled
        if self.use_mlflow and self.mlflow_tracker:
            try:
                self.mlflow_tracker.log_metric(metric, env_info)
            except Exception as e:
                print(f"Failed to log to MLflow: {e}")


if __name__ == '__main__':
    # Test the module
    collector = MetricsCollector("test_results")
    
    # Add a sample metric
    metric = BenchmarkMetrics(
        experiment_id="test_001",
        timestamp=datetime.now().isoformat(),
        model_name="Qwen/Qwen3-0.6B-Instruct",
        instance_type="g5.xlarge",
        hardware_type="gpu",
        serving_mode="offline",
        batch_size=1,
        input_length=32,
        max_output_tokens=32,
        enable_prefix_caching=False,
        temperature=0.7,
        top_p=0.9,
        total_time=2.5,
        actual_input_tokens=32,
        actual_output_tokens=28,
    )
    
    collector.add_metric(metric)
    collector.print_summary()
    collector.save_to_json("test_metrics.json")
