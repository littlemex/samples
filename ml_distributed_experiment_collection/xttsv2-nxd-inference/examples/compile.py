"""XTTSv2 GPT Transformer Neuron コンパイルスクリプト

trn1 インスタンスで実行すること。
Neuron SDK (neuronx_distributed_inference) が必要。

BF16 精度で Prefill + Decode 両モデルをコンパイルし、指定ディレクトリに保存する。

背景:
  FP16 (exponent 5bit) は attention 計算で overflow/underflow が発生しやすく
  WER（単語誤り率）が大幅に悪化する（FP16: WER 68.8% vs BF16: WER 0%）。
  trn1 のネイティブ dtype は BF16 であり、BF16 を強く推奨する。

使用例:
    python examples/compile.py \
        --model-path /home/ubuntu/XTTS-v2 \
        --output-dir /home/ubuntu/neuron_xttsv2_compiled_bf16
"""

import argparse
import sys
import time


def parse_args():
    parser = argparse.ArgumentParser(
        description="XTTSv2 GPT Transformer を BF16 で Neuron コンパイルする"
    )
    parser.add_argument(
        "--model-path",
        required=True,
        help="XTTSv2 チェックポイントディレクトリのパス（config.json と model.pth を含む）",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="コンパイル済みモデルの保存先ディレクトリ",
    )
    parser.add_argument(
        "--tp-degree",
        type=int,
        default=2,
        help="Tensor Parallelism の degree（デフォルト: 2）",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Neuron SDK のインポート（trn1 インスタンスで実行すること）
    try:
        import torch
        from neuronx_distributed_inference.models.config import NeuronConfig
    except ImportError as e:
        print(f"[ERROR] Neuron SDK のインポートに失敗しました: {e}")
        print("[ERROR] trn1 インスタンス上で実行してください。")
        sys.exit(1)

    # neuron_xttsv2 パッケージのインポート
    # このスクリプトはリポジトリルートから実行することを想定している
    try:
        from neuron_xttsv2.config import XTTSv2InferenceConfig
        from neuron_xttsv2.application_gpt import NeuronApplicationXTTSv2GPT
    except ImportError as e:
        print(f"[ERROR] neuron_xttsv2 パッケージのインポートに失敗しました: {e}")
        print("[ERROR] リポジトリルートから実行しているか確認してください。")
        sys.exit(1)

    print("[INFO] XTTSv2 Neuron コンパイル開始")
    print(f"[INFO] モデルパス: {args.model_path}")
    print(f"[INFO] 出力先: {args.output_dir}")
    print(f"[INFO] TP degree: {args.tp_degree}")
    print(f"[INFO] dtype: BF16 (trn1 ネイティブ dtype)")
    print()

    # NeuronConfig を BF16 で設定
    # torch_dtype=torch.bfloat16 を指定することで FP16 attention 問題を回避
    neuron_config = NeuronConfig(
        batch_size=1,
        tp_degree=args.tp_degree,
        torch_dtype=torch.bfloat16,
    )

    # XTTSv2InferenceConfig の作成
    config = XTTSv2InferenceConfig(neuron_config=neuron_config)

    print("[INFO] コンパイル設定:")
    print(f"  gpt_layers:              {config.gpt_layers}")
    print(f"  gpt_n_model_channels:    {config.gpt_n_model_channels}")
    print(f"  gpt_n_heads:             {config.gpt_n_heads}")
    print(f"  max_seq_len:             {config.max_seq_len}")
    print(f"  head_dim:                {config.head_dim}")
    print()

    # Application の初期化（モデルパスは compile() 後に使用される）
    app = NeuronApplicationXTTSv2GPT(args.output_dir, config)

    # コンパイル実行（時間を計測）
    print("[INFO] コンパイル中... （trn1.2xlarge で 10-20 分程度かかります）")
    t_start = time.time()

    try:
        app.compile(compiled_model_path=args.output_dir)
    except Exception as e:
        print(f"[ERROR] コンパイルに失敗しました: {e}")
        raise

    elapsed = time.time() - t_start
    minutes = int(elapsed // 60)
    seconds = elapsed % 60

    print()
    print(f"[OK] コンパイル完了")
    print(f"[OK] コンパイル時間: {minutes}m {seconds:.1f}s")
    print(f"[OK] コンパイル済みモデルの保存先: {args.output_dir}")
    print()
    print("[INFO] 次のステップ: run_inference.py でロードと推論を確認してください")
    print(f"  python examples/run_inference.py \\")
    print(f"      --compiled-dir {args.output_dir} \\")
    print(f"      --checkpoint <XTTSv2 .pth ファイルのパス>")


if __name__ == "__main__":
    main()
