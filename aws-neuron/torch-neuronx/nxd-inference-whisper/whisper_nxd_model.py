"""
Whisper STT model with NxD Inference support.

This replaces the manual Forward Override implementation with AWS official
NeuronX Distributed Inference library for better performance and maintainability.
"""

import torch
import numpy as np
import scipy.signal
from pathlib import Path
from typing import Optional, Tuple, Dict, Any
from transformers import AutoProcessor

try:
    # Try to import from installed package first
    from neuronx_distributed_inference.models.config import NeuronConfig
    from neuronx_distributed_inference.models.whisper.modeling_whisper import (
        WhisperInferenceConfig,
        NeuronApplicationWhisper,
    )
    from neuronx_distributed_inference.utils.hf_adapter import load_pretrained_config
    NXD_AVAILABLE = True
except ImportError:
    # If not available, try to import from repo
    import sys
    from pathlib import Path as PathLib

    nxd_repo = PathLib("/tmp/neuronx-distributed-inference/src")
    if nxd_repo.exists():
        sys.path.insert(0, str(nxd_repo))
        try:
            from neuronx_distributed_inference.models.config import NeuronConfig
            from neuronx_distributed_inference.models.whisper.modeling_whisper import (
                WhisperInferenceConfig,
                NeuronApplicationWhisper,
            )
            from neuronx_distributed_inference.utils.hf_adapter import load_pretrained_config
            NXD_AVAILABLE = True
            print(f"✓ Using NxD Inference from repo: {nxd_repo}")
        except ImportError as e:
            NXD_AVAILABLE = False
            print(f"Warning: neuronx-distributed-inference not available: {e}")
    else:
        NXD_AVAILABLE = False
        print("Warning: neuronx-distributed-inference not available. NxD Inference mode disabled.")


class WhisperNxDModel:
    """
    Whisper STT model using NxD Inference.

    Features:
    - Tensor Parallelism (TP) support for multi-core inference
    - KV-Cache support for faster decoding
    - Simplified API compared to manual Forward Override
    - Official AWS support and maintenance

    Performance improvements over manual Forward Override:
    - TP=8: 4-6x speedup on encoder/decoder
    - KV-Cache: 2-3x speedup on decoding
    - Total: 5-8x expected speedup
    """

    def __init__(
        self,
        model_path: str,
        compiled_path: Optional[str] = None,
        batch_size: int = 1,
        tp_degree: int = 8,
        torch_dtype: torch.dtype = torch.float16,
        language: str = "ja",
        task: str = "transcribe",
        device_type: str = "neuron"
    ):
        """
        Initialize Whisper NxD model.

        Args:
            model_path: Path to HuggingFace Whisper model
            compiled_path: Path to save/load compiled model (if None, uses model_path + "_compiled")
            batch_size: Batch size for inference (default: 1)
            tp_degree: Tensor Parallelism degree (2, 4, 8, 16) - default: 8
            torch_dtype: Data type (default: torch.float16)
            language: Target language code (default: "ja")
            task: Task type ("transcribe" or "translate")
            device_type: Device type ("neuron", "cpu", or "gpu")
        """
        if not NXD_AVAILABLE and device_type == "neuron":
            raise RuntimeError(
                "NxD Inference not available. "
                "Install with: pip install neuronx-distributed-inference"
            )

        self.model_path = Path(model_path)
        self.compiled_path = Path(compiled_path) if compiled_path else (self.model_path.parent / f"{self.model_path.name}_compiled")
        self.batch_size = batch_size
        self.tp_degree = tp_degree
        self.torch_dtype = torch_dtype
        self.language = language
        self.task = task
        self.device_type = device_type

        # Model components
        self.neuron_model = None
        self.processor = None
        self.is_loaded = False
        self.is_compiled = False

    def compile(self):
        """
        Compile model for Neuron.

        This creates the NeuronApplicationWhisper instance and compiles it.
        Compilation takes 1-2 hours but only needs to be done once.
        """
        if self.device_type != "neuron":
            print(f"Skipping compilation for device type: {self.device_type}")
            return

        if not NXD_AVAILABLE:
            raise RuntimeError("NxD Inference not available")

        if self.is_compiled:
            print("Model already compiled")
            return

        print(f"\n🔧 Compiling Whisper model with NxD Inference...")
        print(f"  Model: {self.model_path}")
        print(f"  Compiled path: {self.compiled_path}")
        print(f"  TP degree: {self.tp_degree}")
        print(f"  Batch size: {self.batch_size}")
        print(f"  Dtype: {self.torch_dtype}")

        # Create NeuronConfig
        neuron_config = NeuronConfig(
            batch_size=self.batch_size,
            torch_dtype=self.torch_dtype,
            tp_degree=self.tp_degree,
        )

        # Create WhisperInferenceConfig
        inference_config = WhisperInferenceConfig(
            neuron_config,
            load_config=load_pretrained_config(str(self.model_path)),
        )

        # Create and compile model
        self.neuron_model = NeuronApplicationWhisper(
            str(self.model_path),
            config=inference_config
        )

        print(f"\n  Compiling... (this may take 1-2 hours)")
        self.compiled_path.mkdir(parents=True, exist_ok=True)
        self.neuron_model.compile(str(self.compiled_path))

        self.is_compiled = True
        print(f"  ✅ Compilation complete: {self.compiled_path}")

    def load(self):
        """Load compiled model from disk."""
        if self.is_loaded:
            return

        print(f"\n📦 Loading Whisper NxD model...")
        print(f"  Device: {self.device_type}")

        # Load processor
        print(f"  Loading processor...")
        self.processor = AutoProcessor.from_pretrained(str(self.model_path))
        print(f"    ✓ Processor loaded")

        if self.device_type == "neuron":
            if not NXD_AVAILABLE:
                raise RuntimeError("NxD Inference not available")

            # Check if compiled model exists
            if not self.compiled_path.exists():
                raise FileNotFoundError(
                    f"Compiled model not found: {self.compiled_path}\n"
                    f"Run compile() first to create compiled model."
                )

            # Create NeuronConfig
            neuron_config = NeuronConfig(
                batch_size=self.batch_size,
                torch_dtype=self.torch_dtype,
                tp_degree=self.tp_degree,
            )

            # Create WhisperInferenceConfig
            inference_config = WhisperInferenceConfig(
                neuron_config,
                load_config=load_pretrained_config(str(self.model_path)),
            )

            # Load compiled model
            print(f"  Loading compiled model from {self.compiled_path}...")
            self.neuron_model = NeuronApplicationWhisper(
                str(self.compiled_path),
                config=inference_config
            )
            self.neuron_model.load(str(self.compiled_path))
            print(f"    ✓ NxD Inference model loaded (TP={self.tp_degree})")

        else:
            # CPU/GPU fallback (using transformers directly)
            from transformers import WhisperForConditionalGeneration
            print(f"  Loading standard Whisper model...")
            self.neuron_model = WhisperForConditionalGeneration.from_pretrained(
                str(self.model_path)
            )
            if self.device_type == "gpu":
                self.neuron_model = self.neuron_model.cuda()
            print(f"    ✓ Model loaded on {self.device_type}")

        self.is_loaded = True
        print(f"  ✅ Model ready")

    def unload(self):
        """Unload model from memory."""
        if not self.is_loaded:
            return

        del self.neuron_model
        del self.processor

        self.neuron_model = None
        self.processor = None
        self.is_loaded = False

        if self.device_type == "gpu":
            torch.cuda.empty_cache()

    def infer(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000
    ) -> Tuple[str, Dict[str, float]]:
        """
        Run inference on audio data.

        Args:
            audio_data: Audio numpy array (mono, float32)
            sample_rate: Sample rate (default 16000 Hz)

        Returns:
            Tuple of (transcription, metrics_dict)
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Resample if needed
        if sample_rate != 16000:
            audio_data = scipy.signal.resample_poly(
                audio_data, 16000, sample_rate
            ).astype(np.float32)

        # Calculate audio duration for metrics
        audio_duration = len(audio_data) / 16000

        if self.device_type == "neuron":
            # Use NxD Inference transcribe() API
            # Note: transcribe() accepts numpy array directly
            result = self.neuron_model.transcribe(
                audio_data,  # numpy array (mono, float32)
                language=self.language,
                task=self.task,
                verbose=False
            )
            transcription = result['text']

        else:
            # CPU/GPU inference using transformers
            input_features = self.processor(
                audio_data,
                sampling_rate=16000,
                return_tensors="pt"
            ).input_features

            if self.device_type == "gpu":
                input_features = input_features.cuda()

            with torch.no_grad():
                predicted_ids = self.neuron_model.generate(
                    input_features,
                    language=self.language,
                    task=self.task,
                )

            transcription = self.processor.batch_decode(
                predicted_ids,
                skip_special_tokens=True
            )[0]

        # Metrics
        metrics = {
            'audio_duration': audio_duration,
        }

        return transcription, metrics

    def transcribe_file(self, audio_path: str, verbose: bool = False) -> Dict[str, Any]:
        """
        Transcribe audio file (convenience method).

        Args:
            audio_path: Path to audio file
            verbose: Print progress

        Returns:
            Dictionary with 'text' and metadata
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load() first.")

        # Load audio file first (avoid ffmpeg dependency)
        import soundfile as sf
        audio_data, sr = sf.read(audio_path)

        # Resample if needed
        if sr != 16000:
            audio_data = scipy.signal.resample_poly(
                audio_data, 16000, sr
            ).astype(np.float32)

        # Convert to mono if stereo
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)

        audio_data = audio_data.astype(np.float32)
        audio_duration = len(audio_data) / 16000

        if self.device_type == "neuron" and hasattr(self.neuron_model, 'transcribe'):
            # Use NxD Inference's transcribe with numpy array (no ffmpeg needed)
            result = self.neuron_model.transcribe(
                audio_data,  # Pass numpy array instead of path
                language=self.language,
                verbose=verbose
            )
            result['audio_duration'] = audio_duration
            return result
        else:
            # Use infer() for CPU/GPU
            transcription, metrics = self.infer(audio_data, sample_rate=16000)
            return {
                'text': transcription,
                'audio_duration': metrics['audio_duration']
            }

    def get_mode_string(self) -> str:
        """Get display string for current mode."""
        if self.device_type == "neuron":
            return f"NxD Inference (TP={self.tp_degree}, KV-Cache)"
        elif self.device_type == "gpu":
            return "GPU (CUDA)"
        else:
            return "CPU"
