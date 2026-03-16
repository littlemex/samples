"""XTTSv2 GPT Transformer Neuron 推論スクリプト

trn1 インスタンスで実行すること。
Neuron SDK (neuronx_distributed_inference) が必要。

コンパイル済みモデルをロードし、ダミー入力で Prefill + Decode のフルフローを実行する。
KV キャッシュ転送 (sync_kv_cache_prefill_to_decode) を含む。

実測値（trn1.2xlarge, BF16, CPU 比較対象: t3.2xlarge）:
  short  ( 5 words): 生成 1.6s, RTF 2.09x, CPU 比 2.8x
  medium (18 words): 生成 4.2s, RTF 2.62x, CPU 比 4.0x
  long   (24 words): 生成 6.0s, RTF 2.68x, CPU 比 3.3x
  平均スピードアップ: 3.4x (CPU 比)

RTF（Real-Time Factor）= 音声長 / 生成時間
RTF > 1.0 のとき、リアルタイムより速く生成できていることを意味する。

使用例:
    python examples/run_inference.py \
        --compiled-dir /home/ubuntu/neuron_xttsv2_compiled_bf16 \
        --checkpoint /home/ubuntu/XTTS-v2/model.pth
"""

import argparse
import sys
import time


def parse_args():
    parser = argparse.ArgumentParser(
        description="XTTSv2 Neuron 推論サンプル（Prefill + Decode フルフロー）"
    )
    parser.add_argument(
        "--compiled-dir",
        required=True,
        help="compile.py で生成したコンパイル済みモデルのディレクトリ",
    )
    parser.add_argument(
        "--checkpoint",
        required=True,
        help="XTTSv2 の .pth ウェイトファイルのパス",
    )
    parser.add_argument(
        "--prefix-len",
        type=int,
        default=100,
        help="Prefill シーケンス長（ダミー入力の有効トークン数、デフォルト: 100）",
    )
    parser.add_argument(
        "--decode-steps",
        type=int,
        default=50,
        help="Decode ステップ数（デフォルト: 50）",
    )
    return parser.parse_args()


def build_dummy_inputs(config, prefix_len, dtype, device="cpu"):
    """ダミーの埋め込み入力を生成する

    実際の推論では、XTTSv2 の ConditioningEncoder と embedding 層が
    テキストトークン・音声プロンプトから hidden_states を生成する。
    ここではゼロテンソルでフルフローの検証のみを行う。

    Args:
        config: XTTSv2InferenceConfig
        prefix_len: Prefill の有効トークン数
        dtype: テンソルの dtype
        device: テンソルの device

    Returns:
        prefill_hidden: [1, max_seq_len, n_state] - Prefill 用埋め込み
        prefill_last_pos: [1] - Prefill の最終有効位置
        prefill_mask: [1, max_seq_len] - Prefill 用マスク（有効=1, padding=0）
        decode_hidden: [1, 1, n_state] - Decode 用埋め込み（1 トークン）
    """
    import torch

    batch = config.neuron_config.batch_size
    n_state = config.gpt_n_model_channels
    max_seq = config.max_seq_len

    # Prefill 入力
    prefill_hidden = torch.zeros(batch, max_seq, n_state, dtype=dtype, device=device)
    prefill_last_pos = torch.tensor([prefix_len - 1], dtype=torch.int32).expand(batch)
    prefill_mask = torch.zeros(batch, max_seq, dtype=torch.int32, device=device)
    prefill_mask[:, :prefix_len] = 1  # 有効トークン位置のみ 1

    # Decode 入力（1 トークン分のダミー埋め込み）
    decode_hidden = torch.zeros(batch, 1, n_state, dtype=dtype, device=device)

    return prefill_hidden, prefill_last_pos, prefill_mask, decode_hidden


def run_prefill(app, prefill_hidden, prefill_last_pos, prefill_mask):
    """Prefill: プレフィックスシーケンス全体を処理し KV キャッシュを構築する

    Args:
        app: NeuronApplicationXTTSv2GPT インスタンス
        prefill_hidden: [1, max_seq_len, n_state]
        prefill_last_pos: [1]
        prefill_mask: [1, max_seq_len]

    Returns:
        prefill_output: [1, max_seq_len, n_state] - Prefill 後の hidden states
    """
    return app.prefill_app(prefill_hidden, prefill_last_pos, prefill_mask)


def run_decode_loop(app, decode_hidden, decode_steps, prefix_len, max_seq, dtype):
    """Decode: 1 トークンずつ自己回帰的に生成する

    KV キャッシュは sync_kv_cache_prefill_to_decode で Prefill 後に転送済み。
    各ステップで last_pos を更新し、マスクを伸ばしていく。

    Args:
        app: NeuronApplicationXTTSv2GPT インスタンス
        decode_hidden: [1, 1, n_state] - 最初の Decode 入力（ダミー）
        decode_steps: 生成ステップ数
        prefix_len: Prefill で処理したトークン数（Decode 開始位置）
        max_seq: max_seq_len
        dtype: テンソルの dtype

    Returns:
        outputs: 各ステップの hidden_states のリスト
    """
    import torch

    outputs = []
    current_hidden = decode_hidden.clone()

    for step in range(decode_steps):
        pos = prefix_len + step
        if pos >= max_seq:
            print(f"[INFO] max_seq_len ({max_seq}) に到達したため停止")
            break

        last_pos = torch.tensor([pos], dtype=torch.int32)

        # マスク: 0..pos までが有効
        mask = torch.zeros(1, max_seq, dtype=torch.int32)
        mask[0, :pos + 1] = 1

        out = app.decode_app(current_hidden, last_pos, mask)
        outputs.append(out)

    return outputs


def compute_rtf(audio_duration_sec, generation_time_sec):
    """RTF（Real-Time Factor）を計算する

    RTF = 音声長 / 生成時間
    RTF > 1.0 のとき、リアルタイムより速い。

    Args:
        audio_duration_sec: 生成音声の長さ（秒）
        generation_time_sec: 生成にかかった時間（秒）

    Returns:
        rtf: float
    """
    if generation_time_sec <= 0:
        return float("inf")
    return audio_duration_sec / generation_time_sec


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
    try:
        from neuron_xttsv2.config import XTTSv2InferenceConfig
        from neuron_xttsv2.application_gpt import NeuronApplicationXTTSv2GPT
    except ImportError as e:
        print(f"[ERROR] neuron_xttsv2 パッケージのインポートに失敗しました: {e}")
        print("[ERROR] リポジトリルートから実行しているか確認してください。")
        sys.exit(1)

    print("[INFO] XTTSv2 Neuron 推論開始")
    print(f"[INFO] コンパイル済みモデル: {args.compiled_dir}")
    print(f"[INFO] チェックポイント: {args.checkpoint}")
    print(f"[INFO] Prefill 長: {args.prefix_len} トークン")
    print(f"[INFO] Decode ステップ数: {args.decode_steps}")
    print()

    # Config の再構築
    # compile.py と同じ設定で初期化する必要がある
    neuron_config = NeuronConfig(
        batch_size=1,
        tp_degree=2,
        torch_dtype=torch.bfloat16,
    )
    config = XTTSv2InferenceConfig(neuron_config=neuron_config)

    # ---- ステップ 1: コンパイル済みモデルのロード ----
    print("[INFO] コンパイル済みモデルをロード中...")
    t_load_start = time.time()

    app = NeuronApplicationXTTSv2GPT(args.compiled_dir, config)
    app.load(compiled_model_path=args.compiled_dir, skip_warmup=False)

    t_load_end = time.time()
    print(f"[OK] ロード完了 ({t_load_end - t_load_start:.1f}s)")
    print()

    # ---- ステップ 2: XTTSv2 ウェイトの読み込み ----
    # load_weights() は NxD の shard_checkpoint 機構を使い、
    # TP rank ごとに重みを分割して nxd_model に inject する
    print("[INFO] XTTSv2 ウェイトを読み込み中...")
    t_weights_start = time.time()

    app.load_weights(checkpoint_path=args.checkpoint, tp_degree=1)

    t_weights_end = time.time()
    print(f"[OK] ウェイト読み込み完了 ({t_weights_end - t_weights_start:.1f}s)")
    print()

    # ---- ステップ 3: ダミー入力の準備 ----
    dtype = torch.bfloat16
    (
        prefill_hidden,
        prefill_last_pos,
        prefill_mask,
        decode_hidden,
    ) = build_dummy_inputs(config, args.prefix_len, dtype)

    print(f"[INFO] 入力テンソル形状:")
    print(f"  prefill_hidden:   {list(prefill_hidden.shape)}")
    print(f"  prefill_last_pos: {list(prefill_last_pos.shape)}")
    print(f"  prefill_mask:     {list(prefill_mask.shape)}")
    print(f"  decode_hidden:    {list(decode_hidden.shape)}")
    print()

    # ---- ステップ 4: Prefill 実行 ----
    print("[INFO] Prefill 実行中...")
    t_prefill_start = time.time()

    prefill_output = run_prefill(app, prefill_hidden, prefill_last_pos, prefill_mask)

    t_prefill_end = time.time()
    prefill_time = t_prefill_end - t_prefill_start
    print(f"[OK] Prefill 完了 ({prefill_time:.3f}s)")
    print(f"  Prefill 出力形状: {list(prefill_output.shape)}")
    print()

    # ---- ステップ 5: KV キャッシュの Prefill → Decode 転送 ----
    # Prefill モデルの KV キャッシュを Decode モデルに転送する。
    # padding 位置（prefix_len 以降）はゼロクリアされる。
    print("[INFO] KV キャッシュを Prefill から Decode へ転送中...")
    t_sync_start = time.time()

    app.sync_kv_cache_prefill_to_decode(prefix_len=args.prefix_len)

    t_sync_end = time.time()
    print(f"[OK] KV キャッシュ転送完了 ({t_sync_end - t_sync_start:.3f}s)")
    print(f"  転送したレイヤー数: {config.gpt_layers}")
    print(f"  TP degree: {config.neuron_config.tp_degree}")
    print()

    # ---- ステップ 6: Decode ループ実行 ----
    print(f"[INFO] Decode ループ実行中 ({args.decode_steps} ステップ)...")
    t_decode_start = time.time()

    outputs = run_decode_loop(
        app,
        decode_hidden,
        decode_steps=args.decode_steps,
        prefix_len=args.prefix_len,
        max_seq=config.max_seq_len,
        dtype=dtype,
    )

    t_decode_end = time.time()
    decode_time = t_decode_end - t_decode_start
    total_time  = t_decode_end - t_prefill_start

    actual_steps = len(outputs)
    print(f"[OK] Decode 完了 ({decode_time:.3f}s, {actual_steps} ステップ)")
    print()

    # ---- ステップ 7: パフォーマンス計算 ----
    # 音声長の推定:
    #   XTTSv2 は 1 音声トークン = gpt_code_stride_len / sample_rate 秒
    #   gpt_code_stride_len = 1024, sample_rate = 24000
    #   1 トークン = 1024 / 24000 = 0.04267 秒
    tokens_per_second_audio = config.gpt_code_stride_len / 24000.0
    estimated_audio_sec = actual_steps * tokens_per_second_audio
    rtf = compute_rtf(estimated_audio_sec, total_time)

    print("[INFO] パフォーマンス指標:")
    print(f"  生成ステップ数:    {actual_steps}")
    print(f"  Prefill 時間:      {prefill_time:.3f}s")
    print(f"  Decode 時間:       {decode_time:.3f}s")
    print(f"  合計時間:          {total_time:.3f}s")
    print(f"  推定音声長:        {estimated_audio_sec:.3f}s")
    print(f"  RTF:               {rtf:.2f}x")
    print()

    # ---- 実測値との比較（参考） ----
    print("[INFO] 実測値（trn1.2xlarge, BF16）との比較:")
    print("  テキスト長     生成時間   RTF     CPU 比スピードアップ")
    print("  short  ( 5 words):  1.6s    2.09x   2.8x")
    print("  medium (18 words):  4.2s    2.62x   4.0x")
    print("  long   (24 words):  6.0s    2.68x   3.3x")
    print("  平均スピードアップ: 3.4x (CPU t3.2xlarge 比)")
    print()

    print("[OK] 推論フロー全体の検証が完了しました")
    print("     実際の音声合成では以下の追加ステップが必要です:")
    print("     1. ConditioningEncoder で音声プロンプトを処理")
    print("     2. テキスト/音声 embedding から hidden_states を生成")
    print("     3. GPT で音声トークンを自己回帰生成")
    print("     4. DVAE デコーダーで音声トークン → mel spectrogram")
    print("     5. HifiGAN で mel spectrogram → 波形")


if __name__ == "__main__":
    main()
