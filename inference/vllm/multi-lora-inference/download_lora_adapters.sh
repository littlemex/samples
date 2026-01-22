#!/bin/bash

# LoRAアダプターをダウンロードするスクリプト

set -e

echo "Downloading LoRA adapters for vLLM Multi-LoRA inference..."

# ディレクトリを作成
mkdir -p lora_adapters

# SQL特化LoRAアダプター
echo "Downloading SQL LoRA adapter..."
python3 -c "
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id='yard1/llama-2-7b-sql-lora-test',
    local_dir='./lora_adapters/sql-lora',
    local_dir_use_symlinks=False
)
print('SQL LoRA adapter downloaded successfully')
"

# Python特化LoRAアダプター（例）
# 実際のリポジトリは適宜変更してください
echo "Note: Python and Math LoRA adapters need to be downloaded separately"
echo "You can find suitable LoRA adapters on HuggingFace Hub"
echo "Example: https://huggingface.co/models?search=llama-2-7b+lora"

echo ""
echo "Available LoRA adapters:"
ls -la lora_adapters/

echo ""
echo "LoRA adapter download completed!"
echo "To use custom adapters, place them in ./lora_adapters/ directory"
