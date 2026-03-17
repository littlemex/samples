"""Stub implementations of BaseModelInstance and ModelWrapper."""


class BaseModelInstance:
    """Stub: base class for model instances.

    Subclasses implement load_module() and get().
    """

    def load_module(self):
        raise NotImplementedError

    def get(self, bucket_rank=None, **kwargs):
        raise NotImplementedError


class ModelWrapper:
    """Stub: base class for model wrappers.

    On Neuron this handles compilation, sharding, and tracing.
    In CPU stub mode it stores config and model_cls for subclass use.
    """

    def __init__(self, config, model_cls, tag=None, compiler_args=None, **kwargs):
        self.config = config
        self.neuron_config = config.neuron_config
        self.model_cls = model_cls
        self.tag = tag
        self.compiler_args = compiler_args
        self.model = None
        self.bucket_config = None

    def input_generator(self):
        raise NotImplementedError

    def get_model_instance(self):
        raise NotImplementedError

    def forward(self, *args, **kwargs):
        raise NotImplementedError
