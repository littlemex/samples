"""Orchestrator Lambda for the Indra OCR MicroVM sample.

A MicroVM has no public endpoint of its own -- the only way to reach one is
`boto3.client("lambda-microvms")` plus a per-call auth token minted with
create_microvm_auth_token(), proxied over HTTPS with two special headers
(X-aws-proxy-auth, X-aws-proxy-port). Every call in this file (run_microvm,
get_microvm, create_microvm_auth_token, the X-aws-proxy-* header proxy
pattern) is taken from AWS's own reference implementation --
https://github.com/aws-samples/sample-multi-tenant-ai-agents-on-lambda-microvm
(src/orchestrator/handler.py) -- which at the time this was written is the
only place outside AWS's internal docs where this protocol is written down.
This file is *not* a copy of that orchestrator: it drops the multi-tenant
DynamoDB registry, EFS, VPC/NAT, and Bedrock wiring that sample needs for a
stateful chat agent, because OCR is stateless and the model is baked into the
image (see ../microvm/Dockerfile) -- there is nothing for this workload to
persist between requests, and nothing inside the VM that needs internet or
VPC access at all. What's kept is the minimum: one MicroVM, remembered across
invocations in a single SSM parameter instead of a DynamoDB table, reused
while RUNNING or SUSPENDED (SUSPENDED auto-resumes on the next forwarded
request because idlePolicy.autoResumeEnabled=True in cold_start() below),
cold-started otherwise.

KNOWN LIMITATION (documented, not fixed here -- see ../README.md "What this
sample does not do"): two concurrent cold starts can race, because there is no
conditional-update lock on the SSM parameter the way the reference
implementation locks its DynamoDB item. Fine for a single-caller sample;
add the same conditional-update lock before using this under real concurrency.

Two ways to hand Indra OCR a file, both ending at the same /ocr call on the
VM's sidecar (see ../microvm/sidecar.py):
  - {"s3_bucket": "...", "s3_key": "...", "s3_output_key": "..." (optional)}
    The orchestrator (an ordinary Lambda function, not a MicroVM, so the
    normal S3 SDK/API is available to it) downloads the input and, if
    s3_output_key is given, uploads the OCR result back to S3.
  - {"content_b64": "...", "filename": "..."}
    Bytes travel in the API request/response body directly; nothing touches
    S3. Fits small images; API Gateway HTTP API caps request/response bodies
    at 10 MB.

Lambda "S3 Files" (a function's native /mnt-style filesystem view of an S3
bucket) was asked about for this design and is explicitly NOT available on a
MicroVM: AWS's own design notes for the reference implementation list it as a
"Lambda-function-only feature -- no MicroVM API surface exposes [it]"
(docs/design/storage-options.md in the same reference repo). The S3 access
above happens at the orchestrator (a normal Lambda function, where S3 Files
would in fact be usable) and reaches the VM only as proxied HTTP bytes.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.request

import boto3

REGION = os.environ["AWS_REGION"]
IMAGE_ARN = os.environ["IMAGE_ARN"]
IMAGE_VERSION = os.environ["IMAGE_VERSION"]
EXEC_ROLE_ARN = os.environ["EXEC_ROLE_ARN"]
INGRESS_CONNECTOR = os.environ["INGRESS_CONNECTOR"]
SSM_PARAM_NAME = os.environ["SSM_PARAM_NAME"]
BASE_MEMORY_MIB = int(os.environ.get("BASE_MEMORY_MIB", "2048"))
OCR_PORT = 8080

mv = boto3.client("lambda-microvms", region_name=REGION)
ssm = boto3.client("ssm", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)


# ---------- VM registry (single VM; see the module docstring's known limitation) ----------
def _get_record() -> dict | None:
    try:
        v = ssm.get_parameter(Name=SSM_PARAM_NAME)["Parameter"]["Value"]
        return json.loads(v)
    except ssm.exceptions.ParameterNotFound:
        return None


def _put_record(rec: dict) -> None:
    ssm.put_parameter(Name=SSM_PARAM_NAME, Value=json.dumps(rec),
                       Type="String", Overwrite=True)


def _mv_state(microvm_id: str) -> str | None:
    try:
        return mv.get_microvm(microvmIdentifier=microvm_id).get("state")
    except Exception:  # noqa: BLE001 -- treat any lookup failure as "gone"
        return None


def mint_token(microvm_id: str) -> str:
    r = mv.create_microvm_auth_token(
        microvmIdentifier=microvm_id, expirationInMinutes=55,
        allowedPorts=[{"port": OCR_PORT}])
    return r["authToken"]["X-aws-proxy-auth"]


def call_vm(endpoint: str, path: str, token: str, method="GET", body=None, timeout=120):
    url = f"https://{endpoint}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"X-aws-proxy-auth": token, "X-aws-proxy-port": str(OCR_PORT),
               "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()


def cold_start() -> dict:
    r = mv.run_microvm(
        imageIdentifier=IMAGE_ARN, imageVersion=IMAGE_VERSION,
        executionRoleArn=EXEC_ROLE_ARN,
        ingressNetworkConnectors=[INGRESS_CONNECTOR],
        # No egressNetworkConnectors: the model is baked into the image (see
        # ../microvm/Dockerfile) and this workload makes no outbound calls of
        # its own, so there is nothing for a custom VPC egress connector to do.
        idlePolicy={"autoResumeEnabled": True, "maxIdleDurationSeconds": 900,
                    "suspendedDurationSeconds": 3600},
        maximumDurationInSeconds=28800,
    )
    microvm_id, endpoint = r["microvmId"], r["endpoint"]

    for _ in range(120):
        if _mv_state(microvm_id) == "RUNNING":
            break
        time.sleep(1)
    else:
        raise RuntimeError(f"microvm {microvm_id} did not reach RUNNING")

    token = mint_token(microvm_id)
    for _ in range(60):
        try:
            st, body = call_vm(endpoint, "/health", token, timeout=10)
            if st == 200 and json.loads(body).get("ready"):
                break
        except Exception:  # noqa: BLE001 -- sidecar/model not up yet, keep polling
            pass
        time.sleep(1)
    else:
        raise RuntimeError(f"microvm {microvm_id} sidecar never became ready")

    rec = {"microvmId": microvm_id, "endpoint": endpoint}
    _put_record(rec)
    return rec


def ensure_vm() -> dict:
    """Two-branch decision, same shape as the reference implementation's
    ensure_vm(): alive (RUNNING or SUSPENDED, which auto-resumes on the next
    forwarded request) -> reuse; otherwise -> cold start."""
    rec = _get_record()
    if rec and _mv_state(rec["microvmId"]) in ("RUNNING", "SUSPENDED"):
        return rec
    return cold_start()


# ---------- request handling ----------
def _error(code: int, message: str) -> dict:
    return {"statusCode": code, "body": json.dumps({"error": message}),
            "headers": {"Content-Type": "application/json"}}


def _ok(payload: dict) -> dict:
    return {"statusCode": 200, "body": json.dumps(payload, ensure_ascii=False),
            "headers": {"Content-Type": "application/json"}}


def handle_ocr(req: dict) -> dict:
    fmt = req.get("format", "md")
    if fmt not in ("md", "text", "json"):
        return _error(400, f"format must be md, text or json, not {fmt!r}")

    if "s3_bucket" in req and "s3_key" in req:
        obj = s3.get_object(Bucket=req["s3_bucket"], Key=req["s3_key"])
        data = obj["Body"].read()
        filename = req.get("filename") or req["s3_key"].rsplit("/", 1)[-1]
    elif "content_b64" in req:
        data = base64.b64decode(req["content_b64"])
        filename = req.get("filename", "input.png")
    else:
        return _error(400, "provide either {s3_bucket,s3_key} or {content_b64}")

    rec = ensure_vm()
    token = mint_token(rec["microvmId"])  # fresh per call: VM lifetime (8h) outlives any cached token (<=55min)
    body = {
        "content_b64": base64.b64encode(data).decode(),
        "filename": filename,
        "format": fmt,
        "max_pages": req.get("max_pages", 0),
    }
    try:
        st, resp_body = call_vm(rec["endpoint"], "/ocr", token, "POST", body, timeout=280)
    except urllib.error.HTTPError as e:
        return _error(502, f"microvm /ocr returned {e.code}: {e.read()[:500]!r}")
    resp = json.loads(resp_body)

    if "s3_output_key" in req:
        out_bucket = req.get("s3_output_bucket", req.get("s3_bucket"))
        if not out_bucket:
            return _error(400, "s3_output_key given without s3_output_bucket or s3_bucket")
        s3.put_object(Bucket=out_bucket, Key=req["s3_output_key"],
                       Body=resp["result"].encode("utf-8"),
                       ContentType="application/json" if fmt == "json" else "text/plain")
        return _ok({"s3_output_bucket": out_bucket, "s3_output_key": req["s3_output_key"],
                    "format": fmt, "pages": resp.get("pages"), "elapsed_s": resp.get("elapsed_s")})

    return _ok({"result": resp["result"], "format": fmt,
                "pages": resp.get("pages"), "elapsed_s": resp.get("elapsed_s")})


def handler(event, context):
    raw_path = event.get("rawPath", "/")
    method = (event.get("requestContext", {}).get("http", {}) or {}).get("method", "GET")

    if raw_path == "/health":
        return _ok({"ok": True})

    if raw_path == "/ocr" and method == "POST":
        body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            body = base64.b64decode(body).decode()
        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            return _error(400, "body must be JSON")
        try:
            return handle_ocr(req)
        except Exception as e:  # noqa: BLE001 -- surface the real cause to the caller
            return _error(500, f"{type(e).__name__}: {e}")

    return _error(404, f"no route for {method} {raw_path}")
