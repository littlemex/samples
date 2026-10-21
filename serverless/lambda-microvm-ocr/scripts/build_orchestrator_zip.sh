#!/usr/bin/env bash
# Bundles the orchestrator Lambda: handler.py plus a current boto3 (the Lambda
# Python 3.12 runtime's built-in boto3/botocore predates the lambda-microvms
# service model -- see orchestrator/requirements.txt), uploaded to the key
# AWS::Lambda::Function's Code.S3Key points at.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
ARTIFACT_BUCKET="${1:?usage: build_orchestrator_zip.sh <artifact-bucket> [s3-key]}"
S3_KEY="${2:-lambda/orchestrator.zip}"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

python3 -m pip install -q --no-cache-dir --platform manylinux2014_aarch64 \
  --target "$BUILD_DIR" --implementation cp --python-version 3.12 --only-binary=:all: \
  -r "$ROOT/orchestrator/requirements.txt"
cp "$ROOT/orchestrator/handler.py" "$BUILD_DIR/"

ZIP_PATH="$BUILD_DIR/../orchestrator.zip"
(cd "$BUILD_DIR" && zip -rq "$ZIP_PATH" .)

echo "[build_orchestrator_zip] uploading to s3://${ARTIFACT_BUCKET}/${S3_KEY}"
aws s3 cp "$ZIP_PATH" "s3://${ARTIFACT_BUCKET}/${S3_KEY}" --only-show-errors
rm -f "$ZIP_PATH"
echo "[build_orchestrator_zip] done"
