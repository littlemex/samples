#!/usr/bin/env python3
"""
サンプル画像生成スクリプト

MIT License準拠のサンプル画像（レシート、メニュー、申込書、イベント情報）を生成します。
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import sys


def get_font(size: int):
    """
    フォントを取得（利用可能なものを試行）

    Args:
        size: フォントサイズ

    Returns:
        ImageFont
    """
    font_paths = [
        '/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
    ]

    for font_path in font_paths:
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            continue

    print(f"[WARNING] TrueTypeフォントが見つかりません。デフォルトフォントを使用します。")
    return ImageFont.load_default()


def generate_receipt(output_path: Path):
    """レシート画像を生成"""
    img = Image.new('RGB', (400, 500), color='white')
    draw = ImageDraw.Draw(img)

    font_title = get_font(24)
    font_body = get_font(18)

    # タイトル
    draw.text((150, 30), "お会計", fill='black', font=font_title)

    # 明細
    y = 100
    lines = [
        "商品A: ¥1,200",
        "商品B: ¥800",
        "",
        "小計: ¥2,000",
        "消費税(10%): ¥200",
        "合計: ¥2,200",
        "",
        "ありがとうございました"
    ]

    for line in lines:
        draw.text((50, y), line, fill='black', font=font_body)
        y += 40

    img.save(output_path)
    print(f"[OK] {output_path}")


def generate_menu(output_path: Path):
    """メニュー画像を生成"""
    img = Image.new('RGB', (500, 600), color='#FFF8DC')
    draw = ImageDraw.Draw(img)

    font_title = get_font(28)
    font_body = get_font(18)
    font_small = get_font(14)

    # タイトル
    draw.text((120, 30), "本日のメニュー", fill='#8B4513', font=font_title)

    # メニュー内容
    y = 120
    items = [
        ("ランチセットA: ¥980", "(ハンバーグ・ライス・サラダ・スープ)"),
        ("", ""),
        ("ランチセットB: ¥1,200", "(刺身定食・ご飯・味噌汁・小鉢)"),
        ("", ""),
        ("デザート: ¥300", "")
    ]

    for title, desc in items:
        if title:
            draw.text((50, y), title, fill='black', font=font_body)
            y += 35
        if desc:
            draw.text((70, y), desc, fill='gray', font=font_small)
            y += 30
        if not title and not desc:
            y += 20

    img.save(output_path)
    print(f"[OK] {output_path}")


def generate_form(output_path: Path):
    """申込書フォーム画像を生成"""
    img = Image.new('RGB', (600, 500), color='white')
    draw = ImageDraw.Draw(img)

    font_title = get_font(28)
    font_body = get_font(18)

    # タイトル
    draw.text((230, 30), "申込書", fill='black', font=font_title)

    # フォーム項目
    y = 120
    fields = [
        "氏名: ________",
        "",
        "住所: ________",
        "",
        "電話番号: ________",
        "",
        "生年月日: ____年__月__日",
        "",
        "※記入漏れのないようお願いします"
    ]

    for field in fields:
        draw.text((80, y), field, fill='black', font=font_body)
        y += 40

    img.save(output_path)
    print(f"[OK] {output_path}")


def generate_event_info(output_path: Path):
    """イベント情報画像を生成"""
    img = Image.new('RGB', (600, 600), color='#E6F3FF')
    draw = ImageDraw.Draw(img)

    font_title = get_font(28)
    font_body = get_font(18)

    # タイトル
    draw.text((180, 30), "イベント情報", fill='#004080', font=font_title)

    # 枠線
    draw.rectangle([(40, 100), (560, 520)], outline='#004080', width=3)

    # イベント詳細
    y = 140
    details = [
        "日時: 2026年4月15日(火) 14:00-16:00",
        "",
        "場所: 東京会議室 3F",
        "",
        "テーマ: AWS Bedrock 活用事例",
        "",
        "参加費: 無料",
        "",
        "お問い合わせ: info@example.com"
    ]

    for line in details:
        draw.text((80, y), line, fill='black', font=font_body)
        y += 40

    img.save(output_path)
    print(f"[OK] {output_path}")


def main():
    """メイン処理"""
    output_dir = Path("images")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("[INFO] サンプル画像を生成中...")

    generate_receipt(output_dir / "receipt.jpg")
    generate_menu(output_dir / "menu.jpg")
    generate_form(output_dir / "form.jpg")
    generate_event_info(output_dir / "event_info.jpg")

    print("[INFO] 完了")


if __name__ == "__main__":
    main()
