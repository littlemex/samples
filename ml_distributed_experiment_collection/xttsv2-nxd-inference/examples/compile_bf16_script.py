"""BF16 Neuron コンパイルスクリプト

FP16 の精度不足（WER 68.8%）を解消するため BF16 で再コンパイル。
BF16 は trn1 のネイティブ dtype: exponent 8bit (FP16 は 5bit) により
attention の overflow/underflow を防ぐ。
"""
import sys
import os
import torch

sys.path.insert(0, os.environ.get('SRC_PATH', '/home/ubuntu/nxd-inference-xttsv2/phase3-integration/src'))

from neuron_xttsv2.config import XTTSv2InferenceConfig
from neuron_xttsv2.application_gpt import NeuronApplicationXTTSv2GPT
from neuronx_distributed_inference.models.config import NeuronConfig

compiled = os.environ.get('COMPILED_MODEL_PATH', '/home/ubuntu/neuron_xttsv2_compiled_bf16')
tp = int(os.environ.get('TP_DEGREE', 2))
seq_len = int(os.environ.get('SEQ_LEN', 1081))

print(f'[INFO] dtype=bfloat16, tp_degree={tp}, seq_len={seq_len}')
print(f'[INFO] compiled_path={compiled}')

nc = NeuronConfig(batch_size=1, tp_degree=tp, seq_len=seq_len, torch_dtype=torch.bfloat16)
cfg = XTTSv2InferenceConfig(neuron_config=nc)
print(f'[INFO] gpt_layers={cfg.gpt_layers}, n_heads={cfg.gpt_n_heads}, n_state={cfg.gpt_n_model_channels}')

app = NeuronApplicationXTTSv2GPT(model_path=compiled, config=cfg)
print('[INFO] BF16 コンパイル開始 (30-60 分かかります)...')
app.compile(compiled)
print('[SUCCESS] BF16 コンパイル完了:', compiled)
