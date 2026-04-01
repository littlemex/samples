# AWS Bedrock VLM OCR ベンチマーク

AWS Bedrock の Vision-Language Model (VLM) を使用して、日本語OCRの性能を評価するベンチマークスクリプトです。

## 概要

6つのVLMモデルを4種類のプロンプト、5つのサンプル画像で評価し、精度（CER/BLEU）、速度、コストを測定します。

**サポートモデル**:
- Writer Palmyra Vision 7B
- NVIDIA Nemotron Nano 12B V2 VL BF16
- Amazon Nova 2 Lite
- Moonshot AI Kimi K2.5
- Qwen3 VL 235B-A22B (MoE)
- Anthropic Claude Opus 4.6

## ディレクトリ構成

```
demo20260401/
├── vlm_ocr.py                    # VLM OCR実行スクリプト
├── run_benchmark.py              # ベンチマーク実行スクリプト
├── run_test_benchmark.py         # テストベンチマーク（小規模）
├── test_quick.sh                 # クイックテスト
├── generate_sample_images.py     # サンプル画像生成
├── requirements.txt              # 依存パッケージ
├── configs/
│   ├── images.json               # 画像設定（5画像）
│   ├── prompts.json              # プロンプト設定（4種類）
│   ├── models.json               # モデル設定（6モデル）
│   ├── images_test.json          # テスト用（2画像）
│   ├── prompts_test.json         # テスト用（1プロンプト）
│   └── models_test.json          # テスト用（2モデル）
├── images/
│   ├── sign_no_littering.jpg     # 日英混在看板
│   ├── receipt.jpg               # レシート
│   ├── menu.jpg                  # メニュー
│   ├── form.jpg                  # 申込書
│   └── event_info.jpg            # イベント情報
├── logs/                         # ベンチマーク結果（自動生成）
└── README.md                     # このファイル
```

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. AWS認証設定

```bash
# 環境変数で設定
export AWS_PROFILE=your-profile
export AWS_DEFAULT_REGION=us-east-1

# または ~/.aws/credentials に設定
```

### 3. Bedrock モデルアクセスの有効化

AWS Console > Bedrock > Model Access から、使用するモデルへのアクセスを有効にしてください。

### 4. サンプル画像の生成（オプション）

```bash
python3 generate_sample_images.py
```

## 使い方

### クイックテスト（1モデル x 1画像）

```bash
bash test_quick.sh
```

### 小規模ベンチマーク（2モデル x 1プロンプト x 2画像 = 4テスト）

```bash
python3 run_test_benchmark.py
```

### フルベンチマーク（6モデル x 4プロンプト x 5画像 = 120テスト）

```bash
python3 run_benchmark.py
```

### カスタム実行

```bash
# 単一モデルで単一画像をテスト
python3 vlm_ocr.py images/receipt.jpg \
  --model qwen3 \
  --prompt "Extract all text from this image." \
  --region us-east-1

# 特定の設定ファイルでベンチマーク
python3 run_benchmark.py \
  --images configs/images_test.json \
  --prompts configs/prompts_test.json \
  --models configs/models_test.json \
  --profile your-profile
```

## ベンチマーク結果の見方

結果は `logs/benchmark_results_{timestamp}.json` に保存されます。

**評価指標**:
- **CER (Character Error Rate)**: 文字誤り率（低いほど良い、0.0 = 完全一致）
- **BLEU**: 簡易BLEU-1スコア（高いほど良い、1.0 = 完全一致）
- **elapsed_time**: 実行時間（秒）
- **cost_jpy**: コスト（日本円）

**結果例**:
```json
{
  "model": "qwen3",
  "model_name": "Qwen3 VL 235B-A22B (MoE)",
  "prompt": "detailed_english",
  "image": "receipt",
  "success": true,
  "cer": 0.0235,
  "bleu": 0.9412,
  "elapsed_time": 3.45,
  "cost_jpy": 0.04,
  "output_text": "お会計\n商品A: ¥1,200\n...",
  "ground_truth": "お会計\n商品A: ¥1,200\n..."
}
```

## モデルと料金

| モデル | 入力 ($/1M tokens) | 出力 ($/1M tokens) | 備考 |
|--------|-------------------|-------------------|------|
| Palmyra Vision 7B | $0.30 | $1.50 | 日本語精度低 |
| Nemotron Nano 12B V2 | $0.30 | $1.50 | |
| Nova 2 Lite | $0.30 | $1.50 | 低コスト、高速 |
| Kimi K2.5 | $0.30 | $1.50 | |
| Qwen3 VL 235B (MoE) | $0.30 | $1.50 | 高精度 |
| Claude Opus 4.6 | $15.00 | $75.00 | 最高精度、高コスト |

**為替レート**: ¥150/USD（設定ファイルで変更可能）

**注意**: 料金は2026年4月時点の推定値です。最新の料金は [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/) で確認してください。

## トラブルシューティング

### ValidationException: The requested model requires an inference profile

**原因**: Nova 2 Lite および Claude Opus 4.6 は inference profile が必須です。

**解決**: モデルIDにリージョンプレフィックスを追加:
- `us.amazon.nova-2-lite-v1:0`
- `us.anthropic.claude-opus-4-6-v1`

### AccessDeniedException

**原因**: Bedrock モデルへのアクセスが有効化されていません。

**解決**: AWS Console > Bedrock > Model Access で該当モデルを有効化してください。

### ThrottlingException

**原因**: API呼び出しがレート制限に達しました。

**解決**: 少し待ってから再実行してください。

### 日本語が正しく認識されない

**原因**: 一部のモデル（Palmyra Vision 7B）は日本語の認識精度が低いです。

**解決**: Qwen3 VL, Nova 2 Lite, Claude Opus などの他のモデルを試してください。

## ライセンス

このデモコードおよびサンプル画像は MIT License です。

## 参考リンク

- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)
- [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)
- [AWS Bedrock Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html)
- [Writer Palmyra Vision Model Card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-writer-palmyra-vision-7b.html)

## 関連ブログ記事

このデモの結果を基にした詳細な分析記事:
- `blog/2026-04-01-palmyra-vision-ocr-test.md` (日本語)
