"""Unit tests for the orchestrator's request validation -- the parts that run
before anything touches AWS. No credentials, no network, no MicroVM needed;
boto3.client(...) at import time does not itself make a network call, so the
module imports fine with dummy env vars.

Run from this directory: python3 -m pytest test_handler_validation.py
(or just: python3 -m unittest test_handler_validation.py)
"""
import json
import os
import sys
import unittest

os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("IMAGE_ARN", "arn:aws:lambda:us-east-1:aws:microvm-image:test")
os.environ.setdefault("IMAGE_VERSION", "1")
os.environ.setdefault("EXEC_ROLE_ARN", "arn:aws:iam::123456789012:role/test")
os.environ.setdefault("INGRESS_CONNECTOR",
                       "arn:aws:lambda:us-east-1:aws:network-connector:aws-network-connector:ALL_INGRESS")
os.environ.setdefault("SSM_PARAM_NAME", "/indra-ocr-microvm/current-microvm")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "orchestrator"))
import handler  # noqa: E402


class HandleOcrValidationTest(unittest.TestCase):
    def test_rejects_unknown_format(self):
        resp = handler.handle_ocr({"content_b64": "YQ==", "format": "pdf"})
        self.assertEqual(resp["statusCode"], 400)
        self.assertIn("format", json.loads(resp["body"])["error"])

    def test_rejects_missing_source(self):
        resp = handler.handle_ocr({"format": "md"})
        self.assertEqual(resp["statusCode"], 400)
        self.assertIn("s3_bucket", json.loads(resp["body"])["error"])

    def test_health_route(self):
        resp = handler.handler({"rawPath": "/health",
                                "requestContext": {"http": {"method": "GET"}}}, None)
        self.assertEqual(resp["statusCode"], 200)
        self.assertTrue(json.loads(resp["body"])["ok"])

    def test_unknown_route_404(self):
        resp = handler.handler({"rawPath": "/nope",
                                "requestContext": {"http": {"method": "GET"}}}, None)
        self.assertEqual(resp["statusCode"], 404)

    def test_ocr_route_requires_json_body(self):
        resp = handler.handler({"rawPath": "/ocr", "body": "not json",
                                "requestContext": {"http": {"method": "POST"}}}, None)
        self.assertEqual(resp["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()
