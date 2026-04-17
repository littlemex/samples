# Neuron DLC ベースイメージ（PyTorch 2.9.0 + Neuron SDK 2.29.0）
FROM 763104351884.dkr.ecr.us-west-2.amazonaws.com/pytorch-inference-neuronx:2.9.0-neuronx-py312-sdk2.29.0-ubuntu24.04

# タイムゾーン設定（インタラクティブプロンプト回避）
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# システムパッケージ更新
RUN apt-get update && apt-get upgrade -y && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# NxD Inference のインストール（Agent 調査結果に基づく正しい順序）
RUN pip install --upgrade pip && \
    pip install neuronx-distributed-inference==0.9.* \
    --extra-index-url https://pip.repos.neuron.amazonaws.com

# 作業ディレクトリ
WORKDIR /workspace

# 検証スクリプトをコピー（後で作成）
COPY verify_installation.py /workspace/

# 環境変数
ENV PATH=/opt/aws/neuron/bin:$PATH
ENV NEURON_RT_LOG_LEVEL=INFO
