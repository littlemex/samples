#!/bin/bash

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

#SBATCH --job-name=vllm-neuron-inference
#SBATCH --exclusive
#SBATCH --wait-all-nodes=1
#SBATCH --nodes=1
#SBATCH --output=logs/%x_%j.out

set -ex

# ログディレクトリ作成
mkdir -p logs

# NeuronCore 設定
export NEURON_RT_LOG_LEVEL=INFO
export NEURON_RT_VISIBLE_CORES=0-3  # trn2.3xlarge は 4 コア

# コンテナイメージとマウント設定
declare -a ARGS=(
    --container-image=${PWD}/neuron-inference.sqsh
    --container-mounts=${PWD}:/workspace
    --container-workdir=/workspace
)

# モデル設定
MODEL_ID=${MODEL_ID:-"meta-llama/Llama-3.2-1B-Instruct"}
TENSOR_PARALLEL_SIZE=${TENSOR_PARALLEL_SIZE:-2}
MAX_MODEL_LEN=${MAX_MODEL_LEN:-2048}
MAX_NUM_SEQS=${MAX_NUM_SEQS:-8}

# HuggingFace トークン（環境変数から取得）
if [ -z "$HF_TOKEN" ]; then
    echo "Warning: HF_TOKEN not set. Gated models will fail."
fi

# vLLM 起動コマンド（NxD Inference バックエンド）
declare -a VLLM_ARGS=(
    --model="$MODEL_ID"
    --tensor-parallel-size="$TENSOR_PARALLEL_SIZE"
    --max-model-len="$MAX_MODEL_LEN"
    --max-num-seqs="$MAX_NUM_SEQS"
    --device=neuron
    --dtype=bfloat16
    --port=8000
)

# HF_TOKEN が設定されている場合のみ追加
if [ -n "$HF_TOKEN" ]; then
    VLLM_ARGS+=(--hf-token="$HF_TOKEN")
fi

echo "Starting vLLM Neuron Inference Server..."
echo "Model: $MODEL_ID"
echo "Tensor Parallel Size: $TENSOR_PARALLEL_SIZE"
echo "Max Model Length: $MAX_MODEL_LEN"

# srun でコンテナ起動
srun -l "${ARGS[@]}" python3 -m vllm.entrypoints.openai.api_server \
    "${VLLM_ARGS[@]}"
