"""Neuron SDK なしで動作する CPU スモークテスト

Neuron ライブラリ（neuronx_distributed, neuronx_distributed_inference）が
インストールされていない環境で 3 つのモジュールが正しく動作するか確認する。

実行方法（プロジェクトルートから）:
    PYTHONPATH=stubs:src python examples/smoke_test.py
"""

import sys
import os

# stubs/ と src/ をパスに追加（スクリプト直接実行用）
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(_root, "stubs"), os.path.join(_root, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import torch
from types import SimpleNamespace

from neuron_xttsv2.modeling_gpt import NeuronGPTTransformer, NeuronGPTInstance
from neuron_xttsv2.model_wrapper_gpt import ModelWrapperGPTPrefill, ModelWrapperGPTDecode
from neuron_xttsv2.application_gpt import NeuronApplicationXTTSv2GPT, _make_zero_state_dict


# 小さい config (CPU でも高速)
ns = SimpleNamespace(
    gpt_layers=2,
    gpt_n_model_channels=64,
    gpt_n_heads=4,
    max_seq_len=16,
    neuron_config=SimpleNamespace(
        batch_size=1,
        torch_dtype=torch.float32,
        tp_degree=1,
    ),
    xttsv2_checkpoint_path="",
)
BATCH = ns.neuron_config.batch_size
SEQ   = ns.max_seq_len
N     = ns.gpt_n_model_channels


def test_modeling_gpt():
    print("[TEST] modeling_gpt.py")

    model = NeuronGPTTransformer(
        n_layer=ns.gpt_layers,
        n_state=N,
        n_head=ns.gpt_n_heads,
        batch_size=BATCH,
        seq_len=SEQ,
        dtype=torch.float32,
    )

    # Prefill: seq_len > 1
    hidden   = torch.randn(BATCH, SEQ, N)
    last_pos = torch.tensor([SEQ - 1]).expand(BATCH)
    mask     = torch.ones(BATCH, SEQ, dtype=torch.int32)
    outputs  = model(hidden, last_pos, mask)
    assert outputs[0].shape == (BATCH, SEQ, N), f"unexpected shape: {outputs[0].shape}"
    assert len(outputs) == 1 + 2 * ns.gpt_layers, f"unexpected output count: {len(outputs)}"
    print(f"  Prefill hidden_states : {outputs[0].shape}")
    print(f"  total outputs         : {len(outputs)} (1 + 2 x {ns.gpt_layers} layers)")

    # Decode: seq_len == 1
    hidden_dec   = torch.randn(BATCH, 1, N)
    last_pos_dec = torch.tensor([5]).expand(BATCH)
    outputs_dec  = model(hidden_dec, last_pos_dec, mask)
    assert outputs_dec[0].shape == (BATCH, 1, N), f"unexpected shape: {outputs_dec[0].shape}"
    print(f"  Decode  hidden_states : {outputs_dec[0].shape}")

    # aliases
    instance = NeuronGPTInstance(ns)
    instance.load_module()
    _, aliases = instance.get()
    assert len(aliases) == 2 * ns.gpt_layers, f"unexpected alias count: {len(aliases)}"
    print(f"  aliases count         : {len(aliases)} (expected {2 * ns.gpt_layers})")

    print("[OK] modeling_gpt.py\n")


def test_model_wrapper_gpt():
    print("[TEST] model_wrapper_gpt.py")

    prefill = ModelWrapperGPTPrefill(ns, NeuronGPTInstance)
    [(hidden, last_pos, mask)] = prefill.input_generator()
    assert hidden.shape == (BATCH, SEQ, N)
    assert mask.shape   == (BATCH, SEQ)
    print(f"  Prefill hidden_states : {hidden.shape}")
    print(f"  Prefill last_pos      : {last_pos.tolist()}")

    decode = ModelWrapperGPTDecode(ns, NeuronGPTInstance)
    [(hidden_d, last_pos_d, mask_d)] = decode.input_generator()
    assert hidden_d.shape == (BATCH, 1, N)
    print(f"  Decode  hidden_states : {hidden_d.shape}")
    print(f"  Decode  last_pos      : {last_pos_d.tolist()}")

    print("[OK] model_wrapper_gpt.py\n")


def test_application_gpt():
    print("[TEST] application_gpt.py")

    app = NeuronApplicationXTTSv2GPT("/tmp/test_model", ns)
    assert type(app.prefill_app).__name__ == "NeuronApplicationXTTSv2GPTPrefill"
    assert type(app.decode_app).__name__  == "NeuronApplicationXTTSv2GPTDecode"
    pw = app.prefill_app.models[0]
    dw = app.decode_app.models[0]
    print(f"  prefill ModelWrapper tag : {pw.tag}")
    print(f"  decode  ModelWrapper tag : {dw.tag}")

    # compile/load は stub なのでメッセージを出力して終了
    app.compile()
    app.load()

    sd = _make_zero_state_dict(ns)
    # per layer: ln1(2) + ln2(2) + query(2) + key(2) + value(2) + out(2) + up_proj(2) + down_proj(2) = 16
    assert len(sd) == ns.gpt_layers * 16, f"unexpected state_dict size: {len(sd)}"
    print(f"  state_dict keys : {len(sd)}")

    print("[OK] application_gpt.py\n")


if __name__ == "__main__":
    print("=" * 60)
    print("XTTSv2 NxD Inference - CPU Smoke Test")
    print("(Neuron SDK not required)")
    print("=" * 60)
    print()

    test_modeling_gpt()
    test_model_wrapper_gpt()
    test_application_gpt()

    print("=" * 60)
    print("[OK] All smoke tests passed")
    print("=" * 60)
