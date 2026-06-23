from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def extract_page_text_tokens(pdf_path: Path, page_number: int) -> tuple[dict[str, float], list[dict[str, Any]], str]:
    reader = PdfReader(str(pdf_path))
    page = reader.pages[page_number - 1]
    box = page.mediabox
    page_size = {
        "x0": _num(box.left),
        "y0": _num(box.bottom),
        "x1": _num(box.right),
        "y1": _num(box.top),
        "width": _num(box.width),
        "height": _num(box.height),
    }
    tokens: list[dict[str, Any]] = []

    def visitor_text(text: str, cm: list[float], tm: list[float], font_dict: dict[str, Any] | None, font_size: float) -> None:
        stripped = text.strip()
        if not stripped:
            return
        tokens.append(
            {
                "text": stripped,
                "x": _num(tm[4]),
                "y": _num(tm[5]),
                "font_size": _num(font_size),
                "font": (font_dict or {}).get("/BaseFont", ""),
            }
        )

    text = page.extract_text(visitor_text=visitor_text) or ""
    return page_size, tokens, text


def save_text_position_snapshot(page_size: dict[str, float], tokens: list[dict[str, Any]], output_png: Path) -> None:
    scale = 2.0
    margin = 24
    width = max(1, int(page_size["width"] * scale) + margin * 2)
    height = max(1, int(page_size["height"] * scale) + margin * 2)
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("arial.ttf", 12)
        small_font = ImageFont.truetype("arial.ttf", 9)
    except Exception:
        font = ImageFont.load_default()
        small_font = font

    draw.rectangle([margin, margin, width - margin, height - margin], outline=(190, 190, 190))
    draw.text((margin, 4), "PDF vector text position snapshot", fill=(80, 80, 80), font=small_font)

    for token in tokens:
        x = margin + (token["x"] - page_size["x0"]) * scale
        y = margin + (page_size["y1"] - token["y"]) * scale
        fs = token.get("font_size", 0)
        color = (0, 0, 0)
        if fs and fs >= 10:
            color = (0, 40, 160)
        draw.text((x, y), token["text"], fill=color, font=font)

    output_png.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_png)


def save_page_render(pdf_path: Path, page_number: int, output_png: Path, zoom: float = 2.0) -> str:
    try:
        import fitz  # type: ignore
    except Exception as exc:
        return f"pymupdf_unavailable: {exc}"

    doc = fitz.open(str(pdf_path))
    page = doc.load_page(page_number - 1)
    matrix = fitz.Matrix(zoom, zoom)
    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(output_png))
    doc.close()
    return "rendered_with_pymupdf"


def extract_page_images(pdf_path: Path, page_number: int, out_dir: Path, tag: str) -> list[str]:
    reader = PdfReader(str(pdf_path))
    page = reader.pages[page_number - 1]
    saved: list[str] = []
    for idx, image_file_object in enumerate(getattr(page, "images", []) or []):
        suffix = Path(image_file_object.name).suffix or ".bin"
        image_path = out_dir / f"{tag}_page_{page_number}_image_{idx}{suffix}"
        image_path.write_bytes(image_file_object.data)
        saved.append(str(image_path))
    return saved


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract reviewable PDF text/figure evidence from one page.")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--page", required=True, type=int, help="1-based PDF page number")
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--section", default="")
    parser.add_argument("--figure", action="append", default=[])
    args = parser.parse_args()

    page_size, tokens, text = extract_page_text_tokens(args.pdf, args.page)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    text_path = args.out_dir / f"{args.tag}_page_{args.page}_text.txt"
    tokens_path = args.out_dir / f"{args.tag}_page_{args.page}_text_positions.json"
    png_path = args.out_dir / f"{args.tag}_page_{args.page}_text_positions.png"
    render_path = args.out_dir / f"{args.tag}_page_{args.page}_render.png"
    summary_path = args.out_dir / f"{args.tag}_page_{args.page}_evidence_summary.json"

    text_path.write_text(text, encoding="utf-8")
    tokens_path.write_text(json.dumps({"page_size": page_size, "tokens": tokens}, indent=2), encoding="utf-8")
    save_text_position_snapshot(page_size, tokens, png_path)
    render_status = save_page_render(args.pdf, args.page, render_path)
    embedded_images = extract_page_images(args.pdf, args.page, args.out_dir, args.tag)

    summary = {
        "source_pdf": str(args.pdf),
        "page": args.page,
        "section": args.section,
        "figures": args.figure,
        "extraction_method": "pypdf page text extraction with visitor_text coordinates; PIL snapshot generated from PDF text coordinates",
        "raw_text_path": str(text_path),
        "text_positions_path": str(tokens_path),
        "text_position_snapshot_path": str(png_path),
        "page_render_path": str(render_path) if render_path.exists() else None,
        "page_render_status": render_status,
        "embedded_image_paths": embedded_images,
        "figure_snapshot_or_page_text_position_path": str(render_path if render_path.exists() else png_path),
        "reviewer_status": "visual_cross_check_needed",
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
