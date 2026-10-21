"""Generates the default sample.pdf this demo ships with -- not committed as a
binary (see ../README.md's note on this), built on first run instead so it's
inspectable and reproducible from this source.

Three pages, content taken verbatim from the synthetic images used earlier in
this project's own OCR comparison (see /serverless/lambda-microvm-ocr's
sibling work): a plain paragraph, a table, and invoice-style mixed
kanji/digits text. Ground truth is written alongside as sample.ground_truth.json
so the demo UI can show "does this match what was typed in" rather than just
"here is some OCR output, trust it".

Needs a CJK-capable font to render the Japanese content. Tries a short list of
real paths (macOS's bundled Hiragino Kaku Gothic, Linux's Noto Sans CJK
package) and falls back to an English-only sample with no special font
requirements if none is found -- this should never block someone from running
the demo at all, just change what language the default sample is in.
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

CJK_FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",  # macOS (confirmed present on a current macOS install)
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Linux, `apt install fonts-noto-cjk`
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "C:\\Windows\\Fonts\\meiryo.ttc",  # Windows
]


def _find_cjk_font(size):
    for path in CJK_FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, size, index=0), path
    return None, None


def _page(size, draw_fn):
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    draw_fn(d)
    return img


def _japanese_pages(font):
    gt = {}

    def p1(d):
        lines = [
            "気象庁は21日、関東甲信地方で今年最初の木枯らし一号が",
            "観測されたと発表した。東京都心の最低気温は8.4度まで下がり、",
            "今シーズン最も冷え込んだ。気象台によると、来週にかけて",
            "朝晩の冷え込みが強まる見込みで、インフルエンザの流行にも",
            "注意が必要だとしている。",
        ]
        y = 30
        for line in lines:
            d.text((30, y), line, font=font, fill="black")
            y += 55
        gt["page1_paragraph"] = "\n".join(lines)

    def p2(d):
        rows = [
            ["品目", "数量", "単価", "金額"],
            ["コピー用紙A4", "10箱", "2,400円", "24,000円"],
            ["トナーカートリッジ", "3個", "8,900円", "26,700円"],
            ["USBメモリ32GB", "20個", "1,200円", "24,000円"],
            ["合計", "", "", "74,700円"],
        ]
        col_x, row_h, top = [30, 420, 560, 720], 60, 30
        for r in range(len(rows) + 1):
            d.line([(20, top + r * row_h), (880, top + r * row_h)], fill="black", width=2)
        for x in col_x + [880]:
            d.line([(x, top), (x, top + len(rows) * row_h)], fill="black", width=2)
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                d.text((col_x[c] + 8, top + r * row_h + 15), cell, font=font, fill="black")
        gt["page2_table"] = rows

    def p3(d):
        lines = [
            "請求書番号: INV-2026-10849",
            "発行日: 2026年10月21日",
            "お支払期限: 2026年11月20日",
            "請求金額合計: ¥128,450 (税込)",
            "振込先: みずほ銀行 渋谷支店 普通 1234567",
        ]
        y = 30
        for line in lines:
            d.text((30, y), line, font=font, fill="black")
            y += 50
        gt["page3_invoice"] = "\n".join(lines)

    pages = [_page((900, 400), p1), _page((900, 400), p2), _page((900, 300), p3)]
    return pages, gt


def _english_fallback_pages():
    gt = {}

    def p1(d):
        lines = [
            "No CJK-capable font was found on this machine, so this default",
            "sample is in English instead of Japanese -- indra-ocr itself has",
            "no trouble with Japanese, this is only a font availability issue",
            "in the script that generated this one sample file.",
            "Install a Japanese font (e.g. fonts-noto-cjk on Linux) and delete",
            "sample.pdf, then restart server.py to regenerate it in Japanese.",
        ]
        y = 30
        for line in lines:
            d.text((20, y), line, fill="black")
            y += 28
        gt["page1_note"] = "\n".join(lines)

    def p2(d):
        rows = [
            ["Item", "Qty", "Unit price", "Amount"],
            ["Printer paper A4", "10 boxes", "$16.00", "$160.00"],
            ["Toner cartridge", "3", "$59.00", "$177.00"],
            ["USB drive 32GB", "20", "$8.00", "$160.00"],
            ["Total", "", "", "$497.00"],
        ]
        col_x, row_h, top = [30, 360, 500, 650], 50, 30
        for r in range(len(rows) + 1):
            d.line([(20, top + r * row_h), (880, top + r * row_h)], fill="black", width=2)
        for x in col_x + [880]:
            d.line([(x, top), (x, top + len(rows) * row_h)], fill="black", width=2)
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                d.text((col_x[c] + 8, top + r * row_h + 12), cell, fill="black")
        gt["page2_table"] = rows

    pages = [_page((900, 220), p1), _page((900, 330), p2)]
    return pages, gt


def main(out_pdf_path: str) -> None:
    font, font_path = _find_cjk_font(28)
    if font:
        pages, gt = _japanese_pages(font)
        print(f"[make_sample_pdf] using CJK font: {font_path}")
    else:
        pages, gt = _english_fallback_pages()
        print("[make_sample_pdf] no CJK font found; writing an English-only sample instead")

    pages[0].save(out_pdf_path, save_all=True, append_images=pages[1:])
    gt_path = os.path.splitext(out_pdf_path)[0] + ".ground_truth.json"
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(gt, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else "sample.pdf")
