"""長いテキストでの BF16 品質検証 + レイテンシ測定

CPU と BF16 Neuron で同一テキストを合成し WER・音声長・速度を比較する。
短いテキストでは WER=0% (正規化) を確認済み。長いテキストでの品質維持を検証。
"""
import sys
import os
import time
import re
import torch
import warnings
import logging

logging.disable(logging.CRITICAL)
warnings.filterwarnings('ignore')

sys.path.insert(0, os.environ.get('SRC_PATH', '/home/ubuntu/nxd-inference-xttsv2/phase3-integration/src'))

from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
from neuron_xttsv2.config import XTTSv2InferenceConfig
from neuron_xttsv2.application_gpt import NeuronApplicationXTTSv2GPT
from neuron_xttsv2.neuron_xttsv2 import NeuronGPT2InferenceModel
from neuronx_distributed_inference.models.config import NeuronConfig
import soundfile as sf
import numpy as np
import whisper

COMPILED = os.environ.get('COMPILED_MODEL_PATH', '/home/ubuntu/neuron_xttsv2_compiled_bf16')
XTTS_DIR = os.environ.get('XTTS_MODEL_DIR', '/home/ubuntu/xttsv2-model')
TP = int(os.environ.get('TP_DEGREE', 2))
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', '/home/ubuntu/results/long-text-test')
REF_WAV = os.environ.get('REF_WAV', '/home/ubuntu/results/e2e-prefill-kvsync/reference.wav')

TEST_CASES = [
    (
        'short',
        'Hello, this is a test.',
        'hello this is a test',
    ),
    (
        'medium',
        'Hello, this is a test of the XTTS v2 text to speech system running on AWS Inferentia 2.',
        'hello this is a test of the xtts v2 text to speech system running on aws inferentia 2',
    ),
    (
        'long',
        'AWS Trainium is a machine learning accelerator designed for training and inference workloads. '
        'It provides high performance at low cost for large language models.',
        'aws trainium is a machine learning accelerator designed for training and inference workloads '
        'it provides high performance at low cost for large language models',
    ),
]


def normalize(text):
    text = text.lower()
    text = re.sub(r'[^a-z0-9 ]', '', text)
    return text.split()


def wer(ref_str, hyp_str):
    r = normalize(ref_str)
    h = normalize(hyp_str)
    if not r:
        return 0.0
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + cost)
    return d[len(r)][len(h)] / len(r)


os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- モデルのロード ---
print('[INFO] CPU XTTS モデルをロード中...')
xtts_cfg = XttsConfig()
xtts_cfg.load_json(os.path.join(XTTS_DIR, 'config.json'))
cpu_model = Xtts.init_from_config(xtts_cfg)
cpu_model.load_checkpoint(xtts_cfg, checkpoint_dir=XTTS_DIR, eval=True)
cpu_model.cpu()
print('[OK] CPU モデルロード完了')

# CPU gpt_inference を保存 (後で復元するため)
gpt_module = cpu_model.gpt
orig_gpt_inference = gpt_module.gpt_inference
print(f'[INFO] CPU gpt_inference type: {type(orig_gpt_inference).__name__}')

print('[INFO] BF16 Neuron GPT をロード中...')
nc = NeuronConfig(batch_size=1, tp_degree=TP, seq_len=1081, torch_dtype=torch.bfloat16)
cfg = XTTSv2InferenceConfig(neuron_config=nc)
gpt_app = NeuronApplicationXTTSv2GPT(model_path=COMPILED, config=cfg)
gpt_app.load(COMPILED, skip_warmup=False)
gpt_app.load_weights(os.path.join(XTTS_DIR, 'model.pth'), tp_degree=TP)
print('[OK] BF16 Neuron GPT ロード完了')

orig_gpt = gpt_module.gpt
neuron_wrapper = NeuronGPT2InferenceModel(
    gpt_config=orig_gpt.config,
    neuron_gpt_app=gpt_app,
    mel_pos_emb=gpt_module.mel_pos_embedding,
    mel_emb=gpt_module.mel_embedding,
    final_norm=gpt_module.final_norm,
    mel_head=gpt_module.mel_head,
    gpt_ln_f=orig_gpt.ln_f,
    gpt_wpe=orig_gpt.wpe,
)
print('[OK] NeuronGPT2InferenceModel 構築完了')

print('[INFO] Whisper large-v2 をロード中...')
wm = whisper.load_model('large-v2')
print('[OK] Whisper ロード完了')


def synthesize_cpu(text):
    """CPU で音声合成"""
    gpt_module.gpt_inference = orig_gpt_inference
    t0 = time.time()
    out = cpu_model.synthesize(
        text, xtts_cfg,
        speaker_wav=REF_WAV, language='en', gpt_cond_len=3,
        temperature=0.01,
    )
    elapsed = time.time() - t0
    return out['wav'], elapsed


def synthesize_neuron(text):
    """Neuron BF16 で音声合成"""
    gpt_module.gpt_inference = neuron_wrapper
    neuron_wrapper.token_count = 0
    neuron_wrapper.cached_prefix_emb = None
    neuron_wrapper.is_prefill = True
    t0 = time.time()
    out = cpu_model.synthesize(
        text, xtts_cfg,
        speaker_wav=REF_WAV, language='en', gpt_cond_len=3,
        temperature=0.01,
    )
    elapsed = time.time() - t0
    return out['wav'], elapsed


# --- テスト実行 ---
results = []
print('\n=== 長テキスト検証開始 ===')
for name, text, ref_text in TEST_CASES:
    words = len(text.split())
    print(f'\n[TEST] {name} ({words} 単語): "{text[:70]}{"..." if len(text) > 70 else ""}"')

    # CPU
    wav_cpu, cpu_time = synthesize_cpu(text)
    cpu_path = os.path.join(OUTPUT_DIR, f'cpu_{name}.wav')
    sf.write(cpu_path, wav_cpu, 24000)
    hyp_cpu = wm.transcribe(cpu_path, language='en')['text'].strip()
    wer_cpu = wer(ref_text, hyp_cpu)
    cpu_len = len(wav_cpu) / 24000

    # Neuron BF16
    wav_neuron, neuron_time = synthesize_neuron(text)
    neuron_path = os.path.join(OUTPUT_DIR, f'neuron_bf16_{name}.wav')
    sf.write(neuron_path, wav_neuron, 24000)
    hyp_neuron = wm.transcribe(neuron_path, language='en')['text'].strip()
    wer_neuron = wer(ref_text, hyp_neuron)
    neuron_len = len(wav_neuron) / 24000

    speedup = cpu_time / neuron_time if neuron_time > 0 else 0
    rtf_neuron = neuron_len / neuron_time if neuron_time > 0 else 0

    print(f'  ref:          "{ref_text[:70]}"')
    print(f'  CPU hyp:      "{hyp_cpu}"')
    print(f'  Neuron hyp:   "{hyp_neuron}"')
    print(f'  CPU    WER={wer_cpu * 100:.1f}%  len={cpu_len:.2f}s  time={cpu_time:.1f}s')
    print(f'  Neuron WER={wer_neuron * 100:.1f}%  len={neuron_len:.2f}s  time={neuron_time:.1f}s')
    print(f'  Neuron: {speedup:.1f}x faster, RTF={rtf_neuron:.2f} (audio_len/gen_time)')

    results.append({
        'name': name, 'words': words,
        'cpu_wer': wer_cpu, 'neuron_wer': wer_neuron,
        'cpu_len': cpu_len, 'neuron_len': neuron_len,
        'cpu_time': cpu_time, 'neuron_time': neuron_time,
        'hyp_cpu': hyp_cpu, 'hyp_neuron': hyp_neuron,
    })

print('\n=== サマリー ===')
print(f'{"テスト":<8} {"単語":>5} {"CPU WER":>9} {"N WER":>9} '
      f'{"CPU len":>8} {"N len":>8} {"N time":>8} {"RTF":>6} {"Speedup":>8}')
print('-' * 80)
for r in results:
    speedup = r['cpu_time'] / r['neuron_time'] if r['neuron_time'] > 0 else 0
    rtf = r['neuron_len'] / r['neuron_time'] if r['neuron_time'] > 0 else 0
    print(f'{r["name"]:<8} {r["words"]:>5} '
          f'{r["cpu_wer"]*100:>8.1f}% {r["neuron_wer"]*100:>8.1f}% '
          f'{r["cpu_len"]:>7.2f}s {r["neuron_len"]:>7.2f}s '
          f'{r["neuron_time"]:>7.1f}s {rtf:>5.2f}x {speedup:>7.1f}x')

avg_n_wer = np.mean([r['neuron_wer'] for r in results])
avg_speedup = np.mean([r['cpu_time'] / r['neuron_time'] for r in results if r['neuron_time'] > 0])
print(f'\n  Neuron BF16 平均 WER (正規化): {avg_n_wer * 100:.1f}%')
print(f'  平均スピードアップ: {avg_speedup:.1f}x')

if avg_n_wer < 0.20:
    print('[SUCCESS] 長テキストでも高品質を維持 (WER < 20%)')
elif avg_n_wer < 0.40:
    print('[PARTIAL] 概ね良好だが改善余地あり (WER 20-40%)')
else:
    print('[FAIL] 長テキストで品質が劣化 (WER > 40%)')
