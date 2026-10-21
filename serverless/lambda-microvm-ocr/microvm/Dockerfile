# Indra OCR (https://github.com/datalab-to/indra) running inside an AWS Lambda
# MicroVMs image. arm64: indra-ocr and every dependency it pulls in
# (opencv-python-headless, onnxruntime, numpy, pypdfium2) ship manylinux_aarch64
# wheels, and running indra-ocr under a genuine aarch64 Linux container (not
# emulated) correctly OCR'd a real image -- see ../README.md "Why arm64".
#
# The CodeArtifact zip this Dockerfile lives in is built by the platform at
# AWS::Lambda::MicrovmImage create/update time (see ../cfn/template.yaml);
# nothing about this FROM line is tied to the image's BaseImageArn
# (al2023-1) -- the aws-samples reference implementation this project's
# protocol details were taken from bases its own MicroVM image on a
# third-party container (ghcr.io/openclaw/openclaw), not an AWS base image.
FROM --platform=linux/arm64 python:3.12-slim

# libgl1/libglib2.0-0/libsm6/libxext6/libxrender1/libxcb1: opencv-python-headless
# still dlopen()s these at import time despite the "headless" name. Confirmed
# missing (ImportError: libxcb.so.1) and fixed with exactly this set while
# testing indra-ocr in a plain python:3.11-slim container.
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libxcb1 \
    && rm -rf /var/lib/apt/lists/*

ENV HF_HOME=/opt/hf-cache \
    INDRA_OCR_MODEL_DIR=/opt/indra-ocr/models \
    INDRA_OCR_THREADS=2 \
    PYTHONUNBUFFERED=1

RUN pip install --no-cache-dir indra-ocr==1.1.2 pillow

# Bake the model weights (det.onnx/rec.onnx/order.onnx/meta.json, a few MB --
# indra-ocr's own pitch is a 1M-parameter recognizer, 7M for the whole default
# pipeline) into the image at build time, so a running MicroVM makes no
# Hugging Face network call. model_dir() with no `path=` downloads (or reuses
# the HF cache) and returns that cache's snapshot directory; copying it flat
# into INDRA_OCR_MODEL_DIR makes the "local folder" lookup branch in
# indra_ocr.models.model_dir() succeed at runtime with zero network.
RUN python3 -c "\
import shutil; \
from indra_ocr.models import model_dir; \
src = model_dir(); \
print('downloaded model to', src); \
shutil.copytree(src, '/opt/indra-ocr/models', dirs_exist_ok=True)"

COPY sidecar.py make_sample.py /opt/indra-ocr/
RUN python3 /opt/indra-ocr/make_sample.py /opt/indra-ocr/sample.png

EXPOSE 8080
CMD ["python3", "/opt/indra-ocr/sidecar.py"]
