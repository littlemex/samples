#!/usr/bin/env python3
"""
Whisper モデルのコンパイルスクリプト

NxD Inference を使用して Whisper モデルを Neuron 向けにコンパイルします。

Usage:
    # Whisper Tiny をコンパイル (TP=2)
    python3 02_compile.py --model openai/whisper-tiny --tp-size 2

    # Whisper Large V3 をコンパイル (TP=8)
    python3 02_compile.py --model openai/whisper-large-v3 --tp-size 8
"""

import argparse
import sys
import time
from pathlib import Path

# Add current dir to path
sys.path.insert(0, str(Path(__file__).parent))

from whisper_nxd_model import WhisperNxDModel, NXD_AVAILABLE


def parse_args():
    """コマンドライン引数をパース"""
    parser = argparse.ArgumentParser(description='Whisper モデルのコンパイル')

    parser.add_argument(
        '--model',
        type=str,
        default='openai/whisper-tiny',
        help='モデル名またはパス (デフォルト: openai/whisper-tiny)'
    )

    parser.add_argument(
        '--tp-size',
        type=int,
        default=2,
        choices=[1, 2, 4, 8, 16],
        help='Tensor Parallelism 度 (デフォルト: 2)'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=1,
        help='バッチサイズ (デフォルト: 1)'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default=None,
        help='コンパイル済みモデルの保存先 (デフォルト: models/<model-name>-compiled-tp<tp-size>)'
    )

    parser.add_argument(
        '--force',
        action='store_true',
        help='既存のコンパイル済みモデルを上書き'
    )

    return parser.parse_args()


def get_model_short_name(model_path):
    """モデルパスから短い名前を取得"""
    # "openai/whisper-tiny" -> "whisper-tiny"
    return model_path.split('/')[-1]


def main():
    args = parse_args()

    print("=" * 80)
    print("Whisper モデルのコンパイル")
    print("=" * 80)

    # NxD Inference の確認
    if not NXD_AVAILABLE:
        print("\n❌ NxD Inference が利用できません")
        print("   以下のコマンドでインストールしてください:")
        print("   pip install git+https://github.com/aws-neuron/neuronx-distributed-inference.git@main")
        return 1

    print("\n✓ NxD Inference が利用可能です")

    # 出力ディレクトリの決定
    if args.output_dir:
        compiled_path = args.output_dir
    else:
        model_short_name = get_model_short_name(args.model)
        compiled_path = f"models/{model_short_name}-compiled-tp{args.tp_size}"

    # 既存のコンパイル済みモデルの確認
    compiled_path_obj = Path(compiled_path)
    if compiled_path_obj.exists() and not args.force:
        print(f"\n⚠️  コンパイル済みモデルが既に存在します: {compiled_path}")
        print("   上書きする場合は --force オプションを使用してください")
        print("   スキップして次のステップに進みます")
        return 0

    # 設定の表示
    print(f"\n設定:")
    print(f"  モデル: {args.model}")
    print(f"  TP 度: {args.tp_size}")
    print(f"  バッチサイズ: {args.batch_size}")
    print(f"  出力先: {compiled_path}")

    # モデルの作成
    print(f"\n📦 モデルを初期化しています...")
    try:
        model = WhisperNxDModel(
            model_path=args.model,
            compiled_path=compiled_path,
            batch_size=args.batch_size,
            tp_degree=args.tp_size,
            device_type="neuron"
        )
        print("  ✓ モデルの初期化が完了しました")
    except Exception as e:
        print(f"  ✗ モデルの初期化に失敗しました: {e}")
        return 1

    # コンパイルの実行
    print(f"\n🔧 コンパイルを開始します...")
    print(f"   ⚠️  コンパイルには時間がかかります:")

    model_short_name = get_model_short_name(args.model)
    if 'tiny' in model_short_name.lower():
        print(f"      Whisper Tiny: 30-60 秒程度")
    elif 'base' in model_short_name.lower():
        print(f"      Whisper Base: 1-2 分程度")
    elif 'small' in model_short_name.lower():
        print(f"      Whisper Small: 5-10 分程度")
    elif 'medium' in model_short_name.lower():
        print(f"      Whisper Medium: 15-30 分程度")
    elif 'large' in model_short_name.lower():
        print(f"      Whisper Large: 30-60 分程度")

    try:
        start_time = time.time()
        model.compile()
        compile_time = time.time() - start_time

        print(f"\n✅ コンパイルが完了しました！")
        print(f"   所要時間: {compile_time:.1f} 秒 ({compile_time/60:.1f} 分)")
        print(f"   保存先: {compiled_path}")

        # ファイル構造の表示
        print(f"\n📁 コンパイル済みモデルの構造:")
        if compiled_path_obj.exists():
            for item in sorted(compiled_path_obj.rglob('*')):
                if item.is_file():
                    rel_path = item.relative_to(compiled_path_obj)
                    size = item.stat().st_size / (1024 * 1024)  # MB
                    print(f"   {rel_path}: {size:.1f} MB")

        print(f"\n次のステップ:")
        print(f"   python3 03_inference.py --compiled-path {compiled_path}")

    except Exception as e:
        print(f"\n✗ コンパイルに失敗しました: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
