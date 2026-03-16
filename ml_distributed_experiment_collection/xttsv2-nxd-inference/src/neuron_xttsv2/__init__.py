"""NxD Inference + XTTSv2 Integration

This package integrates XTTSv2 (Text-to-Speech model) with AWS Neuron's
NxD Inference library for efficient inference on AWS Inferentia2.
"""

from .config import XTTSv2InferenceConfig
from .neuron_xttsv2 import NeuronXTTSv2

__version__ = "0.1.0"

__all__ = [
    "XTTSv2InferenceConfig",
    "NeuronXTTSv2",
]
