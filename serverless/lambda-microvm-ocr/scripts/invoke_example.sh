#!/usr/bin/env bash
# Example calls against a deployed stack's ApiEndpoint output. The first
# request to a fresh stack cold-starts the MicroVM (expect tens of seconds --
# see README.md "Cold start" for what that time is actually spent on);
# requests after that reuse the same suspended/resumed VM and should be fast.
set -euo pipefail

API_ENDPOINT="${1:?usage: invoke_example.sh <ApiEndpoint> <image-file> [format]}"
IMAGE_FILE="${2:?usage: invoke_example.sh <ApiEndpoint> <image-file> [format]}"
FORMAT="${3:-md}"

echo "[invoke_example] health check"
curl -sf "${API_ENDPOINT}/health"; echo

echo "[invoke_example] POST /ocr with inline base64 (no S3 involved)"
python3 - "$IMAGE_FILE" "$FORMAT" <<'PY' > /tmp/indra-ocr-request.json
import base64, json, sys
path, fmt = sys.argv[1], sys.argv[2]
with open(path, "rb") as f:
    b64 = base64.b64encode(f.read()).decode()
print(json.dumps({"content_b64": b64, "filename": path.split("/")[-1], "format": fmt}))
PY

time curl -sf -X POST "${API_ENDPOINT}/ocr" \
  -H 'Content-Type: application/json' \
  --data @/tmp/indra-ocr-request.json | python3 -m json.tool

rm -f /tmp/indra-ocr-request.json

cat <<'EOF'

[invoke_example] S3-ref mode looks like this instead (requires OcrBucketName
to have been set at deploy time, and the object already uploaded):

  curl -X POST "$API_ENDPOINT/ocr" -H 'Content-Type: application/json' -d '{
    "s3_bucket": "your-ocr-bucket", "s3_key": "inbox/page1.png",
    "s3_output_key": "results/page1.md", "format": "md"
  }'
EOF
