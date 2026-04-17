#!/bin/bash
set -e

echo "======================================================================"
echo "NxD Inference + vLLM Setup for ParallelCluster"
echo "======================================================================"

# 1. 必要なツールのインストール確認
echo "[1/5] Checking prerequisites..."
if ! command -v docker &> /dev/null; then
    echo "ERROR: docker not found. Please install Docker."
    exit 1
fi

if ! command -v enroot &> /dev/null; then
    echo "ERROR: enroot not found. Installing..."
    # Enroot インストール（Ubuntu 22.04/24.04）
    arch=$(dpkg --print-architecture)
    curl -fSsL -O https://github.com/NVIDIA/enroot/releases/download/v3.4.1/enroot_3.4.1-1_${arch}.deb
    sudo apt install -y ./enroot_3.4.1-1_${arch}.deb
    rm enroot_3.4.1-1_${arch}.deb
fi

# 2. 検証スクリプトに実行権限付与
echo "[2/5] Setting up scripts..."
chmod +x create-enroot-image.sh
chmod +x verify_installation.py

# 3. Enroot イメージ作成
echo "[3/5] Creating Enroot image (this may take 10-15 minutes)..."
./create-enroot-image.sh

# 4. ログディレクトリ作成
echo "[4/5] Creating logs directory..."
mkdir -p logs

# 5. 検証
echo "[5/5] Verifying installation..."
srun --nodes=1 \
    --container-image=${PWD}/neuron-inference.sqsh \
    python3 /workspace/verify_installation.py

echo ""
echo "======================================================================"
echo "Setup complete!"
echo "======================================================================"
echo ""
echo "To start vLLM inference server:"
echo "  export HF_TOKEN=your_token_here"
echo "  sbatch vllm-inference.sbatch"
echo ""
echo "To test with custom model:"
echo "  export MODEL_ID=meta-llama/Llama-3.2-3B-Instruct"
echo "  export TENSOR_PARALLEL_SIZE=2"
echo "  sbatch vllm-inference.sbatch"
