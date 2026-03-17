"""Stub implementation of parallel_state.

On Neuron this manages tensor/pipeline parallel process groups.
In CPU stub mode TP degree is always 1 and parallel is never initialized.
"""


class _FakeGroup:
    def size(self):
        return 1


def model_parallel_is_initialized():
    return False


def get_tensor_model_parallel_group():
    return _FakeGroup()
