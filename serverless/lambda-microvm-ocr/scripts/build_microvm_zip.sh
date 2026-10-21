#!/usr/bin/env bash
# Zips the MicroVM build context (Dockerfile + sidecar.py + make_sample.py) and
# uploads it to the artifact bucket at the key AWS::Lambda::MicrovmImage's
# CodeArtifact.Uri points at. CloudFormation cannot author S3 object
# *contents*, so this upload has to happen before `aws cloudformation deploy`
# creates or updates that resource -- see deploy.sh.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
ARTIFACT_BUCKET="${1:?usage: build_microvm_zip.sh <artifact-bucket> [s3-key]}"
S3_KEY="${2:-microvm-images/indra-ocr.zip}"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

cp "$ROOT/microvm/Dockerfile" "$ROOT/microvm/sidecar.py" "$ROOT/microvm/make_sample.py" "$BUILD_DIR/"

ZIP_PATH="$BUILD_DIR/../indra-ocr-microvm.zip"
(cd "$BUILD_DIR" && zip -rq "$ZIP_PATH" .)

echo "[build_microvm_zip] uploading to s3://${ARTIFACT_BUCKET}/${S3_KEY}"
aws s3 cp "$ZIP_PATH" "s3://${ARTIFACT_BUCKET}/${S3_KEY}" --only-show-errors
rm -f "$ZIP_PATH"
echo "[build_microvm_zip] done"
