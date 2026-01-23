# 利用可能なLoRAアダプター

vLLM Multi-LoRA推論で使用できる、公開されているLoRAアダプターのリストです。

## TinyLlama (1.1B) - 最軽量

### 関数呼び出し
- **モデル**: `unclecode/tinyllama-function-call-lora-adapter-250424`
- **用途**: 関数呼び出し、ツール利用
- **ベースモデル**: TinyLlama/TinyLlama-1.1B-Chat-v1.0
- **ライセンス**: Apache 2.0
- **使用例**: API呼び出し、ツールの動的実行

### SQL生成
- **モデル**: `sid321axn/tiny-llama-text2sql`
- **用途**: 自然言語からSQLクエリ生成
- **ベースモデル**: TinyLlama/TinyLlama-1.1B-Chat-v0.3
- **使用例**: データベースクエリの自動生成

### 数学問題解答
- **モデル**: `philimon/TinyLlama-gsm8k-lora`
- **用途**: GSM8K数学問題の解答
- **ベースモデル**: TinyLlama/TinyLlama-1.1B-Chat-v0.3
- **使用例**: 算数・数学の文章問題

### その他
- `lightblue/tinyllama_chat_jsquad` - テキスト生成
- `rocailler/tinyllama-1b-20K-ProdToCat-2023-11-26_00-10` - カテゴリ分類
- `tushkulange/tinyllama-text-to-sql-lora` - Text-to-SQL（別実装）
- `EddyGiusepe/tinyllama-ItauPortuguese-lora-v0.1` - ポルトガル語チャット

**合計**: 36個以上のアダプター利用可能

## Microsoft Phi-2 (2.7B) - バランス型

### カスタムQLoRA
- **モデル**: `piyushgrover/phi-2-qlora-adapter-custom`
- **用途**: カスタムタスク用QLoRAアダプター

### 医療テキスト
- **モデル**: `NouRed/Med-Phi-2-QLoRa`
- **用途**: 医療テキスト生成・理解

### 多言語対応
- **モデル**: `s3nh/phi-2_dolly_instruction_polish_adapter`
- **用途**: ポーランド語命令チューニング

### 命令チューニング
- **モデル**: `Yhyu13/phi-2-sft-alpaca_gpt4_en-ep1-lora`
- **用途**: Alpaca/GPT4スタイルの命令実行

**合計**: 948個以上のアダプター利用可能

## Qwen2.5-7B (7B) - 高性能

### 中国語テキスト修正
- **モデル**: `shibing624/chinese-text-correction-7b-lora`
- **用途**: 中国語の文法・スペル修正
- **人気度**: ⭐⭐

### 数学問題解答
- **モデル**: `ybian-umd/Qwen2.5-7B-Instruct-gsm8k-*`
- **用途**: GSM8K数学問題（複数バージョン）
- **人気度**: ⭐⭐⭐

### ORPO最適化
- **モデル**: `FINGU-AI/Qwen2.5-orpo-lora`
- **用途**: ORPO（Odds Ratio Preference Optimization）
- **人気度**: ⭐⭐⭐

### テキスト生成
- **モデル**: `vlkn/FT-Qwen2.5-7B-GlossLM`
- **用途**: 汎用テキスト生成

**合計**: 859個以上のアダプター利用可能

## 使用方法

### 基本的な使い方

```python
from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest

# ベースモデルの初期化
llm = LLM(
    model="TinyLlama/TinyLlama-1.1B-Chat-v1.0",
    enable_lora=True,
    max_loras=3,
    max_lora_rank=64,
)

# LoRAリクエストの作成
# lora_pathにHuggingFaceリポジトリIDを指定すると自動ダウンロードされます
lora_request = LoRARequest(
    lora_name="function_call",
    lora_int_id=1,
    lora_path="unclecode/tinyllama-function-call-lora-adapter-250424",
)

# 推論実行
outputs = llm.generate(
    prompts=["Your prompt here"],
    sampling_params=SamplingParams(temperature=0.7, max_tokens=200),
    lora_request=lora_request,
)
```

### 複数のLoRAアダプターを切り替える

```python
# 複数のLoRAアダプターを定義
# 第1引数: lora_name, 第2引数: lora_int_id, 第3引数: lora_path
adapters = {
    "sql": LoRARequest(lora_name="sql", lora_int_id=1, lora_path="sid321axn/tiny-llama-text2sql"),
    "math": LoRARequest(lora_name="math", lora_int_id=2, lora_path="philimon/TinyLlama-gsm8k-lora"),
    "function": LoRARequest(lora_name="function", lora_int_id=3, lora_path="unclecode/tinyllama-function-call-lora-adapter-250424"),
}

# タスクに応じて切り替え
outputs1 = llm.generate(["Generate SQL..."], lora_request=adapters["sql"])
outputs2 = llm.generate(["Solve: 2+2=?"], lora_request=adapters["math"])
outputs3 = llm.generate(["Create function..."], lora_request=adapters["function"])
```

## モデル選択のガイドライン

| モデル | メモリ | 速度 | 品質 | 推奨用途 |
|--------|--------|------|------|----------|
| TinyLlama (1.1B) | 🟢 最小 | 🟢 最速 | 🟡 中 | プロトタイプ、リアルタイム処理 |
| Phi-2 (2.7B) | 🟡 小 | 🟢 高速 | 🟢 高 | バランス型、本番環境 |
| Qwen2.5-7B (7B) | 🟠 中 | 🟡 中速 | 🟢 最高 | 高品質が必要な場合 |

## 注意事項

1. **互換性**: LoRAアダプターは特定のベースモデルに対してファインチューニングされています。異なるモデルでは動作しません。
2. **ライセンス**: 各LoRAアダプターのライセンスを確認してください。
3. **メモリ**: 複数のLoRAアダプターを同時に使用する場合、`max_loras`と`max_cpu_loras`を調整してください。
4. **rank**: 使用するLoRAアダプターのrankを確認し、`max_lora_rank`を適切に設定してください。

## さらに探す

- [Hugging Face - TinyLlama アダプター](https://huggingface.co/models?other=base_model:adapter:TinyLlama/TinyLlama-1.1B-Chat-v0.3)
- [Hugging Face - Phi-2 アダプター](https://huggingface.co/models?other=base_model:adapter:microsoft/phi-2)
- [Hugging Face - Qwen2.5-7B アダプター](https://huggingface.co/models?other=base_model:adapter:Qwen/Qwen2.5-7B-Instruct)
