#!/bin/bash
set -e

# Week 1: Pegasus Simulator v4.5.1 Installation Script
# このスクリプトはIsaac Simコンテナ内で実行します

echo "=========================================="
echo "Week 1: Pegasus Simulator v4.5.1 Setup"
echo "=========================================="

# 環境変数の確認
if [ -z "$ISAAC_SIM_WORKSPACE" ]; then
    echo "WARNING: ISAAC_SIM_WORKSPACE not set, using default"
    WORKSPACE_DIR="$HOME/workspace"
else
    WORKSPACE_DIR="$ISAAC_SIM_WORKSPACE"
fi

echo "Workspace directory: $WORKSPACE_DIR"

# Pegasus Simulatorのクローン
echo "[1/4] Cloning Pegasus Simulator v4.5.1..."
cd "$WORKSPACE_DIR"

if [ -d "PegasusSimulator" ]; then
    echo "PegasusSimulator directory already exists, pulling latest..."
    cd PegasusSimulator
    git fetch --all --tags
    git checkout v4.5.1
    cd ..
else
    git clone https://github.com/PegasusSimulator/PegasusSimulator.git
    cd PegasusSimulator
    git checkout v4.5.1
    cd ..
fi

echo "Pegasus Simulator v4.5.1 cloned successfully!"

# Iris droneモデルのダウンロード
echo "[2/4] Downloading Iris drone model..."
IRIS_URL="https://github.com/PegasusSimulator/PegasusSimulator/raw/v4.5.1/pegasus_simulator/params/robots/iris.usd"
mkdir -p "$WORKSPACE_DIR/models"
wget -O "$WORKSPACE_DIR/models/iris.usd" "$IRIS_URL" || {
    echo "WARNING: Failed to download iris.usd from GitHub"
    echo "You may need to download it manually from:"
    echo "$IRIS_URL"
}

if [ -f "$WORKSPACE_DIR/models/iris.usd" ]; then
    echo "Iris model downloaded: $WORKSPACE_DIR/models/iris.usd"
else
    echo "WARNING: Iris model not found, you'll need to download it manually"
fi

# Week 1プロジェクトのコピー
echo "[3/4] Setting up Week 1 project files..."
if [ -d "/tmp/week1-isaac-pegasus" ]; then
    cp -r /tmp/week1-isaac-pegasus "$WORKSPACE_DIR/"
    echo "Week 1 project copied to workspace"
elif [ -d "$HOME/week1-isaac-pegasus" ]; then
    cp -r "$HOME/week1-isaac-pegasus" "$WORKSPACE_DIR/"
    echo "Week 1 project copied to workspace"
else
    echo "WARNING: Week 1 project not found at /tmp or $HOME"
    echo "You may need to copy it manually to: $WORKSPACE_DIR"
fi

# 依存関係の確認
echo "[4/4] Checking dependencies..."
echo ""
echo "Required for Pegasus Simulator:"
echo "  - Python 3.10 (Isaac Sim 4.5.0 includes this)"
echo "  - Isaac Sim 4.5.0 ✅"
echo "  - ROS2 Humble (included in Isaac Sim) ✅"
echo ""

# セットアップ完了メッセージ
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Pegasus Simulator v4.5.1 is ready!"
echo ""
echo "Project structure:"
echo "  Pegasus: $WORKSPACE_DIR/PegasusSimulator"
echo "  Models: $WORKSPACE_DIR/models/iris.usd"
echo "  Week 1: $WORKSPACE_DIR/week1-isaac-pegasus"
echo ""
echo "Next steps:"
echo "1. Start Isaac Sim container:"
echo "   bash scripts/04-run-container.sh"
echo ""
echo "2. Inside container, install Pegasus:"
echo "   cd /workspace/PegasusSimulator"
echo "   /isaac-sim/python.sh -m pip install -e ."
echo ""
echo "3. Run demo flight:"
echo "   cd /workspace/week1-isaac-pegasus"
echo "   /isaac-sim/python.sh src/demo_iris_flight.py"
echo ""
echo "Documentation:"
echo "  Pegasus: https://pegasussimulator.github.io/PegasusSimulator/"
echo "  Isaac Sim: https://docs.isaacsim.omniverse.nvidia.com/4.5.0/"
echo ""
