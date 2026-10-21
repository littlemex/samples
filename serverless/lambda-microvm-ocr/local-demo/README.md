# Try Indra OCR locally, no AWS

The same OCR engine the MicroVM sidecar runs (`../microvm/sidecar.py`), with a
small browser UI, entirely on your own machine.

```bash
cd local-demo
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 server.py
```

Opens `http://localhost:8765` (or prints the URL if it can't open a browser
itself). The model loads in the background after the server starts -- the
page polls `/status` and unlocks once it's ready. First run downloads model
weights from Hugging Face and caches them under `~/.cache/huggingface`;
later runs are instant.

A default `sample.pdf` (3 pages: a Japanese paragraph, a table, and
invoice-style text) is generated on first run by `make_sample_pdf.py` if it
doesn't already exist -- not committed as a binary, so it's always built from
the source you can read. Click "サンプルPDFを実行" to OCR it without
providing any file of your own, or upload your own PDF/image with the second
form.

Needs a CJK-capable font to render the Japanese sample; it checks a short list
of real paths (macOS's bundled Hiragino Kaku Gothic, Linux's
`fonts-noto-cjk` package). No font found -> the sample is generated in
English instead, with a note explaining why, rather than failing outright.

## What this is not

No authentication, no HTTPS, binds `0.0.0.0` on port 8765 -- fine for
`localhost` on your own machine, not something to expose on a network. This
is the local-only counterpart to the AWS MicroVM deployment one directory up;
see `../README.md` for that one's `AWS_IAM`-authorized API if you want the
same engine reachable over the network instead.
