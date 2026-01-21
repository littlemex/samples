#!/usr/bin/env python3
"""
Analyze and visualize vLLM benchmark results.
"""
import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np


def load_results(results_file: str) -> Dict[str, Any]:
    """Load benchmark results from JSON file."""
    with open(results_file, 'r') as f:
        data = json.load(f)
    return data


def results_to_dataframe(results_data: Dict[str, Any]) -> pd.DataFrame:
    """Convert results to pandas DataFrame."""
    results = results_data.get('results', [])
    return pd.DataFrame(results)


def plot_tokens_per_second_comparison(
    df: pd.DataFrame,
    output_path: str,
    figsize: tuple = (12, 6)
):
    """Plot tokens per second comparison across configurations."""
    plt.figure(figsize=figsize)
    
    # Filter out warmup runs
    df_plot = df[df.get('notes', '').str.contains('warmup=False', na=False)].copy()
    
    if df_plot.empty:
        print("Warning: No non-warmup data found for plotting")
        return
    
    # Create comparison groups
    df_plot['config'] = (
        df_plot['instance_type'].astype(str) + '\n' +
        df_plot['serving_mode'].astype(str) + '\n' +
        'BS=' + df_plot['batch_size'].astype(str) + '\n' +
        'Cache=' + df_plot['enable_prefix_caching'].astype(str)
    )
    
    # Create bar plot
    sns.barplot(
        data=df_plot,
        x='config',
        y='tokens_per_second',
        hue='instance_type',
        ci='sd',
        palette='Set2'
    )
    
    plt.title('Tokens per Second Comparison', fontsize=14, fontweight='bold')
    plt.xlabel('Configuration', fontsize=12)
    plt.ylabel('Tokens/Second', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.legend(title='Instance Type')
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved plot: {output_path}")
    plt.close()


def plot_prefix_caching_effect(
    df: pd.DataFrame,
    output_path: str,
    figsize: tuple = (10, 6)
):
    """Plot the effect of prefix caching."""
    plt.figure(figsize=figsize)
    
    # Filter data
    df_plot = df[df.get('notes', '').str.contains('warmup=False', na=False)].copy()
    
    if df_plot.empty:
        print("Warning: No data for prefix caching plot")
        return
    
    # Group by instance_type and prefix_caching
    grouped = df_plot.groupby(['instance_type', 'enable_prefix_caching'])['tokens_per_second'].mean().reset_index()
    
    # Create grouped bar plot
    x = np.arange(len(grouped['instance_type'].unique()))
    width = 0.35
    
    cache_off = grouped[grouped['enable_prefix_caching'] == False]
    cache_on = grouped[grouped['enable_prefix_caching'] == True]
    
    plt.bar(x - width/2, cache_off['tokens_per_second'], width, label='Cache OFF', alpha=0.8)
    plt.bar(x + width/2, cache_on['tokens_per_second'], width, label='Cache ON', alpha=0.8)
    
    plt.title('Prefix Caching Effect on Performance', fontsize=14, fontweight='bold')
    plt.xlabel('Instance Type', fontsize=12)
    plt.ylabel('Avg Tokens/Second', fontsize=12)
    plt.xticks(x, cache_off['instance_type'].unique())
    plt.legend()
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved plot: {output_path}")
    plt.close()


def plot_batch_size_scaling(
    df: pd.DataFrame,
    output_path: str,
    figsize: tuple = (10, 6)
):
    """Plot performance scaling with batch size."""
    plt.figure(figsize=figsize)
    
    # Filter data
    df_plot = df[df.get('notes', '').str.contains('warmup=False', na=False)].copy()
    
    if df_plot.empty:
        print("Warning: No data for batch size scaling plot")
        return
    
    # Group by instance type
    for instance_type in df_plot['instance_type'].unique():
        instance_data = df_plot[df_plot['instance_type'] == instance_type]
        
        # Group by batch size
        grouped = instance_data.groupby('batch_size')['tokens_per_second'].mean()
        
        plt.plot(
            grouped.index,
            grouped.values,
            marker='o',
            linewidth=2,
            markersize=8,
            label=instance_type
        )
    
    plt.title('Performance Scaling with Batch Size', fontsize=14, fontweight='bold')
    plt.xlabel('Batch Size', fontsize=12)
    plt.ylabel('Avg Tokens/Second', fontsize=12)
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved plot: {output_path}")
    plt.close()


def plot_time_per_token_comparison(
    df: pd.DataFrame,
    output_path: str,
    figsize: tuple = (12, 6)
):
    """Plot time per token comparison (lower is better)."""
    plt.figure(figsize=figsize)
    
    # Filter data
    df_plot = df[df.get('notes', '').str.contains('warmup=False', na=False)].copy()
    
    if df_plot.empty:
        print("Warning: No data for time per token plot")
        return
    
    # Create comparison groups
    df_plot['config'] = (
        df_plot['instance_type'].astype(str) + '\n' +
        'BS=' + df_plot['batch_size'].astype(str)
    )
    
    # Create bar plot
    sns.barplot(
        data=df_plot,
        x='config',
        y='time_per_token',
        hue='instance_type',
        ci='sd',
        palette='Set2'
    )
    
    plt.title('Time per Token Comparison (Lower is Better)', fontsize=14, fontweight='bold')
    plt.xlabel('Configuration', fontsize=12)
    plt.ylabel('Time per Token (ms)', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.legend(title='Instance Type')
    plt.grid(axis='y', alpha=0.3)
    plt.tight_layout()
    
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"Saved plot: {output_path}")
    plt.close()


def generate_summary_report(df: pd.DataFrame, output_path: str):
    """Generate a text summary report."""
    with open(output_path, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("vLLM Benchmark Summary Report\n")
        f.write("=" * 80 + "\n\n")
        
        # Overall statistics
        f.write("Overall Statistics:\n")
        f.write("-" * 80 + "\n")
        f.write(f"Total runs: {len(df)}\n")
        f.write(f"Instance types: {', '.join(df['instance_type'].unique())}\n")
        f.write(f"Models tested: {', '.join(df['model_name'].unique())}\n\n")
        
        # Performance by instance type
        f.write("Performance by Instance Type:\n")
        f.write("-" * 80 + "\n")
        
        for instance_type in df['instance_type'].unique():
            instance_data = df[df['instance_type'] == instance_type]
            
            # Filter out warmup
            instance_data = instance_data[
                instance_data.get('notes', '').str.contains('warmup=False', na=False)
            ]
            
            if instance_data.empty:
                continue
            
            f.write(f"\n{instance_type}:\n")
            f.write(f"  Avg tokens/sec: {instance_data['tokens_per_second'].mean():.2f} " +
                   f"(±{instance_data['tokens_per_second'].std():.2f})\n")
            f.write(f"  Avg time/token: {instance_data['time_per_token'].mean():.2f} ms " +
                   f"(±{instance_data['time_per_token'].std():.2f})\n")
            f.write(f"  Best tokens/sec: {instance_data['tokens_per_second'].max():.2f}\n")
            f.write(f"  Worst tokens/sec: {instance_data['tokens_per_second'].min():.2f}\n")
        
        # Prefix caching effect
        f.write("\nPrefix Caching Effect:\n")
        f.write("-" * 80 + "\n")
        
        for instance_type in df['instance_type'].unique():
            instance_data = df[
                (df['instance_type'] == instance_type) &
                (df.get('notes', '').str.contains('warmup=False', na=False))
            ]
            
            if instance_data.empty:
                continue
            
            cache_off = instance_data[instance_data['enable_prefix_caching'] == False]['tokens_per_second'].mean()
            cache_on = instance_data[instance_data['enable_prefix_caching'] == True]['tokens_per_second'].mean()
            
            if pd.notna(cache_off) and pd.notna(cache_on):
                improvement = ((cache_on - cache_off) / cache_off) * 100
                f.write(f"\n{instance_type}:\n")
                f.write(f"  Without caching: {cache_off:.2f} tokens/sec\n")
                f.write(f"  With caching: {cache_on:.2f} tokens/sec\n")
                f.write(f"  Improvement: {improvement:+.1f}%\n")
        
        f.write("\n" + "=" * 80 + "\n")
    
    print(f"Saved report: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Analyze and visualize vLLM benchmark results'
    )
    
    parser.add_argument(
        '--results-file', type=str, required=True,
        help='Path to benchmark results JSON file'
    )
    parser.add_argument(
        '--output-dir', type=str, default='analysis',
        help='Directory for output plots and reports'
    )
    parser.add_argument(
        '--plots', type=str, nargs='+',
        default=['all'],
        choices=['all', 'tokens_per_sec', 'prefix_caching', 'batch_scaling', 'time_per_token'],
        help='Which plots to generate'
    )
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load results
    print(f"Loading results from: {args.results_file}")
    results_data = load_results(args.results_file)
    
    # Convert to DataFrame
    df = results_to_dataframe(results_data)
    
    if df.empty:
        print("ERROR: No data found in results file")
        sys.exit(1)
    
    print(f"Loaded {len(df)} benchmark results")
    print(f"Instance types: {df['instance_type'].unique()}")
    
    # Generate plots
    plots_to_generate = args.plots
    if 'all' in plots_to_generate:
        plots_to_generate = ['tokens_per_sec', 'prefix_caching', 'batch_scaling', 'time_per_token']
    
    if 'tokens_per_sec' in plots_to_generate:
        plot_tokens_per_second_comparison(
            df,
            output_dir / 'tokens_per_sec_comparison.png'
        )
    
    if 'prefix_caching' in plots_to_generate:
        plot_prefix_caching_effect(
            df,
            output_dir / 'prefix_caching_effect.png'
        )
    
    if 'batch_scaling' in plots_to_generate:
        plot_batch_size_scaling(
            df,
            output_dir / 'batch_size_scaling.png'
        )
    
    if 'time_per_token' in plots_to_generate:
        plot_time_per_token_comparison(
            df,
            output_dir / 'time_per_token_comparison.png'
        )
    
    # Generate summary report
    generate_summary_report(df, output_dir / 'summary_report.txt')
    
    print(f"\nAnalysis complete. Results saved to: {output_dir}")


if __name__ == '__main__':
    main()
