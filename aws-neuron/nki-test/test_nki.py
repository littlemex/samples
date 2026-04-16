#!/usr/bin/env python3
"""
Simple NKI import test to verify NKI 0.3.0 installation on Trainium.
"""
import sys

def main():
    print("[INFO] Starting NKI import test...")

    # Test NKI import
    try:
        import nki
        print(f"[OK] NKI imported successfully")
        print(f"[OK] NKI version: {nki.__version__}")
    except Exception as e:
        print(f"[ERROR] Failed to import NKI: {e}")
        return 1

    # Test NKI language module
    try:
        from nki import language as nl
        print(f"[OK] NKI language module imported successfully")
    except Exception as e:
        print(f"[ERROR] Failed to import NKI language module: {e}")
        return 1

    # Test PyTorch
    try:
        import torch
        print(f"[OK] PyTorch imported successfully")
        print(f"[OK] PyTorch version: {torch.__version__}")
    except Exception as e:
        print(f"[ERROR] Failed to import PyTorch: {e}")
        return 1

    print("[OK] All imports successful - NKI 0.3.0 is operational")
    return 0

if __name__ == "__main__":
    sys.exit(main())
