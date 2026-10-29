"""Cold-start prober for Lambda Web Functions.

Each run sends, per variant and in parallel, one request that is expected to be cold
(the Web Function has scaled to zero since the previous run) followed by WARM_REQUESTS
requests that should land on the environment the first one started. Every request is
timed in three parts on a fresh TLS connection:

  connect_ms  TCP + TLS handshake to CloudFront (or to the endpoint, on the direct path)
  ttfb_ms     request sent -> response headers received   (this is where a cold start shows)
  total_ms    connect + ttfb + body

One JSON line per request goes to the prober's log group; scripts/analyze.py reads them.

Paths
  cloudfront  Cognito access token -> CloudFront -> Lambda@Edge check -> OAC-signed origin request
  direct      the prober signs the request to the IamAuth endpoint itself (SigV4, service "lambda")
  alternate   cloudfront and direct on alternate scheduled runs

Modes
  probe  the scheduled measurement above
  burst  {"mode": "burst", "variant": "minimal", "concurrency": 100, "path": "direct"}:
         fire N requests at once, to see how many wait for new environments
"""

import base64
import concurrent.futures as cf
import hashlib
import http.client
import json
import os
import threading
import time
import urllib.parse
import urllib.request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

REGION = os.environ.get("AWS_REGION", "us-east-1")
CF_DOMAIN = os.environ["CF_DOMAIN"]
DIRECT = {
    "minimal": os.environ["DIRECT_MINIMAL"],
    "express": os.environ["DIRECT_EXPRESS"],
    "padded": os.environ["DIRECT_PADDED"],
}
TOKEN_URL = os.environ["TOKEN_URL"]
TOKEN_SCOPE = os.environ["TOKEN_SCOPE"]
CLIENT_SECRET_ARN = os.environ["CLIENT_SECRET_ARN"]
RATE_MINUTES = int(os.environ.get("RATE_MINUTES", "30"))
WARM_REQUESTS = 5
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

_session = boto3.Session()
_token = {"value": None, "exp": 0.0}
_token_lock = threading.Lock()
# One record per line: without the lock, concurrent prints from the burst threads ran
# together on one line and those records were lost to the JSON log filter.
_print_lock = threading.Lock()


def emit(rec):
    with _print_lock:
        print(json.dumps(rec), flush=True)


def access_token():
    """Cognito client-credentials token, cached until 5 minutes before it expires."""
    with _token_lock:
        return _access_token_locked()


def _access_token_locked():
    if _token["value"] and time.time() < _token["exp"] - 300:
        return _token["value"]
    secret = json.loads(
        _session.client("secretsmanager").get_secret_value(SecretId=CLIENT_SECRET_ARN)["SecretString"]
    )
    basic = base64.b64encode(f"{secret['clientId']}:{secret['clientSecret']}".encode()).decode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode({"grant_type": "client_credentials", "scope": TOKEN_SCOPE}).encode(),
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        body = json.loads(r.read())
    _token["value"], _token["exp"] = body["access_token"], time.time() + body["expires_in"]
    return _token["value"]


def headers_for(path, variant):
    """(host, request path, headers) for one request on the chosen path."""
    if path == "cloudfront":
        return CF_DOMAIN, f"/{variant}/probe", {"Authorization": f"Bearer {access_token()}"}
    host = DIRECT[variant]
    url = f"https://{host}/{variant}/probe"
    req = AWSRequest(method="GET", url=url, headers={"X-Amz-Content-SHA256": EMPTY_SHA256})
    SigV4Auth(_session.get_credentials().get_frozen_credentials(), "lambda", REGION).add_auth(req)
    return host, f"/{variant}/probe", dict(req.headers.items())


def timed_get(path, variant, run_id, seq, barrier=None):
    """One request on a fresh connection. With a barrier (burst mode) every thread
    finishes its TLS handshake first and then all send at the same moment."""
    host, rpath, headers = headers_for(path, variant)
    t0 = time.time()
    conn = http.client.HTTPSConnection(host, timeout=60)
    rec = {"type": "probe", "run": run_id, "variant": variant, "path": path, "seq": seq, "startMs": round(t0 * 1000, 1)}
    try:
        conn.connect()
        if barrier is not None:
            barrier.wait(timeout=60)
        t1 = time.time()
        rec["sendMs"] = round(t1 * 1000, 1)
        conn.request("GET", rpath, headers=headers)
        resp = conn.getresponse()
        t2 = time.time()
        raw = resp.read()
        t3 = time.time()
        rec.update(
            status=resp.status,
            connectMs=round((t1 - t0) * 1000, 2),
            ttfbMs=round((t2 - t1) * 1000, 2),
            totalMs=round((t3 - t0) * 1000, 2),
            requestId=resp.getheader("lambda-web-request-id"),
            pop=resp.getheader("x-amz-cf-pop"),
        )
        if resp.status == 200:
            body = json.loads(raw)
            rec["server"] = {k: body.get(k) for k in ("envId", "processStartMs", "moduleStartMs", "listenMs", "nowMs", "served")}
            # How old the serving environment was when the request was sent. A value of a
            # few seconds means this request started (or waited for) a new environment.
            rec["envAgeAtSendMs"] = round(t1 * 1000 - body["processStartMs"], 1)
        else:
            rec["body"] = raw[:300].decode("utf-8", "replace")
    except Exception as e:  # keep measuring the other variants
        rec.update(status=-1, error=f"{type(e).__name__}: {e}")
    finally:
        conn.close()
    emit(rec)
    return rec


def probe_variant(path, variant, run_id):
    first = timed_get(path, variant, run_id, 0)
    for i in range(1, WARM_REQUESTS + 1):
        timed_get(path, variant, run_id, i)
    return first


def handler(event, context):
    event = event or {}
    mode = event.get("mode", "probe")
    path = event.get("path", "alternate")
    if path == "alternate":
        path = "cloudfront" if int(time.time() // (RATE_MINUTES * 60)) % 2 == 0 else "direct"
    run_id = context.aws_request_id if context else str(time.time())

    if mode == "burst":
        variant, n = event.get("variant", "minimal"), int(event.get("concurrency", 50))
        if path == "cloudfront":
            access_token()  # fetch once before the threads start
        barrier = threading.Barrier(n)
        with cf.ThreadPoolExecutor(max_workers=n) as ex:
            recs = list(ex.map(lambda i: timed_get(path, variant, run_id, i, barrier), range(n)))
        ok = [r for r in recs if r.get("status") == 200]
        sends = [r["sendMs"] for r in recs if "sendMs" in r]
        ttfb = sorted(r["ttfbMs"] for r in ok)
        summary = {"type": "burstSummary", "run": run_id, "variant": variant, "path": path, "n": n,
                   "ok": len(ok), "environments": len({r["server"]["envId"] for r in ok}),
                   "waitedForNewEnv": sum(r["envAgeAtSendMs"] < 0 for r in ok),
                   "sendSpreadMs": round(max(sends) - min(sends), 1) if sends else None,
                   "ttfbP50": ttfb[len(ttfb) // 2] if ttfb else None, "ttfbMax": ttfb[-1] if ttfb else None}
        emit(summary)
        return summary

    variants = event.get("variants", list(DIRECT))
    with cf.ThreadPoolExecutor(max_workers=len(variants)) as ex:
        firsts = list(ex.map(lambda v: probe_variant(path, v, run_id), variants))
    return {"run": run_id, "path": path,
            "first": {r["variant"]: (r.get("status"), r.get("ttfbMs"), r.get("envAgeAtSendMs")) for r in firsts}}
