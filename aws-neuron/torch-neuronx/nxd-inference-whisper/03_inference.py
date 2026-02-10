#!/usr/bin/env python3
"""
Whisper 推論スクリプト

コンパイル済みの Whisper モデルで音声認識を実行します。

Usage:
    # ダミー音声でテスト
    python3 03_inference.py --compiled-path models/whisper-tiny-compiled-tp2

    # 実際の音声ファイルで推論
    python3 03_inference.py --compiled-path models/whisper-tiny-compiled-tp2 --audio test_audio/sample.wav

    # 日本語音声の文字起こし
    python3 03_inference.py --compiled-path models/whisper-tiny-compiled-tp2 --audio japanese.wav --language ja
"""

import argparse
import sys
import time
import numpy as np
from pathlib import Path

# Add current dir to path
sys.path.insert(0, str(Path(__file__).parent))

from whisper_nxd_model import WhisperNxDModel


def parse_args():
    """コマンドライン引数をパース"""
    parser = argparse.ArgumentParser(description='Whisper 推論')

    parser.add_argument(
        '--compiled-path',
        type=str,
        required=True,
        help='コンパイル済みモデルのパス'
    )

    parser.add_argument(
        '--audio',
        type=str,
        default=None,
        help='音声ファイルのパス (省略時はダミー音声を使用)'
    )

    parser.add_argument(
        '--language',
        type=str,
        default=None,
        help='言語コード (en, ja, zh など、省略時は自動検出)'
    )

    parser.add_argument(
        '--task',
        type=str,
        default='transcribe',
        choices=['transcribe', 'translate'],
        help='タスク: transcribe (文字起こし) または translate (英語に翻訳)'
    )

    parser.add_argument(
        '--tp-size',
        type=int,
        default=2,
        help='Tensor Parallelism 度 (デフォルト: 2)'
    )

    parser.add_argument(
        '--duration',
        type=int,
        default=10,
        help='ダミー音声の長さ（秒）(デフォルト: 10)'
    )

    return parser.parse_args()


def generate_dummy_audio(duration_sec=10, sample_rate=16000):
    """ダミー音声を生成"""
    num_samples = int(duration_sec * sample_rate)
    audio_data = np.random.randn(num_samples).astype(np.float32) * 0.1
    return audio_data, sample_rate


def main():
    args = parse_args()

    print("=" * 80)
    print("Whisper 推論")
    print("=" * 80)

    # コンパイル済みモデルの確認
    compiled_path = Path(args.compiled_path)
    if not compiled_path.exists():
        print(f"\n❌ コンパイル済みモデルが見つかりません: {args.compiled_path}")
        print("   先に 02_compile.py を実行してください")
        return 1

    print(f"\n設定:")
    print(f"  コンパイル済みモデル: {args.compiled_path}")
    print(f"  音声ファイル: {args.audio if args.audio else 'ダミー音声'}")
    print(f"  言語: {args.language if args.language else '自動検出'}")
    print(f"  タスク: {args.task}")
    print(f"  TP 度: {args.tp_size}")

    # モデルのロード
    print(f"\n📦 モデルをロードしています...")
    try:
        model = WhisperNxDModel(
            model_path=args.compiled_path,
            compiled_path=args.compiled_path,
            batch_size=1,
            tp_degree=args.tp_size,
            language=args.language,
            task=args.task,
            device_type="neuron"
        )
        model.load()
        print(f"  ✓ モデルのロードが完了しました")
        print(f"    モード: {model.get_mode_string()}")
    except Exception as e:
        print(f"  ✗ モデルのロードに失敗しました: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # 音声の準備
    if args.audio:
        print(f"\n🎤 音声ファイルを読み込んでいます: {args.audio}")
        if not Path(args.audio).exists():
            print(f"  ✗ 音声ファイルが見つかりません: {args.audio}")
            return 1

        try:
            print(f"  ファイルパス: {args.audio}")
        except Exception as e:
            print(f"  ✗ 音声ファイルの読み込みに失敗しました: {e}")
            return 1
    else:
        print(f"\n🎤 ダミー音声を生成しています ({args.duration} 秒)...")
        audio_data, sample_rate = generate_dummy_audio(args.duration)
        print(f"  ✓ ダミー音声を生成しました")
        print(f"    サンプルレート: {sample_rate} Hz")
        print(f"    長さ: {args.duration} 秒")

    # 推論の実行
    print(f"\n🔄 推論を実行しています...")
    try:
        start_time = time.time()

        if args.audio:
            # 音声ファイルから推論
            result = model.transcribe_file(args.audio, verbose=False)
            transcription = result['text']
            audio_duration = result['audio_duration']
        else:
            # ダミー音声から推論
            transcription, metrics = model.infer(audio_data, sample_rate=sample_rate)
            audio_duration = metrics['audio_duration']

        inference_time = time.time() - start_time
        rtf = inference_time / audio_duration

        print(f"\n✅ 推論が完了しました")
        print(f"\n" + "=" * 80)
        print("結果:")
        print("=" * 80)
        print(f"音声の長さ: {audio_duration:.2f} 秒")
        print(f"推論時間: {inference_time:.3f} 秒")
        print(f"Real-Time Factor: {rtf:.3f}x")

        if rtf < 1.0:
            speedup = 1.0 / rtf
            print(f"  → リアルタイムの {speedup:.1f} 倍速で処理")
        else:
            print(f"  → リアルタイムより {rtf:.1f} 倍遅い")

        print(f"\n文字起こし結果:")
        print(f"  \"{transcription}\"")

        if not args.audio:
            print(f"\n注: ダミー音声（ランダムノイズ）のため、認識結果は空または意味不明です")
            print(f"    実際の音声ファイルで試す場合は --audio オプションを使用してください")

    except Exception as e:
        print(f"\n✗ 推論に失敗しました: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
