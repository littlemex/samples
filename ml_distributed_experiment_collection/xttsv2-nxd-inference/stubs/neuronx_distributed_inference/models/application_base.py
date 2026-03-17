"""Stub implementation of NeuronApplicationBase."""


class NeuronApplicationBase:
    """Stub: base class for Neuron applications.

    On Neuron this manages compilation, loading, weight sharding, and tracing.
    In CPU stub mode it provides the same attribute interface so subclass
    __init__ and class hierarchy can be verified without Neuron hardware.
    """

    def __init__(self, model_path, config, *args, **kwargs):
        self.model_path = model_path
        self.config = config
        self.models = []
        self.traced_model = None

    @classmethod
    def get_config_cls(cls):
        raise NotImplementedError

    @staticmethod
    def load_hf_model(model_path):
        raise NotImplementedError

    @classmethod
    def get_state_dict(cls, model_name_or_path, config):
        raise NotImplementedError

    @staticmethod
    def convert_hf_to_neuron_state_dict(state_dict, config):
        raise NotImplementedError

    def compile(self, output_dir=None):
        print(f"[STUB] compile() skipped (Neuron SDK not available) -> {output_dir or self.model_path}")

    def load(self, input_dir=None, skip_warmup=False):
        print(f"[STUB] load() skipped (Neuron SDK not available) -> {input_dir or self.model_path}")

    def load_weights(self, model_path=None):
        print(f"[STUB] load_weights() skipped (Neuron SDK not available) -> {model_path or self.model_path}")

    def forward(self, *args, **kwargs):
        raise NotImplementedError

    def __call__(self, *args, **kwargs):
        return self.forward(*args, **kwargs)
