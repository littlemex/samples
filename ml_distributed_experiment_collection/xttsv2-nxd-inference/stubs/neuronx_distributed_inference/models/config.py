"""Stub implementations of InferenceConfig and NeuronConfig."""

import torch


class NeuronConfig:
    """Stub: holds batch_size, tp_degree, torch_dtype."""

    def __init__(self, batch_size=1, tp_degree=2, torch_dtype=None, **kwargs):
        self.batch_size = batch_size
        self.tp_degree = tp_degree
        self.torch_dtype = torch_dtype or torch.float32


class InferenceConfig:
    """Stub: base config that stores neuron_config."""

    def __init__(self, neuron_config, *args, **kwargs):
        self.neuron_config = neuron_config

    @classmethod
    def get_neuron_config_cls(cls):
        return NeuronConfig

    def to_dict(self):
        return {
            "batch_size": self.neuron_config.batch_size,
            "tp_degree": self.neuron_config.tp_degree,
        }
