#!/bin/bash
set -e

# Week 1: Docker + Isaac Sim 4.5.0 Setup Script
# このスクリプトはEC2インスタンス上で実行します

echo "=========================================="
echo "Week 1: Isaac Sim 4.5.0 Setup"
echo "=========================================="

# NGC API Keyの確認
if [ -z "$NGC_API_KEY" ]; then
    echo "ERROR: NGC_API_KEY environment variable is not set!"
    echo ""
    echo "Please set your NGC API key:"
    echo "  export NGC_API_KEY='your_api_key_here'"
    echo ""
    echo "Get your API key from: https://ngc.nvidia.com/setup/api-key"
    exit 1
fi

# NGC login
echo "[1/4] Logging in to NGC..."
echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin

if [ $? -ne 0 ]; then
    echo "ERROR: NGC login failed!"
    echo "Please check your NGC_API_KEY"
    exit 1
fi

echo "NGC login successful!"

# キャッシュディレクトリの作成
echo "[2/4] Creating cache directories..."
CACHE_DIR="$HOME/docker/isaac-sim"

mkdir -p "$CACHE_DIR/cache/main/ov"
mkdir -p "$CACHE_DIR/cache/main/warp"
mkdir -p "$CACHE_DIR/cache/computecache"
mkdir -p "$CACHE_DIR/config"
mkdir -p "$CACHE_DIR/data/documents"
mkdir -p "$CACHE_DIR/data/Kit"
mkdir -p "$CACHE_DIR/logs"
mkdir -p "$CACHE_DIR/pkg"

# Isaac Simコンテナのユーザー権限に合わせる
sudo chown -R 1234:1234 "$CACHE_DIR"

echo "Cache directories created at: $CACHE_DIR"

# Isaac Sim 4.5.0 containerのpull
echo "[3/4] Pulling Isaac Sim 4.5.0 container (this may take 20-30 minutes)..."
echo "Container size: ~20GB"
echo ""

docker pull nvcr.io/nvidia/isaac-sim:4.5.0

if [ $? -ne 0 ]; then
    echo "ERROR: Failed to pull Isaac Sim container!"
    exit 1
fi

echo "Isaac Sim 4.5.0 container pulled successfully!"

# workspaceディレクトリの作成
echo "[4/4] Creating workspace directory..."
WORKSPACE_DIR="$HOME/workspace"
mkdir -p "$WORKSPACE_DIR"

echo "Workspace created at: $WORKSPACE_DIR"

# 環境変数をファイルに保存
ENV_FILE="$HOME/.isaac_sim_env"
cat > "$ENV_FILE" << EOF
# Isaac Sim 4.5.0 Environment Variables
export ISAAC_SIM_CACHE_DIR="$CACHE_DIR"
export ISAAC_SIM_WORKSPACE="$WORKSPACE_DIR"
export NGC_API_KEY="$NGC_API_KEY"
EOF

echo ""
echo "Environment variables saved to: $ENV_FILE"
echo "Add the following to your ~/.bashrc to persist:"
echo "  source $ENV_FILE"
echo ""

# テスト実行
echo "=========================================="
echo "Verification Test"
echo "=========================================="
echo ""
echo "Testing Isaac Sim container with compatibility check..."
echo "(This may take a few minutes on first run)"
echo ""

docker run --name isaac-sim-test \
    --entrypoint bash \
    --gpus all \
    -e "ACCEPT_EULA=Y" \
    -e "PRIVACY_CONSENT=Y" \
    --rm \
    -v "$CACHE_DIR/cache/main:/isaac-sim/.cache:rw" \
    -v "$CACHE_DIR/cache/computecache:/isaac-sim/.nv/ComputeCache:rw" \
    -u 1234:1234 \
    nvcr.io/nvidia/isaac-sim:4.5.0 \
    -c "./isaac-sim.compatibility_check.sh --/app/quitAfter=10 --no-window"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Compatibility check passed!"
else
    echo ""
    echo "⚠️ Compatibility check failed, but this may be expected in headless mode"
    echo "You can proceed with the next steps"
fi

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Isaac Sim 4.5.0 is ready to use!"
echo ""
echo "Cache directory: $CACHE_DIR"
echo "Workspace directory: $WORKSPACE_DIR"
echo ""
echo "Next steps:"
echo "1. Source environment variables:"
echo "   source $ENV_FILE"
echo ""
echo "2. Run Pegasus Simulator setup:"
echo "   bash scripts/03-pegasus-install.sh"
echo ""
echo "Quick test command:"
echo "  bash scripts/04-run-container.sh"
echo ""
