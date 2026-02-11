#!/bin/bash
set -e

# Week 1: Isaac Sim Container Run Script
# このスクリプトでIsaac Sim 4.5.0コンテナを起動します

echo "=========================================="
echo "Week 1: Starting Isaac Sim Container"
echo "=========================================="

# 環境変数の読み込み
if [ -f "$HOME/.isaac_sim_env" ]; then
    source "$HOME/.isaac_sim_env"
    echo "Environment variables loaded from ~/.isaac_sim_env"
else
    echo "WARNING: ~/.isaac_sim_env not found"
    echo "Setting default values..."
    ISAAC_SIM_CACHE_DIR="$HOME/docker/isaac-sim"
    ISAAC_SIM_WORKSPACE="$HOME/workspace"
fi

# ディレクトリの存在確認
if [ ! -d "$ISAAC_SIM_CACHE_DIR" ]; then
    echo "ERROR: Cache directory not found: $ISAAC_SIM_CACHE_DIR"
    echo "Please run scripts/02-docker-isaac-setup.sh first"
    exit 1
fi

if [ ! -d "$ISAAC_SIM_WORKSPACE" ]; then
    echo "WARNING: Workspace directory not found: $ISAAC_SIM_WORKSPACE"
    echo "Creating workspace directory..."
    mkdir -p "$ISAAC_SIM_WORKSPACE"
fi

# コンテナ名
CONTAINER_NAME="isaac-sim-week1"

# 既存コンテナの確認と停止
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Existing container found: $CONTAINER_NAME"
    echo "Stopping and removing..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    docker rm "$CONTAINER_NAME" 2>/dev/null || true
fi

# 起動モードの選択
echo ""
echo "Select container mode:"
echo "1) Interactive mode (bash shell)"
echo "2) Headless mode with livestream"
echo "3) Background mode (detached)"
echo ""
read -p "Enter choice [1-3]: " mode_choice

case $mode_choice in
    1)
        echo "Starting in interactive mode..."
        MODE="interactive"
        ;;
    2)
        echo "Starting in headless livestream mode..."
        MODE="headless"
        ;;
    3)
        echo "Starting in background mode..."
        MODE="background"
        ;;
    *)
        echo "Invalid choice, using interactive mode"
        MODE="interactive"
        ;;
esac

# 共通のdockerオプション
DOCKER_OPTS="--name $CONTAINER_NAME \
    --gpus all \
    -e ACCEPT_EULA=Y \
    -e PRIVACY_CONSENT=Y \
    --network=host \
    -v $ISAAC_SIM_CACHE_DIR/cache/main:/isaac-sim/.cache:rw \
    -v $ISAAC_SIM_CACHE_DIR/cache/computecache:/isaac-sim/.nv/ComputeCache:rw \
    -v $ISAAC_SIM_CACHE_DIR/logs:/isaac-sim/.nvidia-omniverse/logs:rw \
    -v $ISAAC_SIM_CACHE_DIR/config:/isaac-sim/.nvidia-omniverse/config:rw \
    -v $ISAAC_SIM_CACHE_DIR/data:/isaac-sim/.local/share/ov/data:rw \
    -v $ISAAC_SIM_CACHE_DIR/pkg:/isaac-sim/.local/share/ov/pkg:rw \
    -v $ISAAC_SIM_WORKSPACE:/workspace:rw \
    -u 1234:1234"

# ROS2環境変数の設定
DOCKER_OPTS="$DOCKER_OPTS \
    -e ROS_DISTRO=humble \
    -e RMW_IMPLEMENTATION=rmw_fastrtps_cpp \
    -e ROS_DOMAIN_ID=0"

echo ""
echo "=========================================="
echo "Container Configuration"
echo "=========================================="
echo "Name: $CONTAINER_NAME"
echo "Cache: $ISAAC_SIM_CACHE_DIR"
echo "Workspace: $ISAAC_SIM_WORKSPACE"
echo "Mode: $MODE"
echo ""

# モードに応じてコンテナを起動
case $MODE in
    interactive)
        echo "Starting interactive bash session..."
        echo "Use 'exit' to stop the container"
        echo ""
        docker run --entrypoint bash -it --rm $DOCKER_OPTS nvcr.io/nvidia/isaac-sim:4.5.0
        ;;
    
    headless)
        echo "Starting headless mode with livestream..."
        echo ""
        docker run -d $DOCKER_OPTS nvcr.io/nvidia/isaac-sim:4.5.0 ./runheadless.native.sh --livestream 1
        
        echo ""
        echo "✅ Container started in background!"
        echo ""
        echo "Access livestream at:"
        echo "  http://$(hostname -I | awk '{print $1}'):8211/streaming/webrtc-client"
        echo ""
        echo "To view logs:"
        echo "  docker logs -f $CONTAINER_NAME"
        echo ""
        echo "To enter container:"
        echo "  docker exec -it $CONTAINER_NAME bash"
        echo ""
        echo "To stop container:"
        echo "  docker stop $CONTAINER_NAME"
        echo ""
        ;;
    
    background)
        echo "Starting in background (detached)..."
        docker run --entrypoint bash -dit $DOCKER_OPTS nvcr.io/nvidia/isaac-sim:4.5.0
        
        echo ""
        echo "✅ Container started in background!"
        echo ""
        echo "To enter container:"
        echo "  docker exec -it $CONTAINER_NAME bash"
        echo ""
        echo "To stop container:"
        echo "  docker stop $CONTAINER_NAME"
        echo ""
        ;;
esac

echo "=========================================="
echo "Quick Start Commands (inside container)"
echo "=========================================="
echo ""
echo "1. Install Pegasus Simulator:"
echo "   cd /workspace/PegasusSimulator"
echo "   /isaac-sim/python.sh -m pip install -e ."
echo ""
echo "2. Run compatibility check:"
echo "   ./isaac-sim.compatibility_check.sh --/app/quitAfter=10 --no-window"
echo ""
echo "3. Run demo flight:"
echo "   cd /workspace/week1-isaac-pegasus"
echo "   /isaac-sim/python.sh src/demo_iris_flight.py"
echo ""
echo "4. Setup ROS2 environment:"
echo "   export ROS_DISTRO=humble"
echo "   export RMW_IMPLEMENTATION=rmw_fastrtps_cpp"
echo ""
