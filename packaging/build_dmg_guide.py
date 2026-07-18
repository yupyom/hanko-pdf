#!/usr/bin/env python3
"""DMG同梱用のMarkdown原稿を、macOSで読めるRTFへ変換する。"""

from __future__ import annotations

import argparse
import html
import subprocess
import tempfile
from pathlib import Path


def markdown_to_html(source: str) -> str:
    """クイックスタートで使う最小限のMarkdownを、整形済みHTMLへ変換する。"""
    blocks: list[str] = []
    paragraph: list[str] = []
    bullets: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{html.escape(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_bullets() -> None:
        if bullets:
            items = "".join(f"<li>{html.escape(item)}</li>" for item in bullets)
            blocks.append(f"<ul>{items}</ul>")
            bullets.clear()

    for line in source.splitlines():
        text = line.strip()
        if not text:
            flush_paragraph()
            flush_bullets()
        elif text.startswith("# "):
            flush_paragraph()
            flush_bullets()
            blocks.append(f"<h1>{html.escape(text[2:])}</h1>")
        elif text.startswith("## "):
            flush_paragraph()
            flush_bullets()
            blocks.append(f"<h2>{html.escape(text[3:])}</h2>")
        elif text.startswith("- "):
            flush_paragraph()
            bullets.append(text[2:])
        else:
            flush_bullets()
            paragraph.append(text)
    flush_paragraph()
    flush_bullets()

    content = "\n".join(blocks)
    return f"""<!doctype html>
<html lang=\"ja\"><head><meta charset=\"utf-8\"><style>
body {{ font-family: -apple-system, 'Hiragino Sans', sans-serif; color: #183137; font-size: 14pt; line-height: 1.55; margin: 44px; }}
h1 {{ color: #147b73; font-size: 28pt; margin: 0 0 18px; }}
h2 {{ color: #147b73; font-size: 17pt; margin: 28px 0 8px; }}
p {{ margin: 0 0 12px; }}
ul {{ margin: 0 0 14px 22px; padding: 0; }}
li {{ margin: 0 0 7px; }}
</style></head><body>{content}</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="DMG同梱用のRTFガイドを生成します。")
    parser.add_argument("--source", type=Path, default=Path(__file__).with_name("DMG_QUICK_START.md"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hanko-pdf-guide-") as directory:
        html_path = Path(directory) / "Hanko PDFをはじめる.html"
        html_path.write_text(markdown_to_html(source), encoding="utf-8")
        subprocess.run(
            ["textutil", "-convert", "rtf", "-format", "html", "-output", str(args.output), str(html_path)],
            check=True,
        )


if __name__ == "__main__":
    main()
