from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_KEYWORDS = [
    "shall",
    "must",
    "required",
    "requirement",
    "specification",
    "compliance",
    "table",
    "figure",
    "equation",
    "mask",
    "limit",
    "minimum",
    "maximum",
    "insertion loss",
    "return loss",
    "crosstalk",
    "skew",
    "jitter",
    "eye diagram",
    "eye mask",
    "eye height",
    "eye width",
    "rectangular eye",
    "BER",
    "bit error rate",
    "BER contour",
    "bathtub",
    "contour",
    "voltage transfer function",
    "VTF",
    "impedance",
    "source",
    "load",
    "termination",
    "capacitance",
    "package",
    "channel",
    "pin map",
    "ball map",
    "bump map",
    "pad",
    "lane",
    "port",
]

UNITS_PATTERN = (
    r"(?:GHz|MHz|kHz|Hz|GT/s|Gbps|bps|dB|ohm|Ohm|mV|V|A|mA|pF|nF|uF|fF|"
    r"ps|ns|UI|mm|um|mil|%)"
)

NUMBER_PATTERN = r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?"

NUMERIC_REQUIREMENT_RE = re.compile(
    rf"(?P<context>.{{0,120}}(?:<=|>=|<|>|=|minimum|maximum|min|max|shall|must|required).{{0,120}}"
    rf"{NUMBER_PATTERN}\s*{UNITS_PATTERN}.{{0,120}})",
    re.IGNORECASE,
)

BER_REQUIREMENT_RE = re.compile(
    rf"(?P<context>.{{0,140}}(?:BER|bit\s+error\s+rate|error\s+rate|raw\s+bit\s+error).{{0,140}}"
    rf"{NUMBER_PATTERN}.{{0,140}})",
    re.IGNORECASE,
)

FIGURE_TABLE_RE = re.compile(
    r"\b(?P<kind>table|figure|fig\.|equation|eq\.)\s*(?P<label>[A-Za-z0-9_.:-]+)",
    re.IGNORECASE,
)


@dataclass
class PageEvidence:
    page: int
    label: str
    text_path: str
    blocks_path: str
    render_path: str | None
    score: int
    candidate_count: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def tokens(text: str) -> set[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "into",
        "shall",
        "must",
        "should",
        "will",
        "can",
        "are",
        "was",
        "were",
    }
    return {item for item in re.findall(r"[A-Za-z0-9_.+-]+", text.lower()) if len(item) >= 3 and item not in stop}


def load_pymupdf():
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised in user environment
        raise RuntimeError(
            "PyMuPDF is required for full-spec evidence extraction. "
            "Run `npm run setup:pdf-python` first."
        ) from exc
    return fitz


def extract_blocks(page: Any) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    raw = page.get_text("dict")
    for block_index, block in enumerate(raw.get("blocks", [])):
        if block.get("type") != 0:
            blocks.append(
                {
                    "block_index": block_index,
                    "type": block.get("type"),
                    "bbox": block.get("bbox"),
                    "text": "",
                }
            )
            continue
        lines: list[str] = []
        spans: list[dict[str, Any]] = []
        for line in block.get("lines", []):
            line_text = []
            for span in line.get("spans", []):
                text = span.get("text", "")
                line_text.append(text)
                spans.append(
                    {
                        "text": text,
                        "bbox": span.get("bbox"),
                        "size": span.get("size"),
                        "font": span.get("font"),
                    }
                )
            if "".join(line_text).strip():
                lines.append("".join(line_text).strip())
        blocks.append(
            {
                "block_index": block_index,
                "type": block.get("type"),
                "bbox": block.get("bbox"),
                "text": "\n".join(lines),
                "spans": spans,
            }
        )
    return blocks


def detect_candidates(page_number: int, text: str, blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()

    for match in FIGURE_TABLE_RE.finditer(text):
        key = f"{match.group('kind').lower()}:{match.group('label')}"
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "id": f"p{page_number}_{re.sub(r'[^A-Za-z0-9_]+', '_', key).strip('_')}",
                "page": page_number,
                "kind": match.group("kind").lower().replace(".", ""),
                "label": match.group("label"),
                "text": clean_text(text[max(0, match.start() - 180) : match.end() + 220]),
                "extraction_method": "pdf_text_reference_detection",
                "source_id": f"page_{page_number}",
                "reviewer_status": "unreviewed",
            }
        )

    for idx, match in enumerate(NUMERIC_REQUIREMENT_RE.finditer(text), start=1):
        snippet = clean_text(match.group("context"))
        key = snippet.lower()
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "id": f"p{page_number}_numeric_requirement_{idx}",
                "page": page_number,
                "kind": "numeric_requirement_candidate",
                "label": None,
                "text": snippet,
                "extraction_method": "regex_numeric_requirement_detection",
                "source_id": f"page_{page_number}",
                "reviewer_status": "unreviewed",
                "needs_engineer_classification": True,
            }
        )

    for idx, match in enumerate(BER_REQUIREMENT_RE.finditer(text), start=1):
        snippet = clean_text(match.group("context"))
        key = f"ber:{snippet.lower()}"
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "id": f"p{page_number}_ber_requirement_{idx}",
                "page": page_number,
                "kind": "ber_or_eye_requirement_candidate",
                "label": None,
                "text": snippet,
                "extraction_method": "regex_ber_requirement_detection",
                "source_id": f"page_{page_number}",
                "reviewer_status": "unreviewed",
                "needs_engineer_classification": True,
            }
        )

    for block in blocks:
        block_text = clean_text(block.get("text", ""))
        if not block_text:
            continue
        lowered = block_text.lower()
        if any(
            keyword in lowered
            for keyword in (
                "pin map",
                "ball map",
                "bump map",
                "eye mask",
                "eye diagram",
                "eye height",
                "eye width",
                "rectangular eye",
                "ber contour",
                "bit error rate",
                "bathtub",
                "jitter",
                "loading model",
                "test setup",
                "voltage transfer function",
                "vtf",
            )
        ):
            candidate_kind = "graphical_or_map_candidate"
            if any(keyword in lowered for keyword in ("eye", "ber", "bathtub", "jitter")):
                candidate_kind = "eye_or_ber_requirement_candidate"
            elif any(keyword in lowered for keyword in ("voltage transfer function", "vtf", "loading model")):
                candidate_kind = "loading_or_transfer_function_candidate"
            candidates.append(
                {
                    "id": f"p{page_number}_block_{block.get('block_index')}_graphical_or_map_candidate",
                    "page": page_number,
                    "kind": candidate_kind,
                    "label": None,
                    "text": block_text[:600],
                    "bbox": block.get("bbox"),
                    "extraction_method": "keyword_block_detection",
                    "source_id": f"page_{page_number}",
                    "reviewer_status": "visual_cross_check_needed",
                    "requires_render_review": True,
                }
            )
    return candidates


def score_page(text: str, query_words: set[str], keywords: list[str], candidates: list[dict[str, Any]]) -> int:
    lowered = text.lower()
    score = len(tokens(text) & query_words) * 3
    score += sum(2 for keyword in keywords if keyword.lower() in lowered)
    score += len(candidates) * 4
    if re.search(r"\b(table|figure|equation)\b", lowered):
        score += 5
    return score


def render_page(page: Any, output_png: Path, zoom: float) -> str:
    fitz = load_pymupdf()
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    pixmap.save(str(output_png))
    return str(output_png)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def extract_spec_evidence(
    pdf: Path,
    out_dir: Path,
    tag: str,
    request: str = "",
    keywords: list[str] | None = None,
    max_pages: int | None = None,
    render_mode: str = "candidates",
    render_zoom: float = 2.0,
) -> dict[str, Any]:
    fitz = load_pymupdf()
    keywords = keywords or DEFAULT_KEYWORDS
    query_words = tokens(" ".join([request, " ".join(keywords)]))

    doc = fitz.open(str(pdf))
    page_count = len(doc)
    page_limit = min(page_count, max_pages) if max_pages else page_count
    evidence_root = out_dir / "spec_evidence"
    pages_dir = evidence_root / "pages"
    renders_dir = evidence_root / "renders"

    all_candidates: list[dict[str, Any]] = []
    pages: list[PageEvidence] = []

    toc = [
        {"level": level, "title": title, "page": page}
        for level, title, page in (doc.get_toc(simple=True) or [])
    ]

    for index in range(page_limit):
        page_number = index + 1
        page = doc.load_page(index)
        text = page.get_text("text") or ""
        blocks = extract_blocks(page)
        candidates = detect_candidates(page_number, text, blocks)
        score = score_page(text, query_words, keywords, candidates)
        page_tag = f"{tag}_page_{page_number:04d}"
        text_path = pages_dir / f"{page_tag}.txt"
        blocks_path = pages_dir / f"{page_tag}_blocks.json"
        text_path.parent.mkdir(parents=True, exist_ok=True)
        text_path.write_text(text, encoding="utf-8")
        write_json(blocks_path, {"page": page_number, "blocks": blocks})

        render_path: str | None = None
        should_render = render_mode == "all" or (render_mode == "candidates" and (candidates or score > 0))
        if should_render:
            render_path = render_page(page, renders_dir / f"{page_tag}.png", render_zoom)

        for candidate in candidates:
            candidate["source_pdf"] = str(pdf)
            candidate["page_render_path"] = render_path
            candidate["raw_text_path"] = str(text_path)
            candidate["blocks_path"] = str(blocks_path)
        all_candidates.extend(candidates)

        pages.append(
            PageEvidence(
                page=page_number,
                label=page.get_label(),
                text_path=str(text_path),
                blocks_path=str(blocks_path),
                render_path=render_path,
                score=score,
                candidate_count=len(candidates),
            )
        )

    doc.close()

    ranked_pages = sorted(
        [
            {
                "page": item.page,
                "label": item.label,
                "score": item.score,
                "candidate_count": item.candidate_count,
                "text_path": item.text_path,
                "blocks_path": item.blocks_path,
                "render_path": item.render_path,
            }
            for item in pages
        ],
        key=lambda item: (-int(item["score"]), int(item["page"])),
    )

    manifest = {
        "schema_version": "spec_evidence_v1",
        "source_pdf": str(pdf),
        "source_sha256": sha256_file(pdf),
        "tag": tag,
        "request": request,
        "page_count": page_count,
        "processed_pages": page_limit,
        "toc": toc,
        "outputs": {
            "inventory": str(evidence_root / "spec_inventory.json"),
            "candidates": str(evidence_root / "spec_candidates.json"),
            "review_queue": str(evidence_root / "spec_review_queue.json"),
        },
        "review_policy": {
            "default_status": "unreviewed",
            "design_use_requires": [
                "visual_cross_checked",
                "approved_for_design",
            ],
            "compliance_use_requires": [
                "approved_for_design",
            ],
        },
    }

    inventory = {
        **manifest,
        "ranked_pages": ranked_pages,
        "pages": [item.__dict__ for item in pages],
    }

    candidates_payload = {
        "schema_version": "spec_candidates_v1",
        "source_pdf": str(pdf),
        "tag": tag,
        "candidate_count": len(all_candidates),
        "candidates": all_candidates,
        "classification_targets": [
            "spec_constraint",
            "interface_profile",
            "stackup_profile",
            "validation_metric",
            "validation_flow",
            "bump_or_pin_map",
            "loading_model",
            "eye_mask",
            "eye_diagram",
            "BER_target",
            "BER_contour",
            "bathtub",
            "jitter_requirement",
            "equation",
            "ignore",
        ],
        "notes": [
            "Candidates are not compliance values until classified and reviewed.",
            "Numeric values detected by regex must be linked to a governing table, clause, equation, or figure.",
            "Figure-derived maps require visual cross-check before geometry generation.",
        ],
    }

    review_queue = {
        "schema_version": "spec_review_queue_v1",
        "status": "review_required",
        "source_pdf": str(pdf),
        "review_items": [
            {
                "candidate_id": candidate["id"],
                "page": candidate["page"],
                "kind": candidate["kind"],
                "text": candidate.get("text", "")[:300],
                "page_render_path": candidate.get("page_render_path"),
                "required_action": "classify_and_approve_or_reject",
            }
            for candidate in all_candidates
        ],
    }

    write_json(evidence_root / "spec_manifest.json", manifest)
    write_json(evidence_root / "spec_inventory.json", inventory)
    write_json(evidence_root / "spec_candidates.json", candidates_payload)
    write_json(evidence_root / "spec_review_queue.json", review_queue)
    return {
        "manifest": str(evidence_root / "spec_manifest.json"),
        "inventory": str(evidence_root / "spec_inventory.json"),
        "candidates": str(evidence_root / "spec_candidates.json"),
        "review_queue": str(evidence_root / "spec_review_queue.json"),
        "candidate_count": len(all_candidates),
        "processed_pages": page_limit,
        "page_count": page_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract generic tier-0 spec evidence from a PDF into a case-local evidence bundle.")
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--case-dir", required=True, type=Path)
    parser.add_argument("--tag", default=None)
    parser.add_argument("--request", default="")
    parser.add_argument("--request-file", default=None, type=Path)
    parser.add_argument("--keyword", action="append", default=[])
    parser.add_argument("--max-pages", type=int, default=None)
    parser.add_argument("--render", choices=["none", "candidates", "all"], default="candidates")
    parser.add_argument("--render-zoom", type=float, default=2.0)
    args = parser.parse_args()

    request = args.request
    if args.request_file:
        request = args.request_file.read_text(encoding="utf-8-sig").strip()
    tag = args.tag or re.sub(r"[^A-Za-z0-9_]+", "_", args.pdf.stem).strip("_").lower()[:80]
    keywords = DEFAULT_KEYWORDS + args.keyword
    result = extract_spec_evidence(
        pdf=args.pdf.resolve(),
        out_dir=args.case_dir.resolve(),
        tag=tag,
        request=request,
        keywords=keywords,
        max_pages=args.max_pages,
        render_mode=args.render,
        render_zoom=args.render_zoom,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
