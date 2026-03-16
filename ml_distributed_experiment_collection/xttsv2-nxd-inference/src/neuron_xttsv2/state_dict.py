"""State Dict Conversion: GPT-2 (Coqui/HuggingFace) -> NeuronGPTTransformer"""

import torch


def split_qkv(state_dict, layer_idx, n_state=1024, prefix="h"):
    """Split GPT-2's c_attn (combined Q/K/V) into separate tensors.

    GPT-2 uses Conv1D which stores weights as [in_features, out_features]:
    - c_attn.weight: [n_state, 3*n_state]  (Conv1D convention)
    - c_attn.bias: [3*n_state]

    NeuronGPTTransformer uses ColumnParallelLinear (nn.Linear convention [out, in]).
    So we split along dim=1, then transpose each to convert Conv1D -> nn.Linear.

    Args:
        state_dict: State dictionary (will be modified in-place)
        layer_idx: Layer index
        n_state: Model dimension (default: 1024)
        prefix: Key prefix (default: "h" for GPT-2, "transformer.h" for full path)

    Returns:
        Modified state_dict
    """
    key_prefix = f"{prefix}.{layer_idx}.attn.c_attn"
    qkv_weight = state_dict.pop(f"{key_prefix}.weight")  # (n_state, 3*n_state) - Conv1D [in, out]
    qkv_bias = state_dict.pop(f"{key_prefix}.bias")      # (3*n_state,)

    # Conv1D stores [in, out]: split along dim=1 (output features)
    q_w, k_w, v_w = qkv_weight.split(n_state, dim=1)  # each: (n_state, n_state) [in, out]
    q_b, k_b, v_b = qkv_bias.split(n_state, dim=0)

    # Transpose: Conv1D [in, out] -> nn.Linear [out, in]
    # .contiguous() is required: NxD's shard_checkpoint uses view() which fails on non-contiguous tensors
    neuron_prefix = f"blocks.{layer_idx}.attn"
    state_dict[f"{neuron_prefix}.query.weight"] = q_w.T.contiguous()
    state_dict[f"{neuron_prefix}.query.bias"] = q_b.contiguous()
    state_dict[f"{neuron_prefix}.key.weight"] = k_w.T.contiguous()
    state_dict[f"{neuron_prefix}.key.bias"] = k_b.contiguous()
    state_dict[f"{neuron_prefix}.value.weight"] = v_w.T.contiguous()
    state_dict[f"{neuron_prefix}.value.bias"] = v_b.contiguous()

    return state_dict


def convert_coqui_to_neuron_state_dict(state_dict, config):
    """Convert Coqui TTS / HuggingFace GPT-2 state_dict to NeuronGPTTransformer format.

    Key transformations:
    - h.{i}.attn.c_attn -> blocks.{i}.attn.{query,key,value} (3-way split)
    - h.{i}.attn.c_proj -> blocks.{i}.attn.out
    - h.{i}.ln_1 -> blocks.{i}.ln_1
    - h.{i}.mlp.c_fc -> blocks.{i}.mlp.up_proj
    - h.{i}.mlp.c_proj -> blocks.{i}.mlp.down_proj
    - h.{i}.ln_2 -> blocks.{i}.ln_2

    Args:
        state_dict: GPT-2 state dictionary
        config: XTTSv2InferenceConfig

    Returns:
        Converted state dictionary for NeuronGPTTransformer
    """
    neuron_state_dict = {}
    n_layers = config.gpt_layers
    n_state = config.gpt_n_model_channels

    # Process each layer
    for i in range(n_layers):
        # Split c_attn into Q/K/V
        split_qkv(state_dict, i, n_state=n_state, prefix="h")

        # Attention output projection (Conv1D [in, out] -> nn.Linear [out, in])
        if f"h.{i}.attn.c_proj.weight" in state_dict:
            neuron_state_dict[f"blocks.{i}.attn.out.weight"] = state_dict.pop(f"h.{i}.attn.c_proj.weight").T.contiguous()
        if f"h.{i}.attn.c_proj.bias" in state_dict:
            neuron_state_dict[f"blocks.{i}.attn.out.bias"] = state_dict.pop(f"h.{i}.attn.c_proj.bias")

        # Layer norms
        if f"h.{i}.ln_1.weight" in state_dict:
            neuron_state_dict[f"blocks.{i}.ln_1.weight"] = state_dict.pop(f"h.{i}.ln_1.weight")
        if f"h.{i}.ln_1.bias" in state_dict:
            neuron_state_dict[f"blocks.{i}.ln_1.bias"] = state_dict.pop(f"h.{i}.ln_1.bias")
        if f"h.{i}.ln_2.weight" in state_dict:
            neuron_state_dict[f"blocks.{i}.ln_2.weight"] = state_dict.pop(f"h.{i}.ln_2.weight")
        if f"h.{i}.ln_2.bias" in state_dict:
            neuron_state_dict[f"blocks.{i}.ln_2.bias"] = state_dict.pop(f"h.{i}.ln_2.bias")

        # MLP (Conv1D [in, out] -> nn.Linear [out, in])
        if f"h.{i}.mlp.c_fc.weight" in state_dict:
            neuron_state_dict[f"blocks.{i}.mlp.up_proj.weight"] = state_dict.pop(f"h.{i}.mlp.c_fc.weight").T.contiguous()
        if f"h.{i}.mlp.c_fc.bias" in state_dict:
            neuron_state_dict[f"blocks.{i}.mlp.up_proj.bias"] = state_dict.pop(f"h.{i}.mlp.c_fc.bias")
        if f"h.{i}.mlp.c_proj.weight" in state_dict:
            neuron_state_dict[f"blocks.{i}.mlp.down_proj.weight"] = state_dict.pop(f"h.{i}.mlp.c_proj.weight").T.contiguous()
        if f"h.{i}.mlp.c_proj.bias" in state_dict:
            neuron_state_dict[f"blocks.{i}.mlp.down_proj.bias"] = state_dict.pop(f"h.{i}.mlp.c_proj.bias")

    # Copy over split Q/K/V from state_dict to neuron_state_dict
    for key in list(state_dict.keys()):
        if key.startswith("blocks."):
            neuron_state_dict[key] = state_dict.pop(key)

    return neuron_state_dict


def expand_state_dict(state_dict, config, tp_degree):
    """Expand (pad) attention heads if necessary for Tensor Parallelism.

    If n_heads is not divisible by tp_degree, we need to pad the weights
    to make them divisible.

    Args:
        state_dict: NeuronGPTTransformer state dictionary
        config: XTTSv2InferenceConfig
        tp_degree: Tensor parallelism degree

    Returns:
        Padded state dictionary
    """
    n_heads = config.gpt_n_heads
    head_dim = config.head_dim
    n_state = config.gpt_n_model_channels

    # Check if padding is needed
    if n_heads % tp_degree == 0:
        return state_dict  # No padding needed

    # Calculate padded dimensions
    n_padded_heads = ((n_heads + tp_degree - 1) // tp_degree) * tp_degree
    padded_d = head_dim * n_padded_heads

    # Pad Q/K/V projections and output projection
    for i in range(config.gpt_layers):
        for proj in ["query", "key", "value"]:
            # Pad weight: [n_state, n_state] -> [padded_d, n_state]
            weight_key = f"blocks.{i}.attn.{proj}.weight"
            if weight_key in state_dict:
                weight = state_dict[weight_key]  # (n_state, n_state)
                padding = torch.zeros((padded_d - n_state, n_state), dtype=weight.dtype, device=weight.device)
                state_dict[weight_key] = torch.cat([weight, padding], dim=0)

            # Pad bias: [n_state] -> [padded_d]
            bias_key = f"blocks.{i}.attn.{proj}.bias"
            if bias_key in state_dict:
                bias = state_dict[bias_key]  # (n_state,)
                padding = torch.zeros((padded_d - n_state,), dtype=bias.dtype, device=bias.device)
                state_dict[bias_key] = torch.cat([bias, padding], dim=0)

        # Pad output projection: [n_state, n_state] -> [n_state, padded_d]
        out_weight_key = f"blocks.{i}.attn.out.weight"
        if out_weight_key in state_dict:
            weight = state_dict[out_weight_key]  # (n_state, n_state)
            padding = torch.zeros((n_state, padded_d - n_state), dtype=weight.dtype, device=weight.device)
            state_dict[out_weight_key] = torch.cat([weight, padding], dim=1)

    return state_dict


def load_gpt_weights_from_xttsv2(xtts_checkpoint_path, config, tp_degree=1):
    """Load GPT weights from XTTSv2 checkpoint and convert to Neuron format.

    Args:
        xtts_checkpoint_path: Path to XTTSv2 checkpoint (.pth file)
        config: XTTSv2InferenceConfig
        tp_degree: Tensor parallelism degree

    Returns:
        Converted state dictionary for NeuronGPTTransformer
    """
    # Load XTTSv2 checkpoint
    # weights_only=False: coqui/XTTS-v2 の .pth には XttsConfig オブジェクトが含まれるため必要
    checkpoint = torch.load(xtts_checkpoint_path, map_location="cpu", weights_only=False)

    # Extract GPT state dict (usually under "gpt" or "model.gpt.gpt" key)
    if "model" in checkpoint:
        gpt_state_dict = checkpoint["model"]
    elif "state_dict" in checkpoint:
        gpt_state_dict = checkpoint["state_dict"]
    else:
        gpt_state_dict = checkpoint

    # Filter only GPT transformer weights (h.{i}.*)
    gpt_transformer_dict = {}
    for key, value in gpt_state_dict.items():
        if "gpt.gpt.h." in key:
            # Remove "gpt.gpt." prefix
            new_key = key.replace("gpt.gpt.", "")
            gpt_transformer_dict[new_key] = value
        elif key.startswith("h."):
            gpt_transformer_dict[key] = value

    # Convert to Neuron format
    neuron_state_dict = convert_coqui_to_neuron_state_dict(gpt_transformer_dict, config)

    # Expand if TP requires padding
    if tp_degree > 1:
        neuron_state_dict = expand_state_dict(neuron_state_dict, config, tp_degree)

    return neuron_state_dict
