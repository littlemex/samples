"""Stub implementations of ColumnParallelLinear and RowParallelLinear.

On Neuron these split weight matrices across TP ranks.
In CPU stub mode both behave as plain nn.Linear.
"""

import torch.nn as nn


class ColumnParallelLinear(nn.Linear):
    """Stub: ColumnParallelLinear -> nn.Linear (no TP split)."""

    def __init__(self, in_features, out_features, bias=True,
                 gather_output=True, dtype=None, **kwargs):
        super().__init__(in_features, out_features, bias=bias, dtype=dtype)


class RowParallelLinear(nn.Linear):
    """Stub: RowParallelLinear -> nn.Linear (no TP split)."""

    def __init__(self, in_features, out_features, bias=True,
                 input_is_parallel=False, dtype=None, **kwargs):
        super().__init__(in_features, out_features, bias=bias, dtype=dtype)
