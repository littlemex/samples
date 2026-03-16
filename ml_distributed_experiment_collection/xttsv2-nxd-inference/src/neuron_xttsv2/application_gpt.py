"""NeuronApplicationXTTSv2GPT: High-level interface for GPT Transformer on Neuron

Architecture (Whisper pattern):
  NeuronApplicationXTTSv2GPTPrefill  (NeuronApplicationBase) -- 1 ModelWrapper
  NeuronApplicationXTTSv2GPTDecode   (NeuronApplicationBase) -- 1 ModelWrapper
  NeuronApplicationXTTSv2GPT         (coordinator)           -- routes forward()

NeuronApplicationBase stores a single self.traced_model (torch.jit.ScriptModule).
Indexing with self.traced_model[0] / [1] does NOT work.
Each Application owns exactly one ModelWrapper, so self.traced_model is valid.
"""

import os
import torch
from neuronx_distributed_inference.models.application_base import NeuronApplicationBase
from .config import XTTSv2InferenceConfig
from .modeling_gpt import NeuronGPTTransformer
from .model_wrapper_gpt import ModelWrapperGPTPrefill, ModelWrapperGPTDecode
from .state_dict import load_gpt_weights_from_xttsv2


def _build_compiler_args(config):
    """Build Neuron compiler arguments for GPT-2 Transformer."""
    args = "--model-type=transformer"
    args += " --tensorizer-options='--enable-ccop-compute-overlap --cc-pipeline-tiling-factor=2'"
    if config.neuron_config.torch_dtype == torch.float32:
        args += " --auto-cast=none"
    return args


def _make_zero_state_dict(config):
    """Create a zero-initialized state dict for NeuronGPTTransformer in FULL (non-TP-split) format.

    NeuronApplicationBase.shard_checkpoint() expects FULL-size weights as input
    and splits them across TP ranks internally.
    ColumnParallelLinear/RowParallelLinear would create already-split weights if
    we instantiate the model while parallel_state is active, causing double-splitting.
    We therefore build the state dict manually with full shapes.

    KV-Cache parameters (cache_k, cache_v) are managed by the aliases mechanism
    and are intentionally EXCLUDED here.
    """
    n = config.gpt_n_model_channels  # 1024
    n4 = n * 4                       # 4096
    n_layer = config.gpt_layers

    sd = {}
    for i in range(n_layer):
        p = f"blocks.{i}"
        # LayerNorm (not split across TP)
        sd[f"{p}.ln_1.weight"] = torch.ones(n)
        sd[f"{p}.ln_1.bias"]   = torch.zeros(n)
        sd[f"{p}.ln_2.weight"] = torch.ones(n)
        sd[f"{p}.ln_2.bias"]   = torch.zeros(n)
        # Attention projections (ColumnParallelLinear: full output dim before TP split)
        for proj in ("query", "key", "value"):
            sd[f"{p}.attn.{proj}.weight"] = torch.zeros(n, n)
            sd[f"{p}.attn.{proj}.bias"]   = torch.zeros(n)
        # Output projection (RowParallelLinear: full shapes before TP split)
        sd[f"{p}.attn.out.weight"] = torch.zeros(n, n)
        sd[f"{p}.attn.out.bias"]   = torch.zeros(n)
        # MLP
        sd[f"{p}.mlp.up_proj.weight"]   = torch.zeros(n4, n)
        sd[f"{p}.mlp.up_proj.bias"]     = torch.zeros(n4)
        sd[f"{p}.mlp.down_proj.weight"] = torch.zeros(n, n4)
        sd[f"{p}.mlp.down_proj.bias"]   = torch.zeros(n)
    return sd


class NeuronApplicationXTTSv2GPTPrefill(NeuronApplicationBase):
    """NeuronApplicationBase for Prefill (full-sequence context encoding)."""

    _model_cls = NeuronGPTTransformer

    def __init__(self, model_path, config, *args, **kwargs):
        super().__init__(model_path, config, *args, **kwargs)
        self.models.append(ModelWrapperGPTPrefill(
            config=self.config,
            model_cls=self._model_cls,
            tag="GPTPrefill",
            compiler_args=_build_compiler_args(config),
        ))

    @classmethod
    def get_config_cls(cls):
        """Required by NeuronApplicationBase.__init__ when config=None."""
        return XTTSv2InferenceConfig

    @staticmethod
    def load_hf_model(model_path):
        return None

    @classmethod
    def get_state_dict(cls, model_name_or_path, config):
        """Return NeuronGPTTransformer state dict.

        Called by shard_checkpoint() during both compile() and load_weights().
        - compile() path: xttsv2_checkpoint_path is NOT set -> returns zeros.
          Zeros are used as placeholder shapes for shard layout computation.
        - load_weights() path: xttsv2_checkpoint_path IS set -> returns actual weights.
          NeuronApplicationXTTSv2GPT.load_weights() injects this path before calling here.

        NOTE: KV-Cache parameters (cache_k, cache_v) are intentionally excluded.
        Aliases manage them; including them would cause shard_checkpoint() shape mismatches.
        NOTE: Weights are built with full (pre-TP-split) shapes to avoid double-split.
        """
        ckpt_path = getattr(config, "xttsv2_checkpoint_path", "")
        if ckpt_path:
            return load_gpt_weights_from_xttsv2(ckpt_path, config, tp_degree=1)
        return _make_zero_state_dict(config)

    @staticmethod
    def convert_hf_to_neuron_state_dict(state_dict, config):
        return state_dict

    def forward(self, hidden_states, last_pos, mask):
        outputs = self.traced_model(hidden_states, last_pos, mask)
        return outputs[0] if isinstance(outputs, tuple) else outputs


class NeuronApplicationXTTSv2GPTDecode(NeuronApplicationBase):
    """NeuronApplicationBase for Decode (single-token autoregressive step)."""

    _model_cls = NeuronGPTTransformer

    def __init__(self, model_path, config, *args, **kwargs):
        super().__init__(model_path, config, *args, **kwargs)
        self.models.append(ModelWrapperGPTDecode(
            config=self.config,
            model_cls=self._model_cls,
            tag="GPTDecode",
            compiler_args=_build_compiler_args(config),
        ))

    @classmethod
    def get_config_cls(cls):
        """Required by NeuronApplicationBase.__init__ when config=None."""
        return XTTSv2InferenceConfig

    @staticmethod
    def load_hf_model(model_path):
        return None

    @classmethod
    def get_state_dict(cls, model_name_or_path, config):
        """Return NeuronGPTTransformer state dict (actual weights or zeros).

        See NeuronApplicationXTTSv2GPTPrefill.get_state_dict() for full contract.
        """
        ckpt_path = getattr(config, "xttsv2_checkpoint_path", "")
        if ckpt_path:
            return load_gpt_weights_from_xttsv2(ckpt_path, config, tp_degree=1)
        return _make_zero_state_dict(config)

    @staticmethod
    def convert_hf_to_neuron_state_dict(state_dict, config):
        return state_dict

    def forward(self, hidden_states, last_pos, mask):
        outputs = self.traced_model(hidden_states, last_pos, mask)
        return outputs[0] if isinstance(outputs, tuple) else outputs


class NeuronApplicationXTTSv2GPT:
    """Coordinator: routes forward() to Prefill or Decode Application.

    Directory layout under model_path:
        model_path/prefill/   -- NeuronApplicationXTTSv2GPTPrefill artifacts
        model_path/decode/    -- NeuronApplicationXTTSv2GPTDecode artifacts

    Usage:
        app = NeuronApplicationXTTSv2GPT(model_path, config)
        app.compile()               # compile both and save
        app.load()                  # load both from disk
        out = app(hidden, pos, mask)  # auto-routes prefill vs decode
    """

    def __init__(self, model_path, config):
        self.config = config
        self.model_path = model_path
        self.prefill_app = NeuronApplicationXTTSv2GPTPrefill(
            os.path.join(model_path, "prefill"), config
        )
        self.decode_app = NeuronApplicationXTTSv2GPTDecode(
            os.path.join(model_path, "decode"), config
        )

    def compile(self, compiled_model_path=None):
        """Compile both Prefill and Decode models for Neuron."""
        base = compiled_model_path or self.model_path
        print("[INFO] Compiling Prefill model...")
        self.prefill_app.compile(os.path.join(base, "prefill"))
        print("[INFO] Compiling Decode model...")
        self.decode_app.compile(os.path.join(base, "decode"))
        print(f"[INFO] Compilation complete. Models saved to {base}")

    def load(self, compiled_model_path=None, skip_warmup=False):
        """Load both compiled models from disk."""
        base = compiled_model_path or self.model_path
        print(f"[INFO] Loading compiled models from {base}...")
        self.prefill_app.load(os.path.join(base, "prefill"), skip_warmup=skip_warmup)
        self.decode_app.load(os.path.join(base, "decode"), skip_warmup=skip_warmup)
        print("[INFO] Models loaded successfully.")

    def load_weights(self, checkpoint_path, tp_degree=1):
        """Load XTTSv2 GPT weights into both compiled models.

        Uses NeuronApplicationBase.load_weights() which calls shard_checkpoint()
        to properly shard weights across TP ranks and inject via nxd_model.initialize().
        The checkpoint path is stored in config.xttsv2_checkpoint_path so that
        get_state_dict() can return the actual weights for sharding.
        """
        for app in (self.prefill_app, self.decode_app):
            if app.traced_model is None:
                raise RuntimeError("Model must be compiled or loaded before loading weights")

        # Inject checkpoint path so get_state_dict() returns actual weights
        self.config.xttsv2_checkpoint_path = checkpoint_path

        # Use NxD's proper weight loading mechanism (shard + inject via nxd_model.initialize)
        self.prefill_app.load_weights(os.path.join(self.model_path, "prefill"))
        self.decode_app.load_weights(os.path.join(self.model_path, "decode"))

    def sync_kv_cache_prefill_to_decode(self, prefix_len: int):
        """Prefill モデルの KV キャッシュを Decode モデルに転送する。

        Prefill 実行後、prefill モデルの KV キャッシュバッファには
        positions 0..prefix_len-1 に正しいコンテキストが格納される。
        padding positions（prefix_len..max_seq_len-1）には bias 由来の
        値が残るため、転送前にゼロクリアする。

        traced_model.nxd_model は TorchScript RecursiveScriptModule のため
        Python メソッド（read/write_to_neuron_buffer）は不可。
        代わりに TorchScript 属性として公開されている .state を使用する。
        .state は List[Dict[str, Tensor]] 形式 (インデックス=rank)。

        Args:
            prefix_len: 有効な prefix トークン数（padding 開始位置）
        """
        tp_degree = self.config.neuron_config.tp_degree
        n_layer = self.config.gpt_layers
        max_seq = self.config.max_seq_len

        prefill_state = self.prefill_app.traced_model.nxd_model.state
        decode_state = self.decode_app.traced_model.nxd_model.state

        for rank in range(tp_degree):
            for i in range(n_layer):
                for name in (f"blocks.{i}.attn.cache_k", f"blocks.{i}.attn.cache_v"):
                    src = prefill_state[rank][name]
                    dst = decode_state[rank][name]
                    # CPU へ移してマスク乗算（Neuron デバイステンソルの
                    # 非連続スライス操作を回避）
                    src_cpu = src.cpu()
                    if prefix_len < max_seq:
                        mask = torch.ones(max_seq, dtype=src_cpu.dtype)
                        mask[prefix_len:] = 0.0
                        src_cpu = src_cpu * mask.view(1, 1, -1, 1)
                    dst.copy_(src_cpu)

    def forward(self, hidden_states, last_pos, mask):
        """Route to Prefill (seq_len > 1) or Decode (seq_len == 1)."""
        if hidden_states.shape[1] > 1:
            return self.prefill_app(hidden_states, last_pos, mask)
        else:
            return self.decode_app(hidden_states, last_pos, mask)

    def __call__(self, *args, **kwargs):
        return self.forward(*args, **kwargs)
