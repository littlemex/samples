"""HTTP sidecar that runs inside the Indra OCR MicroVM image.

Two jobs:

1. Answer the AWS Lambda MicroVMs lifecycle-hook protocol: the platform POSTs
   to ``/aws/lambda-microvms/runtime/v1/{ready,validate,run}`` on the port
   declared in the image's ``Hooks`` property (8080 here). That exact path
   prefix and the ready/validate/run hook names are not invented for this
   sample -- they are taken from AWS's own reference implementation,
   https://github.com/aws-samples/sample-multi-tenant-ai-agents-on-lambda-microvm
   (src/microvm/hooks.py), which is the only place this protocol is written
   down outside AWS's internal docs at the time this was written.

2. Serve /ocr: the orchestrator Lambda (see ../orchestrator/handler.py) proxies
   OCR requests here over the MicroVM's authenticated HTTP channel.

The OCR model is loaded ONCE, at process start, into a module-level Converter
and reused for every request. indra_ocr.convert_many() -- the library's own
CLI entry point -- reloads the model on every call, which is fine for a
one-shot CLI invocation but throws away the speedup a warm model gives inside
a long-lived process: a cold CLI call to indra-ocr takes ~1-3s dominated by
model/session init, while a warm, already-loaded Converter processes a page in
~0.1-0.2s (measured on an x86_64 EKS pod and confirmed on native arm64; see
../../README.md). Keeping _conv warm here is what makes paying for a MicroVM
that stays suspended-and-resumable, instead of a fresh container per request,
worth doing at all for a model this small.
"""
import base64
import json
import os
import tempfile
import threading
import time
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOOK_PREFIX = "/aws/lambda-microvms/runtime/v1/"
PORT = 8080

# Baked into the image by the Dockerfile (see ../README.md "Why the model is
# baked in"); no Hugging Face network call happens at runtime.
MODEL_DIR = os.environ.get("INDRA_OCR_MODEL_DIR", "/opt/indra-ocr/models")
THREADS = int(os.environ.get("INDRA_OCR_THREADS", "2"))
SAMPLE_IMAGE = "/opt/indra-ocr/sample.png"

_conv = None
_ready = False


def _load_converter() -> None:
    global _conv
    import indra_ocr

    _conv = indra_ocr.load(path=MODEL_DIR, threads=THREADS)
    print(f"[sidecar] model loaded from {MODEL_DIR} (threads={THREADS})", flush=True)


def _run_ocr(data: bytes, filename: str, fmt: str, max_pages: int = 0) -> dict:
    """OCR one file's bytes with the already-loaded converter.

    Mirrors indra_ocr.cli's own per-page formatting (md/text/json) so /ocr's
    output matches what `indra-ocr --format <fmt>` would print for the same
    input, modulo this being a single already-decoded file rather than a CLI
    argument list.
    """
    suffix = os.path.splitext(filename)[1] or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        chunks = []
        pages_meta = []
        for i, page in _conv.convert(f.name, max_pages or 0):
            pages_meta.append({"page": i, "source": page.source, "note": page.note})
            if fmt == "json":
                chunks.append(json.dumps({
                    "page": i, "source": page.source, "rotation": page.rotation,
                    "skew": page.skew, "vertical": page.vertical, "note": page.note,
                    "lines": [asdict(ln) for ln in page.lines],
                    "markdown": page.markdown, "blocks": page.blocks,
                    "timings": page.timings,
                }, ensure_ascii=False))
            elif fmt == "text":
                chunks.append(page.text)
            else:
                chunks.append(page.markdown if page.markdown is not None else page.text)
        sep = "\n" if fmt == "json" else "\n\n"
        return {"body": sep.join(chunks), "pages": pages_meta}


# ---------- MicroVM image lifecycle hooks ----------
def hook(name: str, body: bytes):
    """Answer one platform lifecycle hook. Returns (status_code, response_body)."""
    if name == "ready":
        # Gates the snapshot: the platform only captures disk+memory once this
        # answers 200, so a loaded model (and its demand-paged ONNX runtime
        # pages) gets baked into every future launch instead of re-paying
        # model init per VM.
        return (200, b'{"ready":true}') if _ready else (503, b'{"ready":false}')
    if name == "validate":
        # Runs on a throwaway VM restored FROM the ready snapshot; the platform
        # samples which pages this touches and prefetches exactly those on
        # every later launch. Must walk the real inference path, not just
        # import the module -- see sample.png / make_sample.py.
        try:
            if os.path.exists(SAMPLE_IMAGE):
                with open(SAMPLE_IMAGE, "rb") as f:
                    _run_ocr(f.read(), "sample.png", "text")
            return 200, b'{"prewarmed":true}'
        except Exception as e:  # noqa: BLE001 -- a failed prewarm must not fail the build
            print(f"[sidecar] prewarm failed (non-fatal): {type(e).__name__}: {e}", flush=True)
            return 200, b'{"prewarmed":false}'
    if name == "run":
        # No per-tenant state for a stateless OCR worker; nothing to do.
        return 200, b"{}"
    return 200, b"{}"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200 if _ready else 503, json.dumps({"ready": _ready}).encode())
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path.startswith(HOOK_PREFIX):
            name = self.path[len(HOOK_PREFIX):].strip("/")
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            try:
                code, payload = hook(name, body)
            except Exception as e:  # noqa: BLE001
                print(f"[sidecar] hook {name} raised {type(e).__name__}: {e}", flush=True)
                code, payload = 200, b"{}"
            self._send(code, payload)
            return

        if self.path == "/ocr":
            n = int(self.headers.get("Content-Length") or 0)
            try:
                req = json.loads(self.rfile.read(n) or b"{}")
                data = base64.b64decode(req["content_b64"])
                fmt = req.get("format", "md")
                filename = req.get("filename", "input.png")
                max_pages = int(req.get("max_pages", 0))
                if not _ready:
                    self._send(503, b'{"error":"model not loaded yet"}')
                    return
                t0 = time.time()
                out = _run_ocr(data, filename, fmt, max_pages)
                self._send(200, json.dumps({
                    "result": out["body"], "format": fmt, "pages": out["pages"],
                    "elapsed_s": round(time.time() - t0, 3),
                }, ensure_ascii=False).encode())
            except KeyError as e:
                self._send(400, json.dumps({"error": f"missing field: {e}"}).encode())
            except Exception as e:  # noqa: BLE001
                self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode())
            return

        self._send(404, b'{"error":"not found"}')

    def log_message(self, *a):  # noqa: D401 -- silence BaseHTTPRequestHandler's default access log
        pass


def _bootstrap() -> None:
    global _ready
    _load_converter()
    _ready = True


if __name__ == "__main__":
    # Load the model in the background so the server can start accepting
    # connections immediately; /health and /ready report not-ready until it's
    # actually done.
    threading.Thread(target=_bootstrap, daemon=True).start()
    print(f"[sidecar] listening on :{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
