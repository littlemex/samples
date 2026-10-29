#!/usr/bin/env bash
# Deletes everything deploy.sh created.
#
# CloudFront removes the Lambda@Edge replicas only some time after the distribution is
# gone, and until then the edge function cannot be deleted. If the main stack ends in
# DELETE_FAILED on EdgeAuthFunction, wait an hour or so and run this script again.
#
# Usage: AWS_REGION=us-east-1 ./scripts/teardown.sh [project-name]
set -euo pipefail
PROJECT="${1:-wf-coldstart}"
AWS="${AWS_CLI:-aws}"
AWS_REGION="${AWS_REGION:?set AWS_REGION=us-east-1 first}"

"$AWS" cloudformation delete-stack --region "$AWS_REGION" --stack-name "$PROJECT"
"$AWS" cloudformation wait stack-delete-complete --region "$AWS_REGION" --stack-name "$PROJECT" || {
  echo "main stack did not finish deleting (usually the Lambda@Edge replicas); rerun later" >&2; exit 1; }

BUCKET=$("$AWS" cloudformation describe-stacks --region "$AWS_REGION" --stack-name "$PROJECT-artifacts" \
  --query "Stacks[0].Outputs[?OutputKey=='ArtifactBucketName'].OutputValue" --output text 2>/dev/null || true)
if [ -n "$BUCKET" ] && [ "$BUCKET" != "None" ]; then
  echo "[teardown] emptying $BUCKET (all object versions)"
  python3 - "$AWS" "$AWS_REGION" "$BUCKET" <<'PY'
import json, subprocess, sys
aws, region, bucket = sys.argv[1:]
while True:
    out = json.loads(subprocess.check_output([aws, "s3api", "list-object-versions", "--region", region,
                                              "--bucket", bucket, "--max-items", "1000", "--output", "json"]) or b"{}")
    objs = [{"Key": o["Key"], "VersionId": o["VersionId"]} for k in ("Versions", "DeleteMarkers") for o in out.get(k) or []]
    if not objs:
        break
    subprocess.check_call([aws, "s3api", "delete-objects", "--region", region, "--bucket", bucket,
                           "--delete", json.dumps({"Objects": objs, "Quiet": True})])
PY
fi
"$AWS" cloudformation delete-stack --region "$AWS_REGION" --stack-name "$PROJECT-artifacts"
"$AWS" cloudformation wait stack-delete-complete --region "$AWS_REGION" --stack-name "$PROJECT-artifacts"
echo "[teardown] done. Log groups created by Lambda itself (/aws/lambda/web/$PROJECT-*.local, /aws/lambda/us-east-1.$PROJECT-edge-auth in edge Regions) are not stack resources; delete them if you want."
