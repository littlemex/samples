"""ModelWrapper for NeuronGPTTransformer

Provides Prefill and Decode wrappers with appropriate input generation.
"""

import torch
from neuronx_distributed_inference.models.model_wrapper import ModelWrapper
from .modeling_gpt import NeuronGPTInstance


class ModelWrapperGPTPrefill(ModelWrapper):
    """ModelWrapper for GPT Prefill (full sequence).

    Prefill mode processes the full input sequence (prefix + initial tokens)
    and builds the KV cache.
    """

    def __init__(self, config, model_cls, **kwargs):
        super().__init__(config, model_cls, **kwargs)
        self.bucket_config = None  # No bucketing, fixed length

    def input_generator(self):
        """Generate sample inputs for Neuron compilation (Prefill mode).

        Returns:
            List of tuples: [(hidden_states, last_pos, mask)]
        """
        max_seq_len = self.config.max_seq_len  # 1081
        batch_size = self.neuron_config.batch_size
        n_state = self.config.gpt_n_model_channels  # 1024

        # Sample input: full sequence
        hidden_states = torch.randn(
            batch_size,
            max_seq_len,
            n_state,
            dtype=self.neuron_config.torch_dtype,
        )

        # last_pos: position of the last valid token (for cache scatter)
        # In Prefill, we process all tokens, so last_pos is seq_len - 1
        last_pos = torch.tensor([max_seq_len - 1], dtype=torch.int32).expand(batch_size)

        # mask: 1 for valid tokens, 0 for padding
        # For sample input, assume all valid
        mask = torch.ones(batch_size, max_seq_len, dtype=torch.int32)

        return [(hidden_states, last_pos, mask)]

    def get_model_instance(self):
        """Return NeuronGPTInstance"""
        return NeuronGPTInstance(self.config)

    def forward(self, *args, **kwargs):
        """Forward pass through the model"""
        return self.model(*args, **kwargs)


class ModelWrapperGPTDecode(ModelWrapper):
    """ModelWrapper for GPT Decode (single token).

    Decode mode processes one token at a time, using the existing KV cache.
    """

    def __init__(self, config, model_cls, **kwargs):
        super().__init__(config, model_cls, **kwargs)
        self.bucket_config = None  # No bucketing

    def input_generator(self):
        """Generate sample inputs for Neuron compilation (Decode mode).

        Returns:
            List of tuples: [(hidden_states, last_pos, mask)]
        """
        batch_size = self.neuron_config.batch_size
        n_state = self.config.gpt_n_model_channels  # 1024
        max_seq_len = self.config.max_seq_len  # 1081

        # Sample input: single token
        hidden_states = torch.randn(
            batch_size,
            1,  # Decode: 1 token at a time
            n_state,
            dtype=self.neuron_config.torch_dtype,
        )

        # last_pos: current position in the sequence (varies during generation)
        # For sample input, use a dummy value
        last_pos = torch.tensor([100], dtype=torch.int32).expand(batch_size)

        # mask: full mask (indicating valid positions in the cache)
        # In Decode, mask covers all positions up to last_pos
        mask = torch.ones(batch_size, max_seq_len, dtype=torch.int32)

        return [(hidden_states, last_pos, mask)]

    def get_model_instance(self):
        """Return NeuronGPTInstance"""
        return NeuronGPTInstance(self.config)

    def forward(self, *args, **kwargs):
        """Forward pass through the model"""
        return self.model(*args, **kwargs)


if __name__ == "__main__":
    import torch
    from types import SimpleNamespace

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
    )

    print("[TEST] ModelWrapperGPTPrefill.input_generator()")
    prefill = ModelWrapperGPTPrefill(ns, NeuronGPTInstance)
    [(hidden, last_pos, mask)] = prefill.input_generator()
    print(f"  hidden_states : {hidden.shape}")   # [1, 16, 64]
    print(f"  last_pos      : {last_pos}")        # tensor([15])
    print(f"  mask          : {mask.shape}")      # [1, 16]

    print("[TEST] ModelWrapperGPTDecode.input_generator()")
    decode = ModelWrapperGPTDecode(ns, NeuronGPTInstance)
    [(hidden, last_pos, mask)] = decode.input_generator()
    print(f"  hidden_states : {hidden.shape}")   # [1, 1, 64]  (single token)
    print(f"  last_pos      : {last_pos}")        # tensor([100])
    print(f"  mask          : {mask.shape}")      # [1, 16]  (full cache mask)

    print("[OK] model_wrapper_gpt.py smoke test passed")
