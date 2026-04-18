# AWS 公式 vLLM Neuron DLC イメージを使用
FROM public.ecr.aws/neuron/pytorch-inference-vllm-neuronx:0.16.0-neuronx-py312-sdk2.29.0-ubuntu24.04

# 作業ディレクトリ
WORKDIR /workspace

# 環境変数
ENV NEURON_RT_LOG_LEVEL=INFO
ENV PATH=/opt/aws/neuron/bin:$PATH

# 検証スクリプトをコピー
COPY verify_installation.py /workspace/

# デフォルトのエントリーポイント
CMD ["/bin/bash"]

