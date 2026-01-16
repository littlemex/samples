#!/usr/bin/env python3
"""
Merge multiple benchmark result JSON files from different instances.
This is useful when you've run benchmarks on both g5 and inf2 instances
and want to analyze them together.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


def load_results_file(filepath: str) -> Dict[str, Any]:
    """Load a single results JSON file."""
    with open(filepath, 'r') as f:
        return json.load(f)


def merge_results(result_files: List[str]) -> Dict[str, Any]:
    """
    Merge multiple result files into a single structure.
    
    Args:
        result_files: List of paths to result JSON files
    
    Returns:
        Merged results dictionary
    """
    merged = {
        'metadata': {
            'merged_at': datetime.now().isoformat(),
            'source_files': result_files,
            'total_runs': 0,
        },
        'results': []
    }
    
    for filepath in result_files:
        print(f"Loading: {filepath}")
        try:
            data = load_results_file(filepath)
            
            # Extract results
            results = data.get('results', [])
            merged['results'].extend(results)
            
            print(f"  Added {len(results)} runs")
            
        except Exception as e:
            print(f"  ERROR: Failed to load {filepath}: {e}")
            continue
    
    merged['metadata']['total_runs'] = len(merged['results'])
    
    return merged


def main():
    parser = argparse.ArgumentParser(
        description='Merge benchmark results from multiple instances'
    )
    
    parser.add_argument(
        'result_files', nargs='+',
        help='Result JSON files to merge'
    )
    parser.add_argument(
        '--output', '-o', type=str,
        default='merged_results.json',
        help='Output filename for merged results'
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Merging Benchmark Results")
    print("=" * 60)
    print(f"Input files: {len(args.result_files)}")
    print()
    
    # Merge results
    merged_data = merge_results(args.result_files)
    
    # Save merged results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w') as f:
        json.dump(merged_data, f, indent=2)
    
    print()
    print("=" * 60)
    print(f"Merge complete!")
    print(f"Total runs: {merged_data['metadata']['total_runs']}")
    print(f"Output saved to: {output_path}")
    print("=" * 60)
    
    # Show instance types in merged data
    instance_types = set()
    for result in merged_data['results']:
        instance_types.add(result.get('instance_type', 'unknown'))
    
    if instance_types:
        print(f"\nInstance types in merged data: {', '.join(sorted(instance_types))}")


if __name__ == '__main__':
    main()
