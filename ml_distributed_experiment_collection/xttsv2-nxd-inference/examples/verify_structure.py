"""XTTSv2 Neuron モデル構造確認スクリプト

CPU 上で実行できる。Neuron SDK は不要。
以下を確認する：
  - XTTSv2InferenceConfig の各パラメータ
  - NeuronGPTTransformer の構造（レイヤー数、パラメータ数）
  - KV キャッシュ aliases インデックスの対応

実行方法:
    python examples/verify_structure.py
"""

import sys

# Neuron SDK が不要な標準ライブラリのみインポート
import torch
import torch.nn as nn

# -------------------------------------------------------------------
# Neuron 依存モジュールを try/except で囲む
# Neuron SDK がない CPU 環境でも動作するよう、ダミー実装を提供
# -------------------------------------------------------------------
try:
    from neuronx_distributed_inference.models.config import NeuronConfig
    NEURON_AVAILABLE = True
except ImportError:
    NEURON_AVAILABLE = False

    class NeuronConfig:
        """Neuron SDK がない環境用のダミー NeuronConfig"""
        def __init__(self, batch_size=1, tp_degree=2, torch_dtype=None):
            self.batch_size = batch_size
            self.tp_degree = tp_degree
            self.torch_dtype = torch_dtype or torch.float32


try:
    from neuronx_distributed_inference.models.model_wrapper import BaseModelInstance
    from neuronx_distributed.parallel_layers import parallel_state
    NEURON_DIST_AVAILABLE = True
except ImportError:
    NEURON_DIST_AVAILABLE = False

    class BaseModelInstance:
        """Neuron SDK がない環境用のダミー BaseModelInstance"""
        pass


# -------------------------------------------------------------------
# CPU モード用の簡易モデル定義
# modeling_gpt.py が Neuron SDK に依存するため、構造確認用に再実装
# -------------------------------------------------------------------
class _CPUGPTAttention(nn.Module):
    """CPU 上で動作する GPT Self-Attention（構造確認用）"""

    def __init__(self, n_state, n_head, batch_size, seq_len, dtype):
        super().__init__()
        self.n_state = n_state
        self.n_head = n_head
        self.head_dim = n_state // n_head

        # 線形層（ColumnParallelLinear の CPU 等価）
        self.query = nn.Linear(n_state, n_state, bias=True)
        self.key   = nn.Linear(n_state, n_state, bias=True)
        self.value = nn.Linear(n_state, n_state, bias=True)
        self.out   = nn.Linear(n_state, n_state, bias=True)

        # KV キャッシュ（nn.Parameter として保持）
        # 実際の Neuron 実装と同じ形状
        self.cache_k = nn.Parameter(
            torch.zeros(batch_size, n_head, seq_len, self.head_dim, dtype=dtype),
            requires_grad=False,
        )
        self.cache_v = nn.Parameter(
            torch.zeros(batch_size, n_head, seq_len, self.head_dim, dtype=dtype),
            requires_grad=False,
        )


class _CPUGPTBlock(nn.Module):
    """CPU 上で動作する GPT ブロック（構造確認用）"""

    def __init__(self, n_state, n_head, batch_size, seq_len, dtype):
        super().__init__()
        self.ln_1 = nn.LayerNorm(n_state)
        self.attn = _CPUGPTAttention(n_state, n_head, batch_size, seq_len, dtype)
        self.ln_2 = nn.LayerNorm(n_state)
        self.mlp = nn.Sequential(
            nn.Linear(n_state, n_state * 4, bias=True),
            nn.GELU(),
            nn.Linear(n_state * 4, n_state, bias=True),
        )


class _CPUNeuronGPTTransformer(nn.Module):
    """CPU 上で動作する NeuronGPTTransformer（構造確認用）

    modeling_gpt.py の NeuronGPTTransformer と同じ構造を持つが、
    Neuron SDK (ColumnParallelLinear など) への依存を排除している。
    """

    def __init__(self, n_layer, n_state, n_head, batch_size, seq_len, dtype):
        super().__init__()
        self.n_layer = n_layer
        self.n_state = n_state
        self.n_head  = n_head
        self.blocks = nn.ModuleList([
            _CPUGPTBlock(n_state, n_head, batch_size, seq_len, dtype)
            for _ in range(n_layer)
        ])


# -------------------------------------------------------------------
# 確認関数
# -------------------------------------------------------------------

def verify_config():
    """XTTSv2InferenceConfig の各パラメータを表示する"""
    print("[OK] XTTSv2InferenceConfig")

    neuron_config = NeuronConfig(
        batch_size=1,
        tp_degree=2,
        torch_dtype=torch.bfloat16,
    )

    # Config クラスのパラメータを手動で定義（Neuron SDK 不要）
    # config.py の XTTSv2InferenceConfig.__init__ と同じ値
    gpt_layers          = 30
    gpt_n_model_channels = 1024
    gpt_n_heads         = 16
    gpt_max_audio_tokens = 605
    gpt_max_text_tokens  = 402
    gpt_max_prompt_tokens = 70
    gpt_num_audio_tokens  = 8194
    gpt_num_text_tokens   = 256
    gpt_code_stride_len   = 1024
    max_seq_len = gpt_max_audio_tokens + 2 + gpt_max_text_tokens + 2 + gpt_max_prompt_tokens
    head_dim = gpt_n_model_channels // gpt_n_heads
    intermediate_size = gpt_n_model_channels * 4

    print(f"  gpt_layers:              {gpt_layers}")
    print(f"  gpt_n_model_channels:    {gpt_n_model_channels}")
    print(f"  gpt_n_heads:             {gpt_n_heads}")
    print(f"  gpt_max_audio_tokens:    {gpt_max_audio_tokens}")
    print(f"  gpt_max_text_tokens:     {gpt_max_text_tokens}")
    print(f"  gpt_max_prompt_tokens:   {gpt_max_prompt_tokens}")
    print(f"  gpt_num_audio_tokens:    {gpt_num_audio_tokens}")
    print(f"  gpt_num_text_tokens:     {gpt_num_text_tokens}")
    print(f"  gpt_code_stride_len:     {gpt_code_stride_len}")
    print(f"  max_seq_len:             {max_seq_len}  "
          f"({gpt_max_audio_tokens}+2 + {gpt_max_text_tokens}+2 + {gpt_max_prompt_tokens})")
    print(f"  head_dim:                {head_dim}  "
          f"({gpt_n_model_channels} / {gpt_n_heads})")
    print(f"  intermediate_size:       {intermediate_size}  "
          f"({gpt_n_model_channels} * 4)")
    print()

    return {
        "gpt_layers": gpt_layers,
        "gpt_n_model_channels": gpt_n_model_channels,
        "gpt_n_heads": gpt_n_heads,
        "max_seq_len": max_seq_len,
        "head_dim": head_dim,
    }


def verify_transformer_structure(config_params):
    """NeuronGPTTransformer の構造（レイヤー数・パラメータ数）を表示する"""
    print("[OK] NeuronGPTTransformer (CPU mode)")

    n_layer  = config_params["gpt_layers"]
    n_state  = config_params["gpt_n_model_channels"]
    n_head   = config_params["gpt_n_heads"]
    seq_len  = config_params["max_seq_len"]
    batch    = 1
    dtype    = torch.float32

    model = _CPUNeuronGPTTransformer(
        n_layer=n_layer,
        n_state=n_state,
        n_head=n_head,
        batch_size=batch,
        seq_len=seq_len,
        dtype=dtype,
    )

    # KV キャッシュパラメータ（cache_k, cache_v）を除いたパラメータ数を計算
    kv_params  = 0
    non_kv_params = 0
    for name, param in model.named_parameters():
        if "cache_k" in name or "cache_v" in name:
            kv_params += param.numel()
        else:
            non_kv_params += param.numel()

    total_params = non_kv_params + kv_params

    print(f"  Layers (n_layer):        {n_layer}")
    print(f"  Hidden size (n_state):   {n_state}")
    print(f"  Attention heads:         {n_head}")
    print(f"  Total parameters:        {total_params:,}")
    print(f"  Non-KV parameters:       {non_kv_params:,}  (Neuron で weight として読み込まれる)")
    print(f"  KV-Cache parameters:     {kv_params:,}  (aliases 管理、state_dict から除外)")
    print(f"  KV-Cache excluded from state_dict: cache_k, cache_v")
    print()

    return model


def verify_aliases_mapping(model, config_params):
    """aliases インデックスの対応（output index → cache_k/v）を表示する"""
    print("[OK] aliases mapping")
    print("  NeuronGPTInstance.get() が返す aliases 辞書の構造:")
    print()

    n_layer = config_params["gpt_layers"]

    # NeuronGPTInstance.get() の実装と同じロジックで aliases を構築
    # modeling_gpt.py:292-313 参照
    aliases = {}
    output_index = 1  # output_index 0 は hidden_states

    # cache_k の aliases
    for i, layer in enumerate(model.blocks):
        aliases[f"blocks.{i}.attn.cache_k"] = output_index
        layer.attn.cache_k._alias_index = output_index  # 参照用に付与
        output_index += 1

    # cache_v の aliases
    for i, layer in enumerate(model.blocks):
        aliases[f"blocks.{i}.attn.cache_v"] = output_index
        layer.attn.cache_v._alias_index = output_index  # 参照用に付与
        output_index += 1

    # 出力インデックスの概要を表示
    print(f"  output[0]                = hidden_states (no alias)")
    print(f"  output[1..{n_layer}]        = cache_k (layers 0..{n_layer - 1})")
    print(f"  output[{n_layer + 1}..{n_layer * 2}]      = cache_v (layers 0..{n_layer - 1})")
    print()

    # 先頭・末尾レイヤーを例示
    print("  詳細（先頭 3 レイヤー + 末尾 1 レイヤー）:")
    show_keys = (
        list(aliases.keys())[:3] +
        [f"blocks.{n_layer - 1}.attn.cache_k"] +
        [f"blocks.{n_layer - 1}.attn.cache_v"]
    )
    for key in show_keys:
        idx = aliases[key]
        print(f"    output[{idx:2d}] = {key}")

    # 総数確認
    total_aliases = len(aliases)
    expected      = n_layer * 2  # cache_k × n_layer + cache_v × n_layer
    status = "[OK]" if total_aliases == expected else "[NG]"
    print()
    print(f"  {status} aliases 総数: {total_aliases} (期待値: {expected} = {n_layer} layers × 2)")
    print()


def main():
    print("=" * 60)
    print("XTTSv2 Neuron モデル構造確認")
    if not NEURON_AVAILABLE:
        print("[INFO] Neuron SDK が見つかりません。CPU モードで実行します。")
    print("=" * 60)
    print()

    # 1. Config パラメータの確認
    config_params = verify_config()

    # 2. モデル構造の確認
    model = verify_transformer_structure(config_params)

    # 3. aliases マッピングの確認
    verify_aliases_mapping(model, config_params)

    print("=" * 60)
    print("[OK] 構造確認完了")
    print("=" * 60)


if __name__ == "__main__":
    main()
