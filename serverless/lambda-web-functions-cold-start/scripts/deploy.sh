#!/usr/bin/env bash
# Builds the three Web Function packages and the prober, uploads them to a versioned
# bucket, deploys the stack, and restricts every Web Function to the CloudFront
# distribution. Rerunning it only creates new revisions for packages that changed.
#
# Usage:
#   export AWS_REGION=us-east-1
#   ./scripts/deploy.sh [project-name]
#
# Needs an AWS CLI release with the `lambda-web` commands (2.39 or later). Set AWS_CLI to
# point at a specific binary if the one on PATH is older.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
PROJECT="${1:-wf-coldstart}"
AWS="${AWS_CLI:-aws}"
AWS_REGION="${AWS_REGION:?set AWS_REGION=us-east-1 first}"
PAD_MB="${PAD_MB:-200}"
BUILD="$ROOT/build"

[ "$AWS_REGION" = "us-east-1" ] || { echo "deploy in us-east-1: Lambda@Edge functions must be created there" >&2; exit 2; }
"$AWS" lambda-web help >/dev/null 2>&1 || { echo "this AWS CLI has no lambda-web commands; set AWS_CLI to a 2.39+ binary" >&2; exit 2; }

echo "[deploy] artifact bucket stack"
"$AWS" cloudformation deploy --region "$AWS_REGION" --stack-name "$PROJECT-artifacts" \
  --template-file "$ROOT/cfn/artifacts.yaml" --parameter-overrides ProjectName="$PROJECT" --no-fail-on-empty-changeset
BUCKET=$("$AWS" cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$PROJECT-artifacts" \
  --query "Stacks[0].Outputs[?OutputKey=='ArtifactBucketName'].OutputValue" --output text)

echo "[deploy] building packages in $BUILD"
rm -rf "$BUILD" && mkdir -p "$BUILD/minimal" "$BUILD/express" "$BUILD/padded" "$BUILD/prober"
cp "$ROOT/app/minimal/index.js" "$BUILD/minimal/"
cp "$ROOT/app/minimal/index.js" "$BUILD/padded/"
# Incompressible filler: it has to be read off the package, never by the server.
# Seeded so the same PAD_MB gives the same bytes and does not force a new revision.
python3 -c "import random,sys; r=random.Random(20261029); sys.stdout.buffer.write(r.randbytes($PAD_MB*1024*1024))" > "$BUILD/padded/pad.bin"
cp "$ROOT/app/express/index.js" "$ROOT/app/express/package.json" "$ROOT/app/express/package-lock.json" "$BUILD/express/"
(cd "$BUILD/express" && npm ci --omit=dev --no-audit --no-fund --silent)
cp "$ROOT/prober/prober.py" "$BUILD/prober/"
for v in minimal express padded prober; do
  (cd "$BUILD/$v" && find . -exec touch -t 202601010000 {} + && zip -qrX "../$v.zip" .)
done

# Upload a package only when its bytes changed, and print the S3 version id to use.
upload() {
  local file="$1" key="$2" sum current
  sum=$(shasum -a 256 "$file" | cut -d' ' -f1)
  current=$("$AWS" s3api head-object --region "$AWS_REGION" --bucket "$BUCKET" --key "$key" \
    --query 'Metadata.sha256' --output text 2>/dev/null || true)
  if [ "$current" != "$sum" ]; then
    "$AWS" s3api put-object --region "$AWS_REGION" --bucket "$BUCKET" --key "$key" --body "$file" \
      --metadata sha256="$sum" --query VersionId --output text
  else
    "$AWS" s3api head-object --region "$AWS_REGION" --bucket "$BUCKET" --key "$key" --query VersionId --output text
  fi
}
echo "[deploy] uploading (unchanged packages are skipped)"
V_MIN=$(upload "$BUILD/minimal.zip" web/minimal.zip)
V_EXP=$(upload "$BUILD/express.zip" web/express.zip)
V_PAD=$(upload "$BUILD/padded.zip" web/padded.zip)
V_PRB=$(upload "$BUILD/prober.zip" prober/prober.zip)
ls -l "$BUILD"/*.zip

# EMBED_JWKS=1 writes the user pool's public keys into the Lambda@Edge code, so a cold
# edge function does not fetch them from Cognito on its first request. It needs the pool,
# so it takes effect from the second deploy on.
JWKS_PARAMS=()
if [ "${EMBED_JWKS:-0}" = "1" ]; then
  POOL_ID=$("$AWS" cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$PROJECT" \
    --query "Stacks[0].Outputs[?OutputKey=='UserPoolId'].OutputValue" --output text 2>/dev/null || true)
  if [ -n "$POOL_ID" ] && [ "$POOL_ID" != "None" ]; then
    JWKS=$(curl -fsS "https://cognito-idp.$AWS_REGION.amazonaws.com/$POOL_ID/.well-known/jwks.json")
    JWKS_PARAMS=(EdgeJwks="$JWKS" EdgeJwksHash="$(printf '%s' "$JWKS" | shasum -a 256 | cut -c1-16)")
    echo "[deploy] embedding the JWKS of $POOL_ID in the Lambda@Edge code"
  else
    echo "[deploy] EMBED_JWKS=1 ignored: the user pool does not exist yet; deploy once more after this" >&2
  fi
else
  JWKS_PARAMS=(EdgeJwks= EdgeJwksHash=none)
fi

echo "[deploy] main stack"
"$AWS" cloudformation deploy --region "$AWS_REGION" --stack-name "$PROJECT" \
  --template-file "$ROOT/cfn/template.yaml" --capabilities CAPABILITY_IAM --no-fail-on-empty-changeset \
  --parameter-overrides ProjectName="$PROJECT" ArtifactBucketName="$BUCKET" \
    MinimalVersionId="$V_MIN" ExpressVersionId="$V_EXP" PaddedVersionId="$V_PAD" ProberVersionId="$V_PRB" \
    ${SCHEDULE_RATE_MINUTES:+ScheduleRateMinutes=$SCHEDULE_RATE_MINUTES} ${SCHEDULE_STATE:+ScheduleState=$SCHEDULE_STATE} \
    "${JWKS_PARAMS[@]}"

out() { "$AWS" cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$PROJECT" \
  --query "Stacks[0].Outputs[?OutputKey=='$1'].OutputValue" --output text; }
DIST_ARN=$(out DistributionArn)

# The endpoints are IamAuth. This resource policy is what lets CloudFront (and only this
# distribution) invoke them; CloudFormation has no resource for it yet.
echo "[deploy] restricting each Web Function to $DIST_ARN"
for v in Minimal Express Padded; do
  fn_arn=$(out "${v}FunctionArn"); ep_arn=$(out "${v}EndpointArn")
  policy=$(printf '{"Version":"2012-10-17","Statement":[{"Sid":"AllowCloudFrontOAC","Effect":"Allow","Principal":{"Service":"cloudfront.amazonaws.com"},"Action":"lambda:InvokeWebFunctionEndpoint","Resource":"%s","Condition":{"StringEquals":{"aws:SourceArn":"%s"}}}]}' "$ep_arn" "$DIST_ARN")
  rev=$("$AWS" lambda-web get-resource-policy --region "$AWS_REGION" --resource-arn "$fn_arn" --query revisionId --output text 2>/dev/null || true)
  if [ -n "$rev" ] && [ "$rev" != "None" ]; then
    "$AWS" lambda-web put-resource-policy --region "$AWS_REGION" --resource-arn "$fn_arn" --policy "$policy" --revision-id "$rev" >/dev/null
  else
    "$AWS" lambda-web put-resource-policy --region "$AWS_REGION" --resource-arn "$fn_arn" --policy "$policy" >/dev/null
  fi
done

"$AWS" cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$PROJECT" --query 'Stacks[0].Outputs' --output table
