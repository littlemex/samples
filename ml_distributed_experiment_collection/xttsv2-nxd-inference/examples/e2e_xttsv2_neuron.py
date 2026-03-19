"""XTTSv2 + NxD Inference E2E テスト（性能 + 精度）

CPU XTTS モデルの GPT Transformer を NeuronApplicationXTTSv2GPT に差し替えて
実際のテキストから音声を生成し、CPU ベースラインと比較する。

Forward Override パターン:
  cpu_model.gpt.gpt  →  NeuronGPT2InferenceModel(neuron_gpt_app)
  cpu_model.synthesize() がそのまま呼べる
"""
import os, sys, time, json
import torch
import numpy as np
import soundfile as sf

SRC = os.environ.get('SRC_PATH', '/home/ubuntu/nxd-inference-xttsv2/phase3-integration/src')
sys.path.insert(0, SRC)

COMPILED = os.environ.get('COMPILED_MODEL_PATH', '/home/ubuntu/neuron_xttsv2_compiled')
XTTS_DIR = os.environ.get('XTTS_MODEL_DIR', '/home/ubuntu/xttsv2-model')
OUTPUT   = os.environ.get('OUTPUT_DIR', '/home/ubuntu/results/e2e-test')
TP       = int(os.environ.get('TP_DEGREE', 2))
NUM_RUNS = int(os.environ.get('NUM_RUNS', 3))
TEMPERATURE = float(os.environ.get('TEMPERATURE', 0.65))  # ブログ同条件のデフォルト

TEST_TEXT = "Hello, this is a test of the XTTSv2 text to speech system running on AWS Trainium."

os.makedirs(OUTPUT, exist_ok=True)

# ============================================================
# 0. 前提確認
# ============================================================
print("=" * 60)
print("[STEP 0] 前提確認")
print("=" * 60)
assert os.path.isdir(f"{COMPILED}/prefill"), f"[ERROR] {COMPILED}/prefill が見つかりません"
assert os.path.isdir(f"{COMPILED}/decode"),  f"[ERROR] {COMPILED}/decode が見つかりません"
assert os.path.isfile(f"{XTTS_DIR}/model.pth"), f"[ERROR] {XTTS_DIR}/model.pth が見つかりません"
print(f"[OK] compiled: {COMPILED}")
print(f"[OK] xtts_dir: {XTTS_DIR}")
print(f"[OK] output:   {OUTPUT}")

# ============================================================
# 1. リファレンス音声を生成
# ============================================================
print("\n" + "=" * 60)
print("[STEP 1] リファレンス音声生成")
print("=" * 60)
ref_path = os.path.join(OUTPUT, "reference.wav")
if not os.path.exists(ref_path):
    sr = 22050
    t = np.linspace(0, 3.0, int(sr * 3.0))
    wave = (0.3 * np.sin(2 * np.pi * 200 * t)
          + 0.2 * np.sin(2 * np.pi * 400 * t)
          + 0.1 * np.sin(2 * np.pi * 800 * t)).astype(np.float32)
    sf.write(ref_path, wave, sr)
    print(f"[OK] リファレンス音声を生成: {ref_path}")
else:
    print(f"[OK] リファレンス音声は既存: {ref_path}")

# ============================================================
# 2. CPU XTTS モデルのロード
# ============================================================
print("\n" + "=" * 60)
print("[STEP 2] CPU XTTS モデルのロード")
print("=" * 60)
from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts

xtts_cfg = XttsConfig()
xtts_cfg.load_json(os.path.join(XTTS_DIR, "config.json"))
cpu_model = Xtts.init_from_config(xtts_cfg)
cpu_model.load_checkpoint(xtts_cfg, checkpoint_dir=XTTS_DIR, eval=True)
cpu_model.cpu()
print("[OK] CPU XTTS モデルのロード完了")

# XTTS 内部構造の確認
orig_gpt = cpu_model.gpt.gpt
print(f"[INFO] model.gpt.gpt の型: {type(orig_gpt).__name__}")
print(f"[INFO] model.gpt のモジュール: {[n for n,_ in cpu_model.gpt.named_children()]}")

# ============================================================
# 3. CPU ベースライン推論（latency 測定）
# ============================================================
print("\n" + "=" * 60)
print("[STEP 3] CPU ベースライン推論")
print("=" * 60)
cpu_latencies = []
cpu_wav_out = None
for run in range(NUM_RUNS):
    t0 = time.time()
    out = cpu_model.synthesize(
        TEST_TEXT, xtts_cfg,
        speaker_wav=ref_path, language="en", gpt_cond_len=3,
        temperature=TEMPERATURE,
    )
    elapsed = time.time() - t0
    cpu_latencies.append(elapsed)
    if run == 0:
        cpu_wav_out = out["wav"]
    print(f"  run {run+1}/{NUM_RUNS}: {elapsed:.2f}s, wav_len={len(out['wav'])/24000:.2f}s")

cpu_mean = np.mean(cpu_latencies)
cpu_min  = np.min(cpu_latencies)
cpu_wav_path = os.path.join(OUTPUT, "output_cpu_baseline.wav")
sf.write(cpu_wav_path, cpu_wav_out, 24000)
print(f"[OK] CPU 平均レイテンシ: {cpu_mean:.2f}s (min={cpu_min:.2f}s)")
print(f"[OK] CPU 音声保存: {cpu_wav_path}")

# ============================================================
# 4. Neuron GPT のロードと重み注入
# ============================================================
print("\n" + "=" * 60)
print("[STEP 4] Neuron GPT ロード + 重み注入")
print("=" * 60)
from neuron_xttsv2.config import XTTSv2InferenceConfig
from neuron_xttsv2.application_gpt import NeuronApplicationXTTSv2GPT
from neuron_xttsv2.neuron_xttsv2 import NeuronGPT2InferenceModel
from neuronx_distributed_inference.models.config import NeuronConfig

neuron_config = NeuronConfig(
    batch_size=1, tp_degree=TP,
    seq_len=1081, torch_dtype=torch.bfloat16,
)
config = XTTSv2InferenceConfig(neuron_config=neuron_config)

t0 = time.time()
gpt_app = NeuronApplicationXTTSv2GPT(model_path=COMPILED, config=config)
gpt_app.load(COMPILED, skip_warmup=False)
load_time = time.time() - t0
print(f"[OK] Neuron GPT ロード完了: {load_time:.1f}s")

t0 = time.time()
gpt_app.load_weights(os.path.join(XTTS_DIR, "model.pth"), tp_degree=TP)
weight_time = time.time() - t0
print(f"[OK] 重み注入完了: {weight_time:.1f}s")

# ============================================================
# 5. Forward Override: cpu_model.gpt.gpt を差し替え
# ============================================================
print("\n" + "=" * 60)
print("[STEP 5] Forward Override")
print("=" * 60)
gpt_module = cpu_model.gpt
neuron_wrapper = NeuronGPT2InferenceModel(
    gpt_config=orig_gpt.config,
    neuron_gpt_app=gpt_app,
    mel_pos_emb=gpt_module.mel_pos_embedding,
    mel_emb=gpt_module.mel_embedding,
    final_norm=gpt_module.final_norm,
    mel_head=gpt_module.mel_head,
    gpt_ln_f=orig_gpt.ln_f,   # GPT2Model internal final norm; CPU applies this before final_norm
    gpt_wpe=orig_gpt.wpe,     # GPT2Model positional embedding; CPU adds wpe(pos) to inputs_embeds
)
# gpt_inference を差し替え（gpt.gpt は get_logits で last_hidden_state を返すので触らない）
gpt_module.gpt_inference = neuron_wrapper
print(f"[OK] cpu_model.gpt.gpt_inference を NeuronGPT2InferenceModel に差し替え完了")

# ============================================================
# 6. Neuron 推論（latency 測定）
# ============================================================
print("\n" + "=" * 60)
print("[STEP 6] Neuron 推論")
print("=" * 60)
neuron_latencies = []
neuron_wav_out = None
for run in range(NUM_RUNS):
    # token_count をリセット
    gpt_module.gpt_inference.token_count = 0
    gpt_module.gpt_inference.cached_prefix_emb = None
    gpt_module.gpt_inference.is_prefill = True

    t0 = time.time()
    out = cpu_model.synthesize(
        TEST_TEXT, xtts_cfg,
        speaker_wav=ref_path, language="en", gpt_cond_len=3,
        temperature=TEMPERATURE,
    )
    elapsed = time.time() - t0
    neuron_latencies.append(elapsed)
    if run == 0:
        neuron_wav_out = out["wav"]
    print(f"  run {run+1}/{NUM_RUNS}: {elapsed:.2f}s, wav_len={len(out['wav'])/24000:.2f}s")

neuron_mean = np.mean(neuron_latencies)
neuron_min  = np.min(neuron_latencies)
neuron_wav_path = os.path.join(OUTPUT, "output_neuron.wav")
sf.write(neuron_wav_path, neuron_wav_out, 24000)
print(f"[OK] Neuron 平均レイテンシ: {neuron_mean:.2f}s (min={neuron_min:.2f}s)")
print(f"[OK] Neuron 音声保存: {neuron_wav_path}")

# ============================================================
# 7. 精度比較: CPU vs Neuron（メルスペクトログラム類似度）
# ============================================================
# NOTE: TTS は確率的サンプリング（temperature > 0）で動作するため、
#       同じ入力でも CPU と Neuron の波形はサンプル単位では一致しない。
#       スペクトル内容（音の周波数構成）で比較するのが適切。
print("\n" + "=" * 60)
print("[STEP 7] 精度比較 (CPU vs Neuron - メルスペクトログラム類似度)")
print("=" * 60)
from scipy.signal import stft as _stft

SR = 24000
NPERSEG = 1024

def _spectral_cosine(wav1, wav2):
    """平均パワースペクトル間のコサイン類似度（音色・音高の類似度を測定）"""
    min_len = min(len(wav1), len(wav2))
    w1 = wav1[:min_len].astype(np.float32)
    w2 = wav2[:min_len].astype(np.float32)
    _, _, S1 = _stft(w1, fs=SR, nperseg=NPERSEG, noverlap=NPERSEG // 2)
    _, _, S2 = _stft(w2, fs=SR, nperseg=NPERSEG, noverlap=NPERSEG // 2)
    avg1 = (np.abs(S1) ** 2).mean(axis=1)
    avg2 = (np.abs(S2) ** 2).mean(axis=1)
    return float(np.dot(avg1, avg2) / (np.linalg.norm(avg1) * np.linalg.norm(avg2) + 1e-8))

spectral_sim = _spectral_cosine(cpu_wav_out, neuron_wav_out)
cpu_dur_s    = len(cpu_wav_out) / SR
neuron_dur_s = len(neuron_wav_out) / SR
dur_ratio    = neuron_dur_s / cpu_dur_s if cpu_dur_s > 0 else 0.0

print(f"  スペクトル類似度 (1.0が理想): {spectral_sim:.4f}")
print(f"  CPU 音声長:    {cpu_dur_s:.2f}s")
print(f"  Neuron 音声長: {neuron_dur_s:.2f}s  (比率: {dur_ratio:.2f})")

if spectral_sim > 0.90 and 0.7 <= dur_ratio <= 1.3:
    quality = "PASS - スペクトル内容が CPU と一致"
elif spectral_sim > 0.70:
    quality = "WARN - スペクトル内容に軽微な差異あり"
else:
    quality = "FAIL - スペクトル内容が CPU と大きく乖離"
print(f"  品質判定: {quality}")

# ============================================================
# 8. 性能サマリー
# ============================================================
print("\n" + "=" * 60)
print("[STEP 8] 性能サマリー")
print("=" * 60)
speedup = cpu_mean / neuron_mean if neuron_mean > 0 else 0
print(f"  CPU  平均レイテンシ: {cpu_mean:.2f}s (min={cpu_min:.2f}s)")
print(f"  Neuron 平均レイテンシ: {neuron_mean:.2f}s (min={neuron_min:.2f}s)")
print(f"  速度比 (CPU/Neuron):  {speedup:.2f}x")
print(f"  Neuron 音声長:        {neuron_dur_s:.2f}s")

results = {
    "test_text": TEST_TEXT,
    "cpu": {"latencies_s": cpu_latencies, "mean_s": cpu_mean, "min_s": cpu_min},
    "neuron": {"latencies_s": neuron_latencies, "mean_s": neuron_mean, "min_s": neuron_min},
    "speedup": speedup,
    "accuracy": {"spectral_cosine": spectral_sim, "duration_ratio": dur_ratio},
    "quality": quality,
}
result_path = os.path.join(OUTPUT, "e2e_results.json")
with open(result_path, "w") as f:
    json.dump(results, f, indent=2)
print(f"\n[OK] 結果を保存: {result_path}")
print("[SUCCESS] E2E テスト完了")
