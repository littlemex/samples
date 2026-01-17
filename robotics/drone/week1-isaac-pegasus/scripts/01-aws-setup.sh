#!/bin/bash
set -e

# Week 1: AWS EC2 Initial Setup Script
# このスクリプトはAWS EC2インスタンス上で実行します
# 対象OS: Ubuntu 22.04 LTS

echo "=========================================="
echo "Week 1: AWS EC2 Initial Setup"
echo "=========================================="

# システムアップデート
echo "[1/5] System update..."
sudo apt-get update
sudo apt-get upgrade -y

# 必要なツールのインストール
echo "[2/5] Installing essential tools..."
sudo apt-get install -y \
    curl \
    wget \
    git \
    vim \
    htop \
    build-essential \
    python3-pip \
    python3-dev

# NVIDIA Driverの確認
echo "[3/5] Checking NVIDIA Driver..."
if command -v nvidia-smi &> /dev/null; then
    echo "NVIDIA Driver is already installed:"
    nvidia-smi --query-gpu=name,driver_version --format=csv
else
    echo "ERROR: NVIDIA Driver not found!"
    echo "Please use AWS Deep Learning AMI or install NVIDIA Driver manually"
    exit 1
fi

# Dockerのインストール
echo "[4/5] Installing Docker..."
if ! command -v docker &> /dev/null; then
    # Dockerインストール (公式スクリプト使用)
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    
    # 現在のユーザーをdockerグループに追加
    sudo usermod -aG docker $USER
    
    # Dockerサービス開始
    sudo systemctl enable docker
    sudo systemctl start docker
    
    echo "Docker installed successfully!"
    echo "NOTE: You may need to log out and log back in for docker group changes to take effect"
else
    echo "Docker is already installed:"
    docker --version
fi

# NVIDIA Container Toolkitのインストール
echo "[5/5] Installing NVIDIA Container Toolkit..."
if ! dpkg -l | grep -q nvidia-container-toolkit; then
    # GPGキーとリポジトリの追加
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
        sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    
    # インストール
    sudo apt-get update
    sudo apt-get install -y nvidia-container-toolkit
    
    # Dockerランタイム設定
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    
    echo "NVIDIA Container Toolkit installed successfully!"
else
    echo "NVIDIA Container Toolkit is already installed"
fi

# 動作確認
echo ""
echo "=========================================="
echo "Verification Tests"
echo "=========================================="

echo "[Test 1] Docker version:"
docker --version

echo ""
echo "[Test 2] NVIDIA Container Runtime test:"
docker run --rm --gpus all ubuntu:22.04 nvidia-smi || {
    echo "ERROR: NVIDIA Container Runtime test failed!"
    echo "Please check NVIDIA Driver and Container Toolkit installation"
    exit 1
}

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. If this is your first time running this script, log out and log back in"
echo "2. Run: bash scripts/02-docker-isaac-setup.sh"
echo ""
echo "IMPORTANT: Make sure you have your NGC API key ready!"
echo "Get it from: https://ngc.nvidia.com/setup/api-key"
echo ""
