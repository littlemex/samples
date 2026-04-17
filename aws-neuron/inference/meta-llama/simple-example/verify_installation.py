#!/usr/bin/env python3
"""
NxD Inference インストール検証スクリプト
"""
import sys

def main():
    print("=" * 80)
    print("NxD Inference Installation Verification")
    print("=" * 80)
    
    # Test 1: torch-neuronx
    print("\n[TEST 1/4] torch-neuronx import")
    try:
        import torch_neuronx
        print(f"[PASS] torch-neuronx: {torch_neuronx.__version__}")
    except Exception as e:
        print(f"[FAIL] {e}")
        sys.exit(1)
    
    # Test 2: neuronx-cc (正しい import 名)
    print("\n[TEST 2/4] neuronx-cc import")
    try:
        import neuronxcc
        print(f"[PASS] neuronxcc: {neuronxcc.__version__}")
    except Exception as e:
        # neuronxcc で失敗したら neuronx_cc も試す
        try:
            import neuronx_cc
            print(f"[PASS] neuronx_cc: {neuronx_cc.__version__}")
        except Exception as e2:
            print(f"[FAIL] Both 'neuronxcc' and 'neuronx_cc' failed: {e}, {e2}")
            sys.exit(1)
    
    # Test 3: NxD Inference
    print("\n[TEST 3/4] NxD Inference import")
    try:
        import neuronx_distributed_inference
        print(f"[PASS] neuronx-distributed-inference: {neuronx_distributed_inference.__version__}")
    except Exception as e:
        print(f"[FAIL] {e}")
        sys.exit(1)
    
    # Test 4: NxD Inference API
    print("\n[TEST 4/4] NxD Inference API test")
    try:
        from neuronx_distributed_inference.models.config import InferenceConfig
        from neuronx_distributed_inference.models.model_wrapper import ModelWrapper
        print("[PASS] NxD Inference APIs accessible")
    except Exception as e:
        print(f"[FAIL] {e}")
        sys.exit(1)
    
    print("\n" + "=" * 80)
    print("[SUCCESS] All tests passed!")
    print("=" * 80)

if __name__ == "__main__":
    main()
