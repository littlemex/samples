#!/usr/bin/env python3
"""SigV4-signed HTTP request against the IAM-authorized HTTP API.

The API's routes use AuthorizationType: AWS_IAM (see ../cfn/template.yaml) --
an unsigned request gets a 403 from API Gateway before it ever reaches the
orchestrator Lambda. This signs with whatever credentials boto3's default
chain finds (the same ones `aws` CLI commands in this shell would use), so the
caller's IAM identity needs execute-api:Invoke on the API's ARN.

Usage:
  python3 sigv4_request.py GET  https://<api-id>.execute-api.<region>.amazonaws.com/health
  python3 sigv4_request.py POST https://<api-id>.execute-api.<region>.amazonaws.com/ocr \
      --json-file request.json
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from urllib.parse import urlparse

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("method")
    ap.add_argument("url")
    ap.add_argument("--json-file")
    ap.add_argument("--region", default=None)
    a = ap.parse_args()

    body = b""
    if a.json_file:
        with open(a.json_file, "rb") as f:
            body = f.read()

    region = a.region or urlparse(a.url).netloc.split(".")[2]
    session = boto3.Session()
    creds = session.get_credentials()
    if creds is None:
        print("no AWS credentials found (check your shell's AWS env/profile)", file=sys.stderr)
        sys.exit(1)

    req = AWSRequest(method=a.method, url=a.url, data=body,
                      headers={"Content-Type": "application/json"} if body else {})
    SigV4Auth(creds, "execute-api", region).add_auth(req)
    prepared = req.prepare()

    urlreq = urllib.request.Request(a.url, data=body or None, method=a.method,
                                     headers=dict(prepared.headers))
    try:
        with urllib.request.urlopen(urlreq, timeout=280) as r:
            status, resp_body = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, resp_body = e.code, e.read()

    print(f"HTTP {status}", file=sys.stderr)
    try:
        print(json.dumps(json.loads(resp_body), indent=2, ensure_ascii=False))
    except ValueError:
        print(resp_body.decode(errors="replace"))
    sys.exit(0 if status < 400 else 1)


if __name__ == "__main__":
    main()
