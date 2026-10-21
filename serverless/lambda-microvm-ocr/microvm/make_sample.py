"""Build-time helper: writes a tiny sample image baked into the MicroVM image.

Its only job is to give the /validate lifecycle hook something to run OCR on so
the real detect -> recognize -> reading-order pipeline gets exercised before the
platform snapshots the VM (see sidecar.py's `hook("validate", ...)` and the
cold-start note in ../README.md). The text content is irrelevant; PIL's built-in
bitmap font is enough and keeps the image free of an extra font package.
"""
import sys

from PIL import Image, ImageDraw


def main(out_path: str) -> None:
    img = Image.new("RGB", (420, 120), "white")
    d = ImageDraw.Draw(img)
    d.text((10, 10), "Indra OCR prewarm sample 12345", fill="black")
    d.text((10, 40), "exercise detect / recognize / order", fill="black")
    img.save(out_path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/opt/indra-ocr/sample.png")
