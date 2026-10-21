#!/usr/bin/env bash
# Example calls against a deployed stack's ApiEndpoint output. Both routes
# require AuthorizationType: AWS_IAM (see ../cfn/template.yaml) -- a plain
# curl gets 403 before it reaches Lambda, so every call here is SigV4-signed
# with sigv4_request.py using whatever credentials this shell's AWS CLI would
# use. The caller's IAM identity needs execute-api:Invoke on the API's ARN.
#
# The first request to a fresh stack cold-starts the MicroVM (expect tens of
# seconds -- see README.md "Cold start" for what that time is actually spent
# on); requests after that reuse the same suspended/resumed VM and should be
# fast.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_ENDPOINT="${1:?usage: invoke_example.sh <ApiEndpoint> <image-file> [format]}"
IMAGE_FILE="${2:?usage: invoke_example.sh <ApiEndpoint> <image-file> [format]}"
FORMAT="${3:-md}"

echo "[invoke_example] health check (signed)"
python3 "$HERE/sigv4_request.py" GET "${API_ENDPOINT}/health"

echo "[invoke_example] POST /ocr with inline base64 (no S3 involved, signed)"
python3 - "$IMAGE_FILE" "$FORMAT" <<'PY' > /tmp/indra-ocr-request.json
import base64, json, sys
path, fmt = sys.argv[1], sys.argv[2]
with open(path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()
print(json.dumps({"content_b64": b64, "filename": path.split("/")[-1], "format": fmt}))
PY

time python3 "$HERE/sigv4_request.py" POST "${API_ENDPOINT}/ocr" --json-file /tmp/indra-ocr-request.json
rm -f /tmp/indra-ocr-request.json

echo
echo "[invoke_example] an UNSIGNED request should be rejected before it reaches Lambda:"
curl -s -o /dev/null -w 'plain curl, no SigV4: HTTP %{http_code} (expect 403)\n' "${API_ENDPOINT}/health"

cat <<'EOF'

[invoke_example] S3-ref mode looks like this instead (requires OcrBucketName
to have been set at deploy time, and the object already uploaded):

  echo '{"s3_bucket":"your-ocr-bucket","s3_key":"inbox/page1.png",
         "s3_output_key":"results/page1.md","format":"md"}' > /tmp/s3-req.json
  python3 sigv4_request.py POST "$API_ENDPOINT/ocr" --json-file /tmp/s3-req.json
EOF
