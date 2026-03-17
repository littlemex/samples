"""NeuronXTTSv2: XTTSv2 with NxD Inference GPT Transformer

This module provides the main NeuronXTTSv2 class that integrates the Neuron-compiled
GPT Transformer into the original XTTSv2 model without modifying upstream code.
"""

import os
import torch
import torch.nn as nn
from typing import Optional
from transformers.models.gpt2.modeling_gpt2 import GPT2PreTrainedModel
from transformers import GenerationMixin
from transformers.modeling_outputs import CausalLMOutputWithCrossAttentions

from .application_gpt import NeuronApplicationXTTSv2GPT
from .config import XTTSv2InferenceConfig


class NeuronGPT2InferenceModel(GPT2PreTrainedModel, GenerationMixin):
    _is_stateful = False
    """GPT2InferenceModel compatible wrapper for Neuron GPT Transformer.

    This class mimics the interface of GPT2InferenceModel from XTTSv2, but internally
    uses NeuronApplicationXTTSv2GPT for the Transformer computation.

    Key differences from standard GPT2InferenceModel:
    - KV-Cache is managed by NxD Inference (via aliases), not HuggingFace's past_key_values
    - Forward pass delegates Transformer computation to Neuron, embeddings/heads on CPU
    """

    def __init__(
        self,
        gpt_config,
        neuron_gpt_app,
        mel_pos_emb,
        mel_emb,
        final_norm,
        mel_head,
        kv_cache=True,
        gpt_ln_f=None,
        gpt_wpe=None,
    ):
        """
        Args:
            gpt_config: GPT-2 config (from XTTSv2)
            neuron_gpt_app: NeuronApplicationXTTSv2GPT instance
            mel_pos_emb: Positional embedding layer (from XTTSv2)
            mel_emb: Mel embedding layer (from XTTSv2)
            final_norm: Final layer norm (from XTTSv2 gpt_module.final_norm)
            mel_head: Mel prediction head (from XTTSv2)
            kv_cache: Whether to use KV cache (always True for Neuron)
            gpt_ln_f: GPT2Model's internal final norm (orig_gpt.ln_f).
                      CPU GPT2InferenceModel applies this BEFORE final_norm, so
                      both must be applied to match CPU output exactly.
            gpt_wpe: GPT2Model's positional embedding (orig_gpt.wpe).
                     CPU GPT2Model applies wpe(position_ids) to inputs_embeds even
                     when inputs_embeds is provided. Neuron must replicate this to
                     produce the same hidden states at each KV cache position.
        """
        super().__init__(gpt_config)
        self.main_input_name = "input_ids"
        self.neuron_gpt_app = neuron_gpt_app
        self.pos_embedding = mel_pos_emb
        self.embeddings = mel_emb
        self.final_norm = final_norm
        self.gpt_ln_f = gpt_ln_f
        self.gpt_wpe = gpt_wpe
        # Build lm_head matching CPU pipeline:
        # CPU: GPT2Model outputs hidden_state -> ln_f (inside GPT2Model) -> final_norm -> mel_head
        # Neuron: NeuronGPTTransformer outputs hidden_state (no ln_f) -> gpt_ln_f -> final_norm -> mel_head
        if gpt_ln_f is not None:
            self.lm_head = nn.Sequential(gpt_ln_f, final_norm, mel_head)
        else:
            self.lm_head = nn.Sequential(final_norm, mel_head)
        self.kv_cache = kv_cache

        # State management for autoregressive generation
        self.cached_prefix_emb = None
        self.is_prefill = True
        self.token_count = 0

    def store_prefix_emb(self, prefix_emb):
        """Store prefix embeddings and run Neuron Prefill to populate KV cache.

        Prefill app で prefix 全体を一括処理し、KV キャッシュを Decode app に転送する。
        89 ステップの逐次 Decode 処理と異なり、Prefill は一度の行列演算で
        全 prefix トークンを処理するため、FP16 累積誤差が発生しない。

        処理フロー:
          1. prefix_emb を max_seq_len に zero-padding
          2. Prefill app で一括実行（causal mask 付き attention）
          3. Prefill state（KV キャッシュ）を Decode state にコピー
          4. padding 位置（prefix_len..max_seq_len-1）をゼロクリア

        Args:
            prefix_emb: [batch_size, prefix_len, n_state]
        """
        self.cached_prefix_emb = prefix_emb
        actual_len = prefix_emb.shape[1]
        self.token_count = actual_len
        self.is_prefill = True

        batch_size = prefix_emb.shape[0]
        max_seq_len = self.neuron_gpt_app.config.max_seq_len
        neuron_dtype = self.neuron_gpt_app.config.neuron_config.torch_dtype
        n_state = prefix_emb.shape[2]

        # prefix_emb を max_seq_len に zero-padding
        padded = torch.zeros(batch_size, max_seq_len, n_state, dtype=neuron_dtype)
        padded[:, :actual_len, :] = prefix_emb[:, :actual_len, :].to(neuron_dtype)

        # last_pos: 最後の有効トークンの位置
        last_pos = torch.tensor([actual_len - 1], dtype=torch.int32).expand(batch_size)

        # mask: 有効位置のみ 1（padding 位置は 0）
        mask = torch.zeros(batch_size, max_seq_len, dtype=torch.int32)
        mask[:, :actual_len] = 1

        with torch.no_grad():
            # Prefill 一括実行: positions 0..actual_len-1 の KV キャッシュを構築
            self.neuron_gpt_app.prefill_app(padded, last_pos, mask)

        # Prefill KV キャッシュを Decode モデルに転送（padding 位置をゼロクリア）
        self.neuron_gpt_app.sync_kv_cache_prefill_to_decode(actual_len)
        # Decode モデルの KV キャッシュは positions 0..actual_len-1 に正しい値を持つ

    def forward(
        self,
        input_ids: Optional[torch.Tensor] = None,
        past_key_values: Optional[tuple] = None,
        attention_mask: Optional[torch.Tensor] = None,
        inputs_embeds: Optional[torch.Tensor] = None,
        **kwargs
    ):
        """Forward pass compatible with HuggingFace GenerationMixin.

        Args:
            input_ids: [batch_size, seq_len] - Token IDs (mel codes)
            past_key_values: Ignored (KV cache managed by aliases)
            attention_mask: [batch_size, seq_len] - Attention mask
            inputs_embeds: [batch_size, seq_len, n_state] - Pre-computed embeddings

        Returns:
            CausalLMOutputWithCrossAttentions-like object with:
            - logits: [batch_size, seq_len, vocab_size]
            - past_key_values: Dummy tuple (to indicate cache is used)
        """
        # Determine if Prefill or Decode based on input shape
        if inputs_embeds is not None:
            emb = inputs_embeds
            is_prefill = emb.shape[1] > 1
        elif input_ids is not None:
            is_prefill = input_ids.shape[1] > 1

            if is_prefill and self.cached_prefix_emb is not None:
                # First forward() call from HF generate(): input_ids is [batch, prefix_len+n_new].
                # The prefix context is already in the Decode model's KV cache (from
                # store_prefix_emb). We only need to process the new audio tokens
                # (everything after the prefix) using the Decode model sequentially.
                # This avoids calling the Prefill model, which has a separate KV cache
                # that would diverge from the Decode model's state.
                prefix_len = self.cached_prefix_emb.shape[1]
                gen_input_ids = input_ids[:, prefix_len:]  # [batch, n_new]
                n_new = gen_input_ids.shape[1]

                batch_size = gen_input_ids.shape[0]
                max_seq_len = self.neuron_gpt_app.config.max_seq_len
                neuron_dtype = self.neuron_gpt_app.config.neuron_config.torch_dtype
                all_hidden = []

                for j in range(n_new):
                    # audio_pos = 0-based index of the j-th new audio token
                    audio_pos = j  # token_count == prefix_len at start; j-th token is at audio_pos=j
                    tok_emb = self.embeddings(gen_input_ids[:, j:j+1])
                    tok_emb = tok_emb + self.pos_embedding.get_fixed_embedding(
                        audio_pos, gen_input_ids.device
                    )
                    # Write to position (prefix_len + j) in the KV cache.
                    # KV cache scatter happens BEFORE attention, so the current token can
                    # attend to itself (causal self-attention); include write_pos in mask.
                    write_pos = self.token_count
                    last_pos = torch.tensor([write_pos], dtype=torch.int32, device=tok_emb.device).expand(batch_size)
                    mask = torch.ones(batch_size, max_seq_len, dtype=torch.int32, device=tok_emb.device)
                    mask[:, write_pos + 1:] = 0
                    h = self.neuron_gpt_app.decode_app(
                        tok_emb.to(neuron_dtype),
                        last_pos,
                        mask
                    ).to(tok_emb.dtype)
                    all_hidden.append(h)
                    self.token_count += 1

                hidden_states = torch.cat(all_hidden, dim=1)
                lm_logits = self.lm_head(hidden_states)
                return CausalLMOutputWithCrossAttentions(
                    logits=lm_logits,
                    past_key_values=((None,),),
                )
            else:
                # Decode: single token
                emb = self.embeddings(input_ids)
                if self.cached_prefix_emb is not None:
                    # Add positional embedding at audio-token relative position.
                    # CPU XTTS uses pos = attention_mask.shape[1] - (prefix_len + 1),
                    # which equals the 0-based index of the current audio token.
                    # token_count == prefix_len+n_audio_so_far (including start_audio_token).
                    # The start_audio_token was written at audio_pos=0, so the next token
                    # after one Prefill step has audio_pos = token_count - prefix_len.
                    prefix_len = self.cached_prefix_emb.shape[1]
                    audio_pos = self.token_count - prefix_len
                    emb = emb + self.pos_embedding.get_fixed_embedding(
                        audio_pos, input_ids.device
                    )
                else:
                    emb = emb + self.pos_embedding(emb)
        else:
            raise ValueError("Either input_ids or inputs_embeds must be provided")

        # Prepare Neuron inputs for single-token Decode
        batch_size = emb.shape[0]
        max_seq_len = self.neuron_gpt_app.config.max_seq_len

        # Decode: write to position token_count (first free slot).
        # KV cache scatter happens BEFORE attention in modeling_gpt.py, so the current
        # token attends to itself (standard causal attention). Include write_pos in mask.
        write_pos = self.token_count
        last_pos = torch.tensor([write_pos], dtype=torch.int32, device=emb.device).expand(batch_size)
        mask = torch.ones(batch_size, max_seq_len, dtype=torch.int32, device=emb.device)
        mask[:, write_pos + 1:] = 0
        self.token_count += 1

        # Run Neuron Decode Transformer
        hidden_states = self.neuron_gpt_app.decode_app(
            emb.to(self.neuron_gpt_app.config.neuron_config.torch_dtype),
            last_pos,
            mask
        )

        # Convert back to original dtype
        hidden_states = hidden_states.to(emb.dtype)

        # Apply lm_head to get logits
        lm_logits = self.lm_head(hidden_states)

        return CausalLMOutputWithCrossAttentions(
            logits=lm_logits,
            past_key_values=((None,),),  # Dummy tuple to signal cache is used
        )

    def _validate_model_kwargs(self, model_kwargs):
        """Skip HF's strict kwargs validation (XTTS passes attention_mask we don't need)."""
        pass

    def prepare_inputs_for_generation(self, input_ids, past_key_values=None, **kwargs):
        """Prepare inputs for HuggingFace generation.

        Args:
            input_ids: [batch_size, seq_len]
            past_key_values: Ignored (managed by aliases)
            **kwargs: Additional arguments

        Returns:
            Dict with input_ids and past_key_values
        """
        # If past_key_values exists, only use last token
        if past_key_values is not None:
            input_ids = input_ids[:, -1].unsqueeze(-1)

        return {
            "input_ids": input_ids,
            "past_key_values": past_key_values,
        }


class NeuronXTTSv2:
    """XTTSv2 with Neuron-accelerated GPT Transformer.

    This class wraps the original XTTSv2 model and replaces the GPT Transformer
    with a Neuron-compiled version, while keeping all other components (embeddings,
    HifiDecoder, etc.) on CPU.

    Usage:
        # Create model
        config = XTTSv2InferenceConfig.from_pretrained(...)
        neuron_config = NeuronConfig(batch_size=1, tp_degree=2, torch_dtype=torch.float16)
        config.neuron_config = neuron_config

        model = NeuronXTTSv2(config, neuron_compiled_path="/path/to/compiled")

        # Compile (first time only)
        model.compile("/path/to/compiled")

        # Load compiled model
        model.load("/path/to/compiled")

        # Inference
        wav = model.inference(
            text="Hello world",
            language="en",
            gpt_cond_latent=cond_latent,
            speaker_embedding=speaker_emb,
        )
    """

    def __init__(self, config: XTTSv2InferenceConfig, neuron_compiled_path: str = None):
        """
        Args:
            config: XTTSv2InferenceConfig with neuron_config
            neuron_compiled_path: Path to compiled Neuron models (optional)
        """
        self.config = config

        # Create NeuronApplicationXTTSv2GPT
        self.gpt_neuron = NeuronApplicationXTTSv2GPT(
            model_path=neuron_compiled_path if neuron_compiled_path else "/tmp/neuron_xttsv2_gpt",
            config=config,
        )

        # Placeholder: In real implementation, we would load the full XTTSv2 model
        # and extract components like embeddings, HifiDecoder, etc.
        # For now, we mark them as None
        self.xtts_model = None  # Original XTTSv2 model (CPU)
        self.neuron_gpt_inference = None  # NeuronGPT2InferenceModel wrapper

    def compile(self, compiled_model_path: str):
        """Compile GPT Transformer for Neuron.

        Args:
            compiled_model_path: Path to save compiled models
        """
        print(f"[NeuronXTTSv2] Compiling GPT Transformer to {compiled_model_path}...")
        self.gpt_neuron.compile(compiled_model_path)
        print("[NeuronXTTSv2] Compilation complete.")

    def load(self, compiled_model_path: str):
        """Load compiled GPT Transformer from disk.

        Args:
            compiled_model_path: Path to compiled models
        """
        print(f"[NeuronXTTSv2] Loading compiled GPT Transformer from {compiled_model_path}...")
        self.gpt_neuron.load(compiled_model_path)
        print("[NeuronXTTSv2] Models loaded.")

    def load_xttsv2_checkpoint(self, checkpoint_path: str):
        """Load XTTSv2 checkpoint and apply weights.

        Args:
            checkpoint_path: Path to XTTSv2 .pth checkpoint
        """
        print(f"[NeuronXTTSv2] Loading XTTSv2 checkpoint from {checkpoint_path}...")

        # Load GPT weights into Neuron model
        tp_degree = self.config.neuron_config.tp_degree
        self.gpt_neuron.load_weights(checkpoint_path, tp_degree=tp_degree)

        # Load full XTTSv2 model for other components (CPU)
        # In real implementation, we would load embeddings, HifiDecoder, etc.
        # For now, this is a placeholder

        print("[NeuronXTTSv2] Checkpoint loaded.")

    def inference(
        self,
        text: str,
        language: str,
        gpt_cond_latent: torch.Tensor,
        speaker_embedding: torch.Tensor,
        **kwargs
    ):
        """Run inference to generate speech.

        Args:
            text: Input text
            language: Language code (e.g., "en", "ja")
            gpt_cond_latent: Conditioning latent from reference audio
            speaker_embedding: Speaker embedding
            **kwargs: Additional inference parameters

        Returns:
            Dict with "wav" key containing generated audio
        """
        # This is a placeholder. In real implementation, we would:
        # 1. Tokenize text
        # 2. Compute embeddings (CPU)
        # 3. Run GPT generation (Neuron)
        # 4. Run HifiDecoder (CPU)

        raise NotImplementedError(
            "Full inference pipeline not yet implemented. "
            "See Step 7 (E2E test) for a working example."
        )
