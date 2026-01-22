# vLLM Multi-LoRA Inference Sample

このディレクトリには、vLLMのMulti-LoRA推論機能のサンプル実装が含まれています。

## 概要

vLLMのMulti-LoRA機能を使用すると、単一のベースモデルに対して複数のLoRAアダプターを動的に切り替えながら推論を実行できます。

## 必要な環境

- Python 3.8+
- CUDA対応GPU（推奨: V100, A100, H100など）
- GPU メモリ: 最低16GB（モデルとLoRAサイズに依存）

## インストール

```bash
pip install -r requirements.txt
```

## サンプルファイル

### 1. basic_multi_lora.py
最もシンプルなMulti-LoRA推論の例です。

```bash
python basic_multi_lora.py
```

### 2. advanced_multi_lora.py
より高度な設定とエラーハンドリングを含む例です。

```bash
python advanced_multi_lora.py
```

### 3. offline_batch_inference.py
大量のリクエストをバッチ処理する例です。

```bash
python offline_batch_inference.py --input prompts.json --output results.json
```

### 4. online_serving.py
オンラインサービング用のAPIサーバー例です。

```bash
python online_serving.py --port 8000
```

## LoRAアダプターの準備

サンプルでは、HuggingFace Hubから公開されているLoRAアダプターを使用します：

```bash
# LoRAアダプターのダウンロード
bash download_lora_adapters.sh
```

または、Pythonで直接ダウンロード：

```python
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="yard1/llama-2-7b-sql-lora-test",
    local_dir="./lora_adapters/sql-lora"
)
```

## 設定パラメータの説明

### enable_lora
- 型: `bool`
- デフォルト: `False`
- LoRA機能を有効化します。

### max_loras
- 型: `int`
- デフォルト: `1`
- バッチ内で同時に使用できるLoRAアダプター数。
- 値を大きくするとメモリ使用量が増加します。

### max_lora_rank
- 型: `int`
- デフォルト: `8`
- サポートする最大rank値。
- すべてのLoRAアダプターのrankがこの値以下である必要があります。

### max_cpu_loras
- 型: `int`
- デフォルト: `None`
- CPU側でキャッシュするLoRAアダプター数。
- 頻繁に切り替わるアダプターがある場合に有効です。

## パフォーマンスチューニング

### メモリ使用量の最適化

```python
# メモリ使用量を抑える設定
llm = LLM(
    model="meta-llama/Llama-2-7b-hf",
    enable_lora=True,
    max_loras=2,           # 同時LoRA数を制限
    max_lora_rank=16,      # rank上限を低めに設定
    gpu_memory_utilization=0.85  # GPUメモリ使用率
)
```

### スループットの最適化

```python
# スループット重視の設定
llm = LLM(
    model="meta-llama/Llama-2-7b-hf",
    enable_lora=True,
    max_loras=8,           # より多くのLoRAを同時処理
    max_cpu_loras=16,      # CPUキャッシュを増やす
    max_num_seqs=256       # バッチサイズを大きく
)
```

## トラブルシューティング

### Out of Memory (OOM) エラー

```bash
# max_lorasを減らす
# max_lora_rankを実際に必要な値に設定
# gpu_memory_utilizationを下げる（デフォルト0.9 → 0.8など）
```

### LoRAアダプターが見つからない

```bash
# パスを確認
ls -la ./lora_adapters/

# 絶対パスを使用
lora_path = os.path.abspath("./lora_adapters/sql-lora")
```

### 推論速度が遅い

```bash
# max_num_seqsを増やしてバッチサイズを大きくする
# tensor_parallel_sizeでマルチGPUを使用
# より小さいモデルを使用（7B → 3Bなど）
```

## 参考リンク

- [vLLM公式ドキュメント](https://docs.vllm.ai/)
- [Multi-LoRA Inference Example](https://docs.vllm.ai/en/v0.4.1/getting_started/examples/multilora_inference.html)
- [vLLM GitHub](https://github.com/vllm-project/vllm)

## ライセンス

このサンプルコードはMITライセンスの下で提供されています。
