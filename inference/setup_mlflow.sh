#!/bin/bash
# MLflow setup and launch script

set -e

echo "=================================="
echo "MLflow Setup for vLLM Benchmark"
echo "=================================="

# Check if mlflow is installed
if ! command -v mlflow &> /dev/null; then
    echo "MLflow not found. Installing..."
    pip install mlflow>=2.10.0
else
    echo "MLflow is already installed: $(mlflow --version)"
fi

# Create mlruns directory if it doesn't exist
MLFLOW_DIR="${MLFLOW_DIR:-./mlruns}"
mkdir -p "$MLFLOW_DIR"

echo ""
echo "MLflow tracking directory: $MLFLOW_DIR"
echo ""

# Default settings
HOST="${MLFLOW_HOST:-0.0.0.0}"
PORT="${MLFLOW_PORT:-5000}"
BACKEND_STORE="${MLFLOW_BACKEND_STORE:-$MLFLOW_DIR}"

echo "Starting MLflow server..."
echo "  Host: $HOST"
echo "  Port: $PORT"
echo "  Backend Store: $BACKEND_STORE"
echo ""

# Launch MLflow server
mlflow server \
    --host "$HOST" \
    --port "$PORT" \
    --backend-store-uri "$BACKEND_STORE" \
    --default-artifact-root "$BACKEND_STORE"

# Note: To run in background, use:
# nohup mlflow server --host $HOST --port $PORT --backend-store-uri $BACKEND_STORE > mlflow.log 2>&1 &
