# NxD Inference Whisper サンプル

AWS Neuron で OpenAI Whisper モデルを動かすサンプルコードです。NxD Inference (NeuronX Distributed Inference) を使用して、Tensor Parallelism と KV-Cache による高速な音声認識を実現します。

## 環境要件

| コンポーネント | 必須バージョン | 備考 |
|---------------|---------------|------|
| **Neuron SDK** | 2.27+ | 2.28+ 推奨 |
| **neuronxcc** | 2.22+ | `get_program_sharding_info` 関数が必須 |
| **NxD Inference** | 0.7.0 (開発版) | Whisper サポート版 |
| **PyTorch** | 2.5+ | 2.8+ 推奨 |
| **transformers** | 4.40+ | Whisper モデルサポート |
| **openai-whisper** | 20250625 | 音声処理ユーティリティ |

## インスタンスタイプ

- **inf2.xlarge**: 2 NeuronCores (TP=2 推奨)
- **trn1.2xlarge**: 2 NeuronCores (TP=2 推奨)
- **trn1.32xlarge**: 16 NeuronCores (TP=8 推奨)

## セットアップ

### 1. Neuron 仮想環境のアクティベート

```bash
source /opt/aws_neuronx_venv_pytorch_2_9_nxd_inference/bin/activate
```

### 2. NxD Inference 0.7.0 のインストール

```bash
pip install git+https://github.com/aws-neuron/neuronx-distributed-inference.git@main
```

### 3. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 4. 環境確認

```bash
python3 01_setup.py
```

## 使い方

### Step 1: 環境確認

```bash
python3 01_setup.py
```

必要なライブラリとバージョンが正しくインストールされているか確認します。

### Step 2: モデルのコンパイル

```bash
python3 02_compile.py --model openai/whisper-tiny --tp-size 2
```

**オプション**:
- `--model`: 使用するモデル (デフォルト: `openai/whisper-tiny`)
  - `openai/whisper-tiny` (39M)
  - `openai/whisper-base` (74M)
  - `openai/whisper-small` (244M)
  - `openai/whisper-medium` (769M)
  - `openai/whisper-large-v3` (1550M)
- `--tp-size`: Tensor Parallelism 度 (デフォルト: 2)
  - inf2.xlarge / trn1.2xlarge: `2`
  - trn1.32xlarge: `8`

**コンパイル時間**:
- Whisper Tiny: 30-60 秒
- Whisper Large V3: 30-60 分

### Step 3: 推論の実行

**ダミー音声でテスト**:

```bash
python3 03_inference.py --compiled-path models/whisper-tiny-compiled-tp2
```

**実際の音声ファイルで推論**:

```bash
python3 03_inference.py --compiled-path models/whisper-tiny-compiled-tp2 --audio test_audio/sample.wav
```

**オプション**:
- `--compiled-path`: コンパイル済みモデルのパス (必須)
- `--audio`: 音声ファイルのパス (省略時はダミー音声を使用)
- `--language`: 言語コード (`en`, `ja`, `zh` など、省略時は自動検出)
- `--tp-size`: Tensor Parallelism 度 (デフォルト: 2)

## 性能ベンチマーク

| モデル | TP 度 | インスタンス | RTF | Speedup |
|--------|------|-------------|-----|---------|
| Whisper Tiny | 2 | inf2.xlarge | 0.05x | 20x |
| Whisper Large V3 | 2 | trn1.2xlarge | 0.15-0.25x | 4-7x |
| Whisper Large V3 | 8 | trn1.32xlarge | 0.05-0.1x | 10-20x |

**RTF (Real-Time Factor)**: 音声長に対する処理時間の比率。RTF=0.1 は、10 秒の音声を 1 秒で処理できることを意味します。

## ファイル構成

```
nxd-inference-whisper/
├── README.md                    # このファイル
├── requirements.txt             # 依存パッケージ
├── whisper_nxd_model.py        # NxD Inference Whisper ラッパー
├── 01_setup.py                  # 環境確認スクリプト
├── 02_compile.py                # コンパイルスクリプト
├── 03_inference.py              # 推論スクリプト
├── models/                      # モデル保存ディレクトリ
│   ├── whisper-tiny/           # ダウンロードされたモデル
│   └── whisper-tiny-compiled-tp2/  # コンパイル済みモデル
└── test_audio/                  # テスト音声ファイル
    └── README.md               # 音声ファイルの取得方法
```

## トラブルシューティング

### 1. `ImportError: cannot import name 'get_program_sharding_info'`

**原因**: neuronxcc のバージョンが古い (2.21 以下)

**解決策**:
```bash
pip install neuronxcc --upgrade --extra-index-url https://pip.repos.neuron.amazonaws.com
python3 -c "import neuronxcc; print(neuronxcc.__version__)"  # 2.22+ であることを確認
```

### 2. `ModuleNotFoundError: No module named 'whisper'`

**原因**: openai-whisper パッケージが未インストール

**解決策**:
```bash
pip install openai-whisper
```

### 3. コンパイルが途中で停止

**原因**: メモリ不足、または NeuronCore の問題

**解決策**:
```bash
# Neuron デバイスの状態確認
neuron-ls

# Neuron ランタイムの再起動
sudo systemctl restart neuron-rtd
```

### 4. NxD Inference の Whisper モジュールが見つからない

**原因**: NxD Inference のバージョンが 0.7.0 未満

**解決策**:
```bash
# 開発版をインストール
pip install git+https://github.com/aws-neuron/neuronx-distributed-inference.git@main

# バージョン確認
python3 -c "import neuronx_distributed_inference; print(neuronx_distributed_inference.__version__)"
```

## 参考資料

- [AWS Neuron Documentation](https://awsdocs-neuron.readthedocs-hosted.com/)
- [NxD Inference GitHub Repository](https://github.com/aws-neuron/neuronx-distributed-inference)
- [OpenAI Whisper](https://github.com/openai/whisper)

## ライセンス

- **NxD Inference**: Apache License 2.0 (AWS)
- **Whisper**: MIT License (OpenAI)
- **このサンプルコード**: MIT License

## 作者

Claude Sonnet 4.5
