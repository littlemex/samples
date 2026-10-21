#!/usr/bin/env python3
"""A tiny, dependency-light local UI for trying Indra OCR, no AWS involved.

Everything here is Python stdlib (http.server) plus indra-ocr and Pillow --
no Flask/FastAPI, no npm/Node, no CDN scripts in the page it serves. The point
is to let someone try the same OCR path the MicroVM sidecar uses
(../microvm/sidecar.py) without deploying anything to AWS.

Run:
  pip install -r requirements.txt
  python3 server.py            # http://localhost:8765

The model is loaded once at startup (same reason as the sidecar: indra-ocr's
own convert_many() reloads it per call, which throws away most of the speed a
warm model gives). The first run downloads model weights from Hugging Face
and caches them under ~/.cache/huggingface -- expect a short delay once, not
on every request.
"""
import base64
import json
import mimetypes
import os
import sys
import tempfile
import threading
import time
import webbrowser
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8765"))
SAMPLE_PDF = os.path.join(HERE, "sample.pdf")

_conv = None
_ready = False
_ready_error = None


def _load_converter():
    global _conv, _ready, _ready_error
    try:
        import indra_ocr
        _conv = indra_ocr.load(threads=int(os.environ.get("INDRA_OCR_THREADS", "2")))
        _ready = True
        print("[local-demo] model loaded", flush=True)
    except Exception as e:  # noqa: BLE001
        _ready_error = f"{type(e).__name__}: {e}"
        print(f"[local-demo] model load failed: {_ready_error}", flush=True)


def _ensure_sample_pdf():
    if os.path.exists(SAMPLE_PDF):
        return
    print("[local-demo] generating default sample.pdf ...", flush=True)
    sys.path.insert(0, HERE)
    import make_sample_pdf
    make_sample_pdf.main(SAMPLE_PDF)
    print(f"[local-demo] wrote {SAMPLE_PDF}", flush=True)


def run_ocr(data: bytes, filename: str, fmt: str, max_pages: int = 0) -> dict:
    suffix = os.path.splitext(filename)[1] or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        pages_out = []
        for i, page in _conv.convert(f.name, max_pages or 0):
            if fmt == "json":
                body = json.dumps({
                    "page": i, "source": page.source, "rotation": page.rotation,
                    "skew": page.skew, "vertical": page.vertical, "note": page.note,
                    "lines": [asdict(ln) for ln in page.lines],
                    "markdown": page.markdown, "blocks": page.blocks,
                    "timings": page.timings,
                }, ensure_ascii=False)
            elif fmt == "text":
                body = page.text
            else:
                body = page.markdown if page.markdown is not None else page.text
            pages_out.append({"page": i, "source": page.source, "note": page.note, "body": body})
        return {"pages": pages_out}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype="application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: str, ctype: str) -> None:
        with open(path, "rb") as f:
            data = f.read()
        self._send(200, data, ctype)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send_file(os.path.join(HERE, "index.html"), "text/html; charset=utf-8")
        elif self.path == "/sample.pdf":
            self._send_file(SAMPLE_PDF, "application/pdf")
        elif self.path == "/sample.ground_truth.json":
            gt_path = os.path.splitext(SAMPLE_PDF)[0] + ".ground_truth.json"
            if os.path.exists(gt_path):
                self._send_file(gt_path, "application/json")
            else:
                self._send(404, b'{"error":"no ground truth for this sample"}')
        elif self.path == "/status":
            self._send(200, json.dumps({"ready": _ready, "error": _ready_error}).encode())
        else:
            self._send(404, b'{"error":"not found"}')

    def do_POST(self):
        if self.path != "/ocr":
            self._send(404, b'{"error":"not found"}')
            return
        n = int(self.headers.get("Content-Length") or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
            if not _ready:
                self._send(503, json.dumps({"error": _ready_error or "model still loading"}).encode())
                return
            data = base64.b64decode(req["content_b64"])
            fmt = req.get("format", "md")
            filename = req.get("filename", "input.png")
            max_pages = int(req.get("max_pages", 0))
            t0 = time.time()
            out = run_ocr(data, filename, fmt, max_pages)
            out["format"] = fmt
            out["elapsed_s"] = round(time.time() - t0, 3)
            self._send(200, json.dumps(out, ensure_ascii=False).encode())
        except KeyError as e:
            self._send(400, json.dumps({"error": f"missing field: {e}"}).encode())
        except Exception as e:  # noqa: BLE001
            self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode())

    def log_message(self, *a):
        pass


def main():
    _ensure_sample_pdf()
    threading.Thread(target=_load_converter, daemon=True).start()
    url = f"http://localhost:{PORT}"
    print(f"[local-demo] serving {url} (model loads in the background, check /status)", flush=True)
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001 -- headless environments: just print the URL
        pass
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
