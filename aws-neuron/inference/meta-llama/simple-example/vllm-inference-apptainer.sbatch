#!/bin/bash
#SBATCH --job-name=vllm-neuron
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --output=logs/vllm-%j.out
#SBATCH --error=logs/vllm-%j.err

MODEL_ID="meta-llama/Llama-3.2-1B-Instruct"
TP_DEGREE=2

apptainer run \
  --bind /dev/neuron0:/dev/neuron0 \
  --bind /opt/aws/neuron:/opt/aws/neuron:ro \
  --bind $PWD:$PWD \
  --pwd $PWD \
  --env NEURON_CC_FLAGS="--model-type=transformer" \
  --env NEURON_COMPILE_CACHE_URL="$PWD/neuron_cache" \
  docker://public.ecr.aws/neuron/pytorch-inference-vllm-neuronx:0.16.0-neuronx-py312-sdk2.29.0-ubuntu24.04 \
  vllm serve $MODEL_ID \
    --tensor-parallel-size $TP_DEGREE \
    --max-num-seqs 8 \
    --max-model-len 512 \
    --block-size 512 \
    --device neuron \
    --port 8000 \
    --host 0.0.0.0

