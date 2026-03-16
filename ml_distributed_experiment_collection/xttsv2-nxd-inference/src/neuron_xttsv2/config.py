"""XTTSv2 Inference Configuration for NxD Inference"""

from neuronx_distributed_inference.models.config import InferenceConfig, NeuronConfig


class XTTSv2InferenceConfig(InferenceConfig):
    """Configuration for XTTSv2 GPT model inference on Neuron.

    This config extends InferenceConfig to include XTTSv2-specific parameters.
    Only the GPT Transformer part is compiled for Neuron; other components
    (ConditioningEncoder, PerceiverResampler, HifiDecoder) run on CPU.

    Usage:
        neuron_config = NeuronConfig(batch_size=1, tp_degree=2, torch_dtype=torch.float32)
        config = XTTSv2InferenceConfig(neuron_config=neuron_config)
    """

    def __init__(self, neuron_config=None, *args, **kwargs):
        # InferenceConfig 0.8.x では neuron_config が第 1 引数
        if neuron_config is None:
            neuron_config = NeuronConfig()
        super().__init__(neuron_config, *args, **kwargs)

        # XTTSv2 GPT Model Architecture Parameters
        self.gpt_layers = 30              # Number of transformer layers
        self.gpt_n_model_channels = 1024  # Model dimension (d_model)
        self.gpt_n_heads = 16             # Number of attention heads

        # XTTSv2 Token Limits
        self.gpt_max_audio_tokens = 605   # Max audio (mel) tokens
        self.gpt_max_text_tokens = 402    # Max text tokens
        self.gpt_max_prompt_tokens = 70   # Max prompt tokens (conditioning)

        # Vocabulary Sizes
        self.gpt_num_audio_tokens = 8194  # Audio token vocabulary size
        self.gpt_num_text_tokens = 256    # Text token vocabulary size (BPE)

        # Audio Parameters
        self.gpt_code_stride_len = 1024   # DVAE hop size

        # Computed Parameters
        self.max_seq_len = (
            self.gpt_max_audio_tokens + 2 +    # mel tokens + start/stop
            self.gpt_max_text_tokens + 2 +     # text tokens + start/stop
            self.gpt_max_prompt_tokens         # prompt tokens
        )  # Total: 605 + 2 + 402 + 2 + 70 = 1081

        # Head Dimension
        self.head_dim = self.gpt_n_model_channels // self.gpt_n_heads  # 1024 / 16 = 64

        # MLP Intermediate Size
        self.intermediate_size = self.gpt_n_model_channels * 4  # 4096

        # XTTSv2 checkpoint path for weight loading via NxD sharding mechanism
        # Set this BEFORE calling NeuronApplicationXTTSv2GPT.load_weights()
        self.xttsv2_checkpoint_path = ""

    @classmethod
    def get_neuron_config_cls(cls):
        """Return the NeuronConfig class to use."""
        return NeuronConfig

    @classmethod
    def from_pretrained(cls, model_path, neuron_config=None, **kwargs):
        """Load config from pretrained XTTSv2 model.

        Args:
            model_path: Path to XTTSv2 checkpoint
            neuron_config: NeuronConfig instance
            **kwargs: Additional config overrides

        Returns:
            XTTSv2InferenceConfig instance
        """
        if neuron_config is None:
            neuron_config = NeuronConfig()
        return cls(neuron_config=neuron_config, **kwargs)

    def to_dict(self):
        """Convert config to dictionary."""
        config_dict = super().to_dict()
        config_dict.update({
            "gpt_layers": self.gpt_layers,
            "gpt_n_model_channels": self.gpt_n_model_channels,
            "gpt_n_heads": self.gpt_n_heads,
            "gpt_max_audio_tokens": self.gpt_max_audio_tokens,
            "gpt_max_text_tokens": self.gpt_max_text_tokens,
            "gpt_max_prompt_tokens": self.gpt_max_prompt_tokens,
            "gpt_num_audio_tokens": self.gpt_num_audio_tokens,
            "gpt_num_text_tokens": self.gpt_num_text_tokens,
            "gpt_code_stride_len": self.gpt_code_stride_len,
            "max_seq_len": self.max_seq_len,
            "head_dim": self.head_dim,
            "intermediate_size": self.intermediate_size,
        })
        return config_dict
