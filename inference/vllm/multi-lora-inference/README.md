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

### 2. multi_lora_with_adapters.py（推奨）
実際のLoRAアダプターを使用したデモです。チャットテンプレートを適用し、複数のLoRAアダプターを切り替えながら推論を実行します。

```bash
python multi_lora_with_adapters.py
```

### 3. batch_test_lora.py
txtファイルから複数のプロンプトを読み込んでバッチテストを実行します。

```bash
# ベースモデルのみでテスト
python batch_test_lora.py --prompt-file test_prompts/base_model.txt

# SQL生成LoRAでテスト
python batch_test_lora.py --prompt-file test_prompts/sql_generation.txt --lora text2sql

# 数学問題LoRAでテスト
python batch_test_lora.py --prompt-file test_prompts/math_problems.txt --lora math

# 結果をファイルに保存
python batch_test_lora.py --prompt-file test_prompts/sql_generation.txt --lora text2sql --output results.txt
```

### 4. advanced_multi_lora.py
より高度な設定とエラーハンドリングを含む例です。

```bash
python advanced_multi_lora.py
```

### 5. offline_batch_inference.py
大量のリクエストをバッチ処理する例です。

```bash
python offline_batch_inference.py --input prompts.json --output results.json
```

### 6. online_serving.py
オンラインサービング用のAPIサーバー例です。

```bash
python online_serving.py --port 8000
```

## 利用可能なLoRAアダプター

### TinyLlama (1.1B) - 最軽量・高速

**ベースモデル**: `TinyLlama/TinyLlama-1.1B-Chat-v1.0`

| 用途 | HuggingFace リポジトリ | batch_test_lora.pyでの指定 |
|------|------------------------|---------------------------|
| SQL生成 | `sid321axn/tiny-llama-text2sql` | `--lora text2sql` |
| 数学問題 | `philimon/TinyLlama-gsm8k-lora` | `--lora math` |
| 関数呼び出し | `unclecode/tinyllama-function-call-lora-adapter-250424` | `--lora function` |

**特徴**:
- メモリ消費最小（~2GB）
- 最速の推論速度
- プロトタイプや開発に最適

### Microsoft Phi-2 (2.7B) - バランス型

**ベースモデル**: `microsoft/phi-2`

- 948個以上のLoRAアダプター利用可能
- HuggingFaceで検索: [Phi-2 adapters](https://huggingface.co/models?other=base_model:adapter:microsoft/phi-2)

### Qwen2.5-7B (7B) - 高性能

**ベースモデル**: `Qwen/Qwen2.5-7B-Instruct`

- 859個以上のLoRAアダプター利用可能
- 中国語処理に強い
- HuggingFaceで検索: [Qwen2.5-7B adapters](https://huggingface.co/models?other=base_model:adapter:Qwen/Qwen2.5-7B-Instruct)

## LoRAアダプターの準備

vLLMは自動的にHuggingFaceからLoRAアダプターをダウンロードします。`lora_path`にリポジトリIDを指定するだけです：

```python
from vllm import LLM
from vllm.lora.request import LoRARequest

llm = LLM(
    model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    enable_lora=True,
)

# 自動ダウンロードされる
lora_request = LoRARequest(
    lora_name="sql",
    lora_int_id=1,
    lora_path="sid321axn/tiny-llama-text2sql",  # HuggingFace リポジトリID
)
```

事前ダウンロードする場合：

```bash
python download_lora_adapters_hf.py
```

## チャットテンプレートの重要性

TinyLlamaなどのチャットモデルは、特定のフォーマットを期待します。正しいテンプレートを使用しないと、出力が不自然になります。

### TinyLlamaのチャットテンプレート

```
<|system|>
システムメッセージ</s>
<|user|>
ユーザーメッセージ</s>
<|assistant|>
```

### Pythonでの使用例

```python
def format_chat_prompt(user_message: str, system_message: str = None) -> str:
    if system_message:
        return f"<|system|>\n{system_message}</s>\n<|user|>\n{user_message}</s>\n<|assistant|>\n"
    else:
        return f"<|user|>\n{user_message}</s>\n<|assistant|>\n"

# 使用
prompt = format_chat_prompt(
    "What is the capital of France?",
    "You are a helpful assistant."
)
```

`batch_test_lora.py`と`multi_lora_with_adapters.py`は自動的にチャットテンプレートを適用します。

## テストプロンプトファイル

`test_prompts/`ディレクトリに3つのサンプルファイルがあります：

- `base_model.txt` - 一般的な質問（ベースモデル用）
- `sql_generation.txt` - SQLクエリ生成タスク
- `math_problems.txt` - 数学問題

カスタムプロンプトファイルの作成：

```bash
# 1行1プロンプト、#で始まる行はコメント
cat > test_prompts/my_test.txt << 'EOF'
# 私のテストプロンプト
プロンプト1
プロンプト2
EOF
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

### 出力が"And And And..."のように繰り返される

**原因**: チャットテンプレートが適用されていない、またはLoRAアダプターが適切に機能していない

**解決策**:
1. `multi_lora_with_adapters.py`または`batch_test_lora.py`を使用（自動的にテンプレート適用）
2. temperatureを0.7～0.9に調整
3. 別のLoRAアダプターを試す

### 出力が1トークンのみ、または空

**原因**: チャットテンプレートの問題、またはEOSトークンの早期生成

**解決策**:
1. 正しいチャットテンプレートを使用（上記参照）
2. `max_tokens`を増やす（150以上）
3. temperatureを上げる（0.7～1.0）

### Out of Memory (OOM) エラー

**解決策**:
```python
llm = LLM(
    model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    enable_lora=True,
    max_loras=2,                    # 同時LoRA数を減らす
    max_lora_rank=32,               # rank上限を下げる
    gpu_memory_utilization=0.7,    # メモリ使用率を下げる
)
```

### LoRAアダプターが見つからない

**原因**: HuggingFaceからのダウンロード失敗、またはパスが間違っている

**解決策**:
```bash
# HuggingFaceトークンを設定
export HF_TOKEN="your_token_here"

# パスを確認（自動ダウンロードの場合）
ls ~/.cache/huggingface/hub/

# 手動ダウンロード
python download_lora_adapters_hf.py
```

### 推論速度が遅い

**解決策**:
```python
llm = LLM(
    model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    enable_lora=True,
    max_num_seqs=256,              # バッチサイズを増やす
    max_loras=8,                   # より多くのLoRAを同時処理
    tensor_parallel_size=2,        # マルチGPUを使用
)
```

### TinyLlamaの出力品質が低い

TinyLlama (1.1B) は非常に小さいモデルです。より高品質な出力が必要な場合：

1. **Phi-2 (2.7B)** に変更 - バランス型
2. **Qwen2.5-7B (7B)** に変更 - 高性能

## 参考リンク

- [vLLM公式ドキュメント](https://docs.vllm.ai/)
- [Multi-LoRA Inference Example](https://docs.vllm.ai/en/v0.4.1/getting_started/examples/multilora_inference.html)
- [vLLM GitHub](https://github.com/vllm-project/vllm)

## ライセンス

このサンプルコードはMITライセンスの下で提供されています。
