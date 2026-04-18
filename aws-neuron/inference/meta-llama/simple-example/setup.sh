#!/bin/bash
set -e

echo "======================================================================"
echo "NxD Inference + vLLM Setup for ParallelCluster"
echo "======================================================================"

# 1. 必要なツールのインストール確認
echo "[1/6] Checking prerequisites..."
if ! command -v docker &> /dev/null; then
    echo "ERROR: docker not found. Please install Docker."
    exit 1
fi

if ! command -v enroot &> /dev/null; then
    echo "ERROR: enroot not found. Installing..."
    arch=$(dpkg --print-architecture)
    curl -fSsL -O https://github.com/NVIDIA/enroot/releases/download/v3.4.1/enroot_3.4.1-1_${arch}.deb
    sudo apt install -y ./enroot_3.4.1-1_${arch}.deb
    rm enroot_3.4.1-1_${arch}.deb
fi

# 2. 検証スクリプトに実行権限付与
echo "[2/6] Setting up scripts..."
chmod +x create-enroot-image.sh

# 3. Enroot イメージ作成
echo "[3/6] Creating Enroot image (this may take 10-15 minutes)..."
./create-enroot-image.sh

# 4. ログディレクトリ作成
echo "[4/6] Creating logs directory..."
mkdir -p logs

# 5. Pyxis/Enroot 初期化（重要！）
echo "[5/6] Initializing Pyxis/Enroot on ComputeNode..."
srun --nodes=1 --container-image=ubuntu:22.04 echo "[OK] Pyxis initialized"

# 6. 検証
echo "[6/6] Verifying installation..."
srun --nodes=1 \
    --container-image=${PWD}/neuron-inference.sqsh \
    --container-mounts=${PWD}:/workspace \
    python3 -c "import vllm; print('vLLM version:', vllm.__version__)"

echo ""
echo "======================================================================"
echo "Setup complete!"
echo "======================================================================"
echo ""
echo "To start vLLM inference server:"
echo "  export HF_TOKEN=your_token_here"
echo "  sbatch vllm-inference.sbatch"
