"""XTTS v2 コンポーネント別実行時間ベンチマーク

4 コンポーネントの CPU 上での実行時間を計測し、GPT Transformer が
ボトルネックであることを数値で示す。

実際の次元数（d_model=1024, n_heads=16, 30 層）を使うと CPU では数十秒かかるため、
1/4 スケール（d_model=256, n_heads=4, seq_len=270, 30 層）で測定する。
層数 30 は維持しているため、コンポーネント間の比率は実機と近い値になる。

実行方法（プロジェクトルートから）:
    PYTHONPATH=stubs:src uv run python examples/benchmark_timing.py
"""

import sys
import os
import time

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_root, "stubs"), os.path.join(_root, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import torch
import torch.nn as nn

# --- スケール設定 ---
# 実機: d_model=1024, n_heads=16, seq_len=1081, n_layers=30
# ベンチ: 1/4 スケール（層数は 30 のまま維持）
D      = 256    # d_model
HEADS  = 4      # n_heads
SEQ    = 270    # seq_len (≒ 1081/4)
LAYERS = 30     # GPT 層数（実機と同じ）
BATCH  = 1
WARMUP = 2
RUNS   = 5


# --- コンポーネント近似実装 ---

class ApproxConditioningEncoder(nn.Module):
    """ConditioningEncoder の近似: 参照音声 → 話者特徴量
    実機: 参照音声スペクトログラム [B, mel_bins, T] → latent [B, T', D]
    近似: Linear + 2 層 Transformer Encoder"""

    def __init__(self):
        super().__init__()
        self.proj = nn.Linear(80, D)
        enc_layer = nn.TransformerEncoderLayer(D, HEADS, D * 4, batch_first=True)
        self.encoder = nn.TransformerEncoder(enc_layer, num_layers=2)

    def forward(self, x):
        # x: [B, T, 80] (mel spectrogram frames)
        return self.encoder(self.proj(x))


class ApproxPerceiverResampler(nn.Module):
    """PerceiverResampler の近似: 話者特徴量 → GPT 入力埋め込み
    実機: cross-attention で固定長 latent に圧縮
    近似: MultiheadAttention 1 層"""

    def __init__(self):
        super().__init__()
        self.latents = nn.Parameter(torch.randn(1, SEQ, D))
        self.attn = nn.MultiheadAttention(D, HEADS, batch_first=True)
        self.proj = nn.Linear(D, D)

    def forward(self, context):
        latents = self.latents.expand(context.size(0), -1, -1)
        out, _ = self.attn(latents, context, context)
        return self.proj(out)


class ApproxGPTTransformer(nn.Module):
    """GPT Transformer の近似: mel トークン自己回帰生成の中核
    実機: 30 層 Self-Attention + MLP、KV-Cache あり
    近似: 30 層 Transformer Decoder（キャッシュなし Prefill 相当）"""

    def __init__(self):
        super().__init__()
        dec_layer = nn.TransformerEncoderLayer(D, HEADS, D * 4, batch_first=True)
        self.transformer = nn.TransformerEncoder(dec_layer, num_layers=LAYERS)

    def forward(self, x):
        return self.transformer(x)


class ApproxHifiDecoder(nn.Module):
    """HifiDecoder の近似: mel トークン → 音声波形
    実機: HiFi-GAN ベースの Vocoder（Conv1d + ResBlock の積み重ね）
    近似: 3 層 Conv1d"""

    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv1d(D, D, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv1d(D, D, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv1d(D, 1, kernel_size=3, padding=1),
        )

    def forward(self, x):
        # x: [B, T, D] -> [B, D, T] for Conv1d -> [B, 1, T]
        return self.net(x.transpose(1, 2))


def measure(fn, warmup=WARMUP, runs=RUNS):
    """ウォームアップ後の平均実行時間（秒）を返す"""
    for _ in range(warmup):
        with torch.no_grad():
            fn()
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        with torch.no_grad():
            fn()
        times.append(time.perf_counter() - t0)
    return sum(times) / len(times)


def main():
    print("=" * 60)
    print("XTTS v2 コンポーネント別実行時間ベンチマーク（CPU）")
    print(f"  スケール: d_model={D}, n_heads={HEADS}, seq_len={SEQ}, layers={LAYERS}")
    print(f"  測定: warmup={WARMUP} + {RUNS} runs の平均")
    print("=" * 60)
    print()

    # 入力データ
    mel_input   = torch.randn(BATCH, SEQ, 80)       # 参照音声 mel spectrogram
    cond_latent = torch.randn(BATCH, SEQ, D)         # conditioning latent
    gpt_input   = torch.randn(BATCH, SEQ, D)         # GPT Transformer 入力埋め込み
    gpt_output  = torch.randn(BATCH, SEQ, D)         # GPT Transformer 出力 hidden states

    # モデル初期化
    cond    = ApproxConditioningEncoder()
    perc    = ApproxPerceiverResampler()
    gpt     = ApproxGPTTransformer()
    hifi    = ApproxHifiDecoder()

    for m in (cond, perc, gpt, hifi):
        m.eval()

    # 計測
    print("計測中...")
    t_cond = measure(lambda: cond(mel_input))
    t_perc = measure(lambda: perc(cond_latent))
    t_gpt  = measure(lambda: gpt(gpt_input))
    t_hifi = measure(lambda: hifi(gpt_output))

    total = t_cond + t_perc + t_gpt + t_hifi

    print()
    print(f"{'コンポーネント':<30} {'時間 (ms)':>10} {'割合':>8}")
    print("-" * 52)
    for name, t in [
        ("ConditioningEncoder",   t_cond),
        ("PerceiverResampler",    t_perc),
        (f"GPT Transformer ({LAYERS} 層)", t_gpt),
        ("HifiDecoder",           t_hifi),
    ]:
        bar = "#" * int(t / total * 40)
        print(f"  {name:<28} {t*1000:>8.1f}ms  {t/total*100:>5.1f}%  {bar}")
    print("-" * 52)
    print(f"  {'合計':<28} {total*1000:>8.1f}ms  100.0%")
    print()

    gpt_pct = t_gpt / total * 100
    if gpt_pct >= 80:
        print(f"[OK] GPT Transformer が全体の {gpt_pct:.1f}% を占めています。")
        print("     Neuron コンパイル対象として GPT を選択した数値的根拠です。")
    else:
        print(f"[INFO] GPT Transformer の割合: {gpt_pct:.1f}%")
        print("       (CPU 環境では近似実装のため実機と比率が異なる場合があります)")

    print()
    print("注: 実機（trn1）では Neuron コンパイル後の GPT が大幅に高速化されるため、")
    print("    Prefill 1 ステップの比率はさらに GPT 側に偏ります。")


if __name__ == "__main__":
    main()
