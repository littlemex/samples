#!/usr/bin/env python3
"""
vLLM Neuron インストール検証スクリプト
"""
import sys

def main():
    print("=" * 80)
    print("vLLM Neuron Installation Verification")
    print("=" * 80)

    # Test 1: vLLM
    print("\n[TEST 1/3] vLLM import")
    try:
        import vllm
        print(f"[PASS] vLLM: {vllm.__version__}")
    except Exception as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    # Test 2: torch-neuronx
    print("\n[TEST 2/3] torch-neuronx import")
    try:
        import torch_neuronx
        print(f"[PASS] torch-neuronx: {torch_neuronx.__version__}")
    except Exception as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    # Test 3: neuronx-distributed-inference
    print("\n[TEST 3/3] neuronx-distributed-inference import")
    try:
        import neuronx_distributed_inference
        print(f"[PASS] neuronx-distributed-inference: {neuronx_distributed_inference.__version__}")
    except Exception as e:
        print(f"[FAIL] {e}")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("[SUCCESS] All tests passed!")
    print("=" * 80)

if __name__ == "__main__":
    main()

