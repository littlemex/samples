#!/usr/bin/env bash
# Deploys the Indra OCR MicroVM stack. Order matters: the artifact zips must
# exist in S3 before `cloudformation deploy` creates AWS::Lambda::MicrovmImage
# / AWS::Lambda::Function, because CloudFormation cannot author S3 object
# *contents* -- it can only reference objects that are already there.
#
# Usage:
#   export AWS_REGION=us-east-1          # MicroVMs' region availability varies; check first
#   ./deploy.sh <artifact-bucket-name> [stack-name] [ocr-bucket-name]
#
# ocr-bucket-name is optional: set it only if you plan to call /ocr with
# {s3_bucket,s3_key} instead of {content_b64}.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

ARTIFACT_BUCKET="${1:?usage: deploy.sh <artifact-bucket-name> [stack-name] [ocr-bucket-name]}"
STACK_NAME="${2:-indra-ocr-microvm}"
OCR_BUCKET="${3:-}"
AWS_REGION="${AWS_REGION:?set AWS_REGION first}"

if ! aws s3api head-bucket --bucket "$ARTIFACT_BUCKET" --region "$AWS_REGION" 2>/dev/null; then
  echo "[deploy] creating artifact bucket $ARTIFACT_BUCKET"
  if [ "$AWS_REGION" = "us-east-1" ]; then
    aws s3api create-bucket --bucket "$ARTIFACT_BUCKET" --region "$AWS_REGION"
  else
    aws s3api create-bucket --bucket "$ARTIFACT_BUCKET" --region "$AWS_REGION" \
      --create-bucket-configuration LocationConstraint="$AWS_REGION"
  fi
fi

"$HERE/build_microvm_zip.sh" "$ARTIFACT_BUCKET"
"$HERE/build_orchestrator_zip.sh" "$ARTIFACT_BUCKET"

aws cloudformation deploy \
  --region "$AWS_REGION" \
  --stack-name "$STACK_NAME" \
  --template-file "$ROOT/cfn/template.yaml" \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      ArtifactBucketName="$ARTIFACT_BUCKET" \
      OcrBucketName="$OCR_BUCKET"

aws cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs' --output table
