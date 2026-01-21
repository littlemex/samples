"""
Environment information collection module for vLLM benchmarking.
Collects system, hardware, and software configuration details.
"""
import json
import os
import platform
import subprocess
from datetime import datetime
from typing import Dict, Any, Optional


def get_cpu_info() -> Dict[str, Any]:
    """Get CPU information."""
    try:
        with open('/proc/cpuinfo', 'r') as f:
            lines = f.readlines()
        
        model_name = None
        for line in lines:
            if 'model name' in line:
                model_name = line.split(':')[1].strip()
                break
        
        cpu_count = os.cpu_count()
        
        return {
            'model': model_name,
            'count': cpu_count,
            'architecture': platform.machine()
        }
    except Exception as e:
        return {'error': str(e)}


def get_memory_info() -> Dict[str, Any]:
    """Get memory information."""
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
        
        mem_info = {}
        for line in lines:
            if 'MemTotal' in line or 'MemAvailable' in line:
                key, value = line.split(':')
                mem_info[key.strip()] = value.strip()
        
        return mem_info
    except Exception as e:
        return {'error': str(e)}


def get_gpu_info() -> Dict[str, Any]:
    """Get GPU information using nvidia-smi."""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,driver_version,memory.total', '--format=csv,noheader'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            gpu_info = result.stdout.strip().split(', ')
            return {
                'name': gpu_info[0] if len(gpu_info) > 0 else None,
                'driver_version': gpu_info[1] if len(gpu_info) > 1 else None,
                'memory_total': gpu_info[2] if len(gpu_info) > 2 else None,
                'type': 'NVIDIA'
            }
        else:
            return {'type': 'Not available', 'error': result.stderr}
    except FileNotFoundError:
        return {'type': 'nvidia-smi not found'}
    except Exception as e:
        return {'type': 'Error', 'error': str(e)}


def get_neuron_info() -> Dict[str, Any]:
    """Get AWS Neuron information."""
    try:
        # Check if neuron-ls is available
        result = subprocess.run(
            ['neuron-ls'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return {
                'available': True,
                'output': result.stdout.strip(),
                'type': 'AWS Inferentia/Trainium'
            }
        else:
            return {'available': False, 'type': 'Not available'}
    except FileNotFoundError:
        return {'available': False, 'type': 'neuron-ls not found'}
    except Exception as e:
        return {'available': False, 'error': str(e)}


def get_python_packages() -> Dict[str, str]:
    """Get installed Python packages relevant to vLLM."""
    packages = [
        'vllm',
        'torch',
        'transformers',
        'accelerate',
        'neuronx-cc',
        'torch-neuronx',
        'neuronx-distributed',
    ]
    
    versions = {}
    for package in packages:
        try:
            result = subprocess.run(
                ['pip', 'show', package],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.startswith('Version:'):
                        versions[package] = line.split(':')[1].strip()
                        break
            else:
                versions[package] = 'Not installed'
        except Exception as e:
            versions[package] = f'Error: {str(e)}'
    
    return versions


def get_environment_variables() -> Dict[str, str]:
    """Get relevant environment variables."""
    env_vars = [
        'CUDA_VISIBLE_DEVICES',
        'NEURON_RT_NUM_CORES',
        'NEURON_COMPILE_CACHE_URL',
        'NEURON_CC_FLAGS',
        'VLLM_USE_MODELSCOPE',
        'HF_HOME',
        'TRANSFORMERS_CACHE',
    ]
    
    return {var: os.environ.get(var, 'Not set') for var in env_vars}


def get_instance_metadata() -> Dict[str, Any]:
    """Get EC2 instance metadata if available."""
    try:
        # Try to get instance metadata
        result = subprocess.run(
            ['curl', '-s', '--max-time', '2', 
             'http://169.254.169.254/latest/meta-data/instance-type'],
            capture_output=True,
            text=True,
            timeout=3
        )
        
        if result.returncode == 0 and result.stdout:
            instance_type = result.stdout.strip()
            
            # Get availability zone
            az_result = subprocess.run(
                ['curl', '-s', '--max-time', '2',
                 'http://169.254.169.254/latest/meta-data/placement/availability-zone'],
                capture_output=True,
                text=True,
                timeout=3
            )
            
            return {
                'instance_type': instance_type,
                'availability_zone': az_result.stdout.strip() if az_result.returncode == 0 else 'Unknown',
                'provider': 'AWS EC2'
            }
        else:
            return {'provider': 'Not EC2 or metadata unavailable'}
    except Exception as e:
        return {'provider': 'Unknown', 'error': str(e)}


def collect_all_info() -> Dict[str, Any]:
    """Collect all environment information."""
    return {
        'timestamp': datetime.now().isoformat(),
        'platform': {
            'system': platform.system(),
            'release': platform.release(),
            'version': platform.version(),
            'python_version': platform.python_version(),
        },
        'cpu': get_cpu_info(),
        'memory': get_memory_info(),
        'gpu': get_gpu_info(),
        'neuron': get_neuron_info(),
        'instance': get_instance_metadata(),
        'python_packages': get_python_packages(),
        'environment_variables': get_environment_variables(),
    }


def save_env_info(output_path: str, additional_info: Optional[Dict[str, Any]] = None) -> str:
    """
    Collect and save environment information to a JSON file.
    
    Args:
        output_path: Path to save the environment info JSON file
        additional_info: Additional custom information to include
    
    Returns:
        Path to the saved file
    """
    env_info = collect_all_info()
    
    if additional_info:
        env_info['additional_info'] = additional_info
    
    with open(output_path, 'w') as f:
        json.dump(env_info, f, indent=2)
    
    print(f"Environment information saved to: {output_path}")
    return output_path


if __name__ == '__main__':
    # Test the module
    info = collect_all_info()
    print(json.dumps(info, indent=2))
