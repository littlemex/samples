# vLLM Inference Benchmark

g5 (GPU) と inf2 (Inferentia2) インスタンスでの vLLM 推論性能を比較するベンチマークツール。

## 概要

このベンチマークツールは以下をサポートします：

- **Offline (Batch) Inference**: バッチ推論のスループット計測
- **Online (API Server) Inference**: APIサーバー経由のレイテンシ計測
- **Prefix Caching**: プレフィックスキャッシュの効果検証
- **MLflow統合**: メトリクスの自動記録と可視化

## 検証シナリオ

1. **短いプロンプト + 短い生成** (チャットボット想定)
2. **長いプロンプト + 短い生成** (要約タスク想定)
3. **短いプロンプト + 長い生成** (文章生成想定)
4. **バッチ処理** (複数バッチサイズでの比較)
5. **Prefix Caching** (キャッシュ効果の検証)

## セットアップ

### 前提条件

- Python 3.10以上
- vLLMがインストールされた環境
  - GPU: `pip install vllm`
  - Neuron: `pip install vllm-neuron`

### 依存パッケージのインストール

```bash
cd /work/samples/inference
pip install -r requirements.txt
```

### MLflowサーバーの起動（オプション）

ローカルでMLflowトラッキングサーバーを起動する場合：

```bash
# MLflowインストール
pip install mlflow

# MLflowサーバー起動（別ターミナル）
mlflow server --host 0.0.0.0 --port 5000
```

MLflow UIにアクセス: http://localhost:5000

## 使用方法

### 重要: インスタンスタイプ別の実行について

**g5（GPU）とinf2（Neuron）は別々のEC2インスタンスで実行する必要があります。**

各インスタンスで独立してベンチマークを実行し、後で結果を統合します：

1. **g5.xlargeインスタンス**でベンチマーク実行
2. **inf2.xlargeインスタンス**でベンチマーク実行
3. 結果JSONファイルを収集
4. `merge_results.py`で結果を統合して分析

### Offline (Batch) 推論ベンチマーク

#### ステップ1: g5インスタンスでの実行

```bash
# g5.xlargeインスタンスにログイン
cd /work/samples/inference/benchmark

# ベンチマーク実行
python offline_benchmark.py \
  --output-dir ../results/g5 \
  --test-prefix-caching \
  --no-mlflow  # またはMLflowサーバーを指定

# 結果ファイルを保存
# results/g5/offline_results_YYYYMMDD_HHMMSS.json
```

#### ステップ2: inf2インスタンスでの実行

```bash
# inf2.xlargeインスタンスにログイン
cd /work/samples/inference/benchmark

# ベンチマーク実行
python offline_benchmark.py \
  --output-dir ../results/inf2 \
  --test-prefix-caching \
  --no-mlflow  # またはMLflowサーバーを指定

# 結果ファイルを保存
# results/inf2/offline_results_YYYYMMDD_HHMMSS.json
```

#### ステップ3: 結果の統合と分析

結果JSONファイルを1つの場所に集めて統合：

```bash
# 結果ファイルをマージ
python merge_results.py \
  results/g5/offline_results_*.json \
  results/inf2/offline_results_*.json \
  --output results/merged_results.json

# 統合された結果を分析
python analyze_results.py \
  --results-file results/merged_results.json \
  --output-dir results/analysis
```

基本的な使用方法（単一インスタンス）：

```bash
cd /work/samples/inference/benchmark
python offline_benchmark.py
```

詳細なオプション指定：

```bash
python offline_benchmark.py \
  --model Qwen/Qwen3-0.6B-Instruct \
  --scenarios short medium prefix_caching \
  --batch-sizes 1 4 8 \
  --max-tokens 128 \
  --num-runs 3 \
  --test-prefix-caching \
  --output-dir ../results/offline \
  --mlflow-uri http://localhost:5000
```

#### 主要なオプション

- `--model`: 使用するモデル名（デフォルト: Qwen/Qwen3-0.6B-Instruct）
- `--scenarios`: 実行するシナリオ（short, medium, long, prefix_caching）
- `--batch-sizes`: テストするバッチサイズのリスト
- `--max-tokens`: 生成する最大トークン数
- `--num-runs`: 各シナリオの実行回数（ウォームアップ含む）
- `--test-prefix-caching`: prefix caching ON/OFFの両方をテスト
- `--enable-prefix-caching`: prefix cachingを有効化
- `--no-mlflow`: MLflowトラッキングを無効化

### Online (API Server) 推論ベンチマーク

*実装中*

### 実験条件の記録

すべてのベンチマーク実行時に、以下の情報が自動的に記録されます：

- システム情報（CPU、メモリ、GPU/Neuron）
- インスタンスタイプ（EC2メタデータから取得）
- Pythonパッケージバージョン（vllm, torch等）
- 環境変数
- ベンチマーク設定（バッチサイズ、温度等）

結果は以下の形式で保存されます：

```
results/
├── env_info_YYYYMMDD_HHMMSS.json          # 環境情報
├── offline_results_YYYYMMDD_HHMMSS.json   # 詳細結果
└── offline_summary_YYYYMMDD_HHMMSS.json   # サマリー
```

### 結果の統合（複数インスタンス）

g5とinf2の両方でベンチマークを実行した後、結果を統合する方法：

#### 方法1: JSON ファイルのマージ

```bash
# 各インスタンスから結果JSONファイルを収集
# 例: scp等でローカルマシンやS3にコピー

# 結果をマージ
python benchmark/merge_results.py \
  results/g5/offline_results_20260116_100000.json \
  results/inf2/offline_results_20260116_110000.json \
  --output results/merged_results.json

# マージされた結果を分析
python benchmark/analyze_results.py \
  --results-file results/merged_results.json \
  --output-dir results/comparison
```

#### 方法2: MLflowでの統合

同一のMLflowサーバーにデータを集約する場合：

```bash
# g5インスタンスで実行（MLflow有効）
python offline_benchmark.py --mlflow-uri http://YOUR_MLFLOW_SERVER:5000

# inf2インスタンスで実行（同じMLflowサーバーを指定）
python offline_benchmark.py --mlflow-uri http://YOUR_MLFLOW_SERVER:5000
```

両方のインスタンスが同じMLflowサーバーにデータを送信すれば、MLflow UIで一括比較可能です。

### MLflowでの結果確認

MLflowサーバーが起動している場合、ブラウザで以下にアクセス：

```
http://localhost:5000
```

実験名: `vllm-offline-benchmark` または `vllm-online-benchmark`

各実験run には以下が記録されます：
- **Parameters**: モデル名、インスタンスタイプ、バッチサイズ、prefix caching設定等
- **Metrics**: tokens/sec、time/token、レイテンシ等
- **Artifacts**: 環境情報JSON
- **Tags**: 実験ID、タイムスタンプ、エラー情報等

**MLflow UIでの比較:**
- 複数のrunを選択して "Compare" ボタンをクリック
- パラメータとメトリクスを並べて比較
- グラフの生成とエクスポート

## 計測指標

### 主要メトリクス

1. **Tokens per Second (tokens/sec)**: スループット指標
2. **Time per Token (ms/tok)**: 平均トークン生成時間
3. **First Token Latency (sec)**: 初回トークン生成までの時間（TTFT）
4. **Inter-token Latency (ms)**: トークン間の平均生成時間
5. **Total Time (sec)**: 全体の処理時間
6. **Memory Usage (MB)**: メモリ使用量

### 正規化と比較

異なる出力長の結果を公平に比較するため、以下の正規化指標を使用：

```python
tokens_per_second = actual_output_tokens / total_time
time_per_token = (total_time * 1000) / actual_output_tokens  # ms
```

実際に生成されたトークン数（`actual_output_tokens`）を用いて計算します。

## 結果の可視化

### Pythonでの分析

```python
import json

# 結果の読み込み
with open('results/offline_results_20260116_120000.json') as f:
    data = json.load(f)

# データ分析
for result in data['results']:
    print(f"{result['instance_type']}: {result['tokens_per_second']:.2f} tok/s")
```

### MLflowでの比較

MLflow UIで以下が可能：
- 複数runの並列比較
- メトリクスのグラフ化
- パラメータでのフィルタリング
- 結果のエクスポート

## トラブルシューティング

### vLLMがインストールされていない

```bash
# GPU環境
pip install vllm

# Neuron環境
pip install --extra-index-url=https://pip.repos.neuron.amazonaws.com vllm-neuron
```

### MLflowに接続できない

1. MLflowサーバーが起動しているか確認
2. `--mlflow-uri` オプションで正しいURIを指定
3. または `--no-mlflow` でMLflowを無効化

### メモリ不足エラー

- `--max-model-len` を小さくする
- `--batch-sizes` を小さくする
- より小さいモデルを使用する

### Neuron環境でのエラー

1. Neuron SDKがインストールされているか確認：
   ```bash
   neuron-ls
   ```

2. vllm-neuronプラグインがインストールされているか確認：
   ```bash
   pip show vllm-neuron
   ```

## ディレクトリ構成

```
samples/inference/
├── README.md                    # このファイル
├── requirements.txt             # 依存パッケージ
├── setup_mlflow.sh             # MLflowセットアップスクリプト
├── benchmark/
│   ├── common/
│   │   ├── __init__.py
│   │   ├── env_info.py         # 環境情報収集
│   │   └── metrics.py          # メトリクス管理
│   ├── offline_benchmark.py    # Offlineベンチマーク
│   ├── analyze_results.py      # 結果分析・可視化
│   └── merge_results.py        # 複数結果ファイルの統合
├── configs/                     # 設定ファイル
├── data/                        # テストデータ
└── results/                     # 結果出力先
    ├── g5/                      # g5インスタンスの結果
    ├── inf2/                    # inf2インスタンスの結果
    └── analysis/                # 分析結果
```

## 実行ワークフロー例

### 完全な比較ベンチマーク

```bash
# 1. g5.xlargeインスタンスで実行
ssh g5-instance
cd /work/samples/inference/benchmark
python offline_benchmark.py \
  --scenarios short medium prefix_caching \
  --batch-sizes 1 4 8 \
  --test-prefix-caching \
  --output-dir ../results/g5 \
  --no-mlflow

# 結果ファイル: results/g5/offline_results_YYYYMMDD_HHMMSS.json
# ローカルにコピー: scp g5-instance:/work/samples/inference/results/g5/*.json ./results/g5/

# 2. inf2.xlargeインスタンスで実行
ssh inf2-instance
cd /work/samples/inference/benchmark
python offline_benchmark.py \
  --scenarios short medium prefix_caching \
  --batch-sizes 1 4 8 \
  --test-prefix-caching \
  --output-dir ../results/inf2 \
  --no-mlflow

# 結果ファイル: results/inf2/offline_results_YYYYMMDD_HHMMSS.json
# ローカルにコピー: scp inf2-instance:/work/samples/inference/results/inf2/*.json ./results/inf2/

# 3. ローカルマシンで結果を統合・分析
python benchmark/merge_results.py \
  results/g5/offline_results_*.json \
  results/inf2/offline_results_*.json \
  -o results/merged_results.json

python benchmark/analyze_results.py \
  --results-file results/merged_results.json \
  --output-dir results/analysis

# 4. 生成された分析結果を確認
ls results/analysis/
# - tokens_per_sec_comparison.png
# - prefix_caching_effect.png
# - batch_size_scaling.png
# - time_per_token_comparison.png
# - summary_report.txt
```

## ライセンス

Apache License 2.0

## 参考資料

- [vLLM Documentation](https://docs.vllm.ai/)
- [AWS Neuron vLLM Guide](https://awsdocs-neuron.readthedocs-hosted.com/en/latest/libraries/nxd-inference/vllm/)
- [MLflow Documentation](https://mlflow.org/docs/latest/index.html)
- [Anatomy of vLLM](https://blog.vllm.ai/2025/09/05/anatomy-of-vllm.html)
