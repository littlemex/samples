#!/bin/bash
#
# Quick test script for VLM OCR benchmark
#
# Usage:
#   ./test_quick.sh [--image IMAGE_ID] [--prompt PROMPT_ID]
#

set -e

# Default values
IMAGE="sign_no_littering"
PROMPT="simple_english"

# Parse arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --image)
      IMAGE="$2"
      shift 2
      ;;
    --prompt)
      PROMPT="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "Usage: $0 [--image IMAGE_ID] [--prompt PROMPT_ID]"
      exit 1
      ;;
  esac
done

# Check AWS_PROFILE
if [ -z "$AWS_PROFILE" ]; then
  echo "[WARNING] AWS_PROFILE not set. Using default credentials."
else
  echo "[INFO] Using AWS_PROFILE: $AWS_PROFILE"
fi

# Run test benchmark
python3 run_test_benchmark.py --image "$IMAGE" --prompt "$PROMPT"
