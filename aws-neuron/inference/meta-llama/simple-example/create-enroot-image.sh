#!/usr/bin/env bash
set -ex

# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

# AWS リージョンとアカウント設定
export AWS_REGION=${AWS_REGION:-us-west-2}
export AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# ECR ログイン
aws ecr get-login-password --region ${AWS_REGION} | \
    docker login --username AWS --password-stdin \
    763104351884.dkr.ecr.${AWS_REGION}.amazonaws.com

# 古い sqsh ファイルを削除
if [ -f neuron-inference.sqsh ] ; then
    echo "Removing old neuron-inference.sqsh"
    rm neuron-inference.sqsh
fi

# Docker イメージをビルド
echo "Building Docker image..."
docker build -t neuron-inference:latest -f Dockerfile .

# Enroot イメージに変換
echo "Converting to Enroot image..."
enroot import -o neuron-inference.sqsh dockerd://neuron-inference:latest

echo "Enroot image created: neuron-inference.sqsh"
ls -lh neuron-inference.sqsh
