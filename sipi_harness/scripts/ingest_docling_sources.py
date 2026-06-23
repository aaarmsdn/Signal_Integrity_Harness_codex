from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SUPPORTED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".epub",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".md",
    ".markdown",
    ".txt",
    ".text",
    ".csv",
    ".eml",
    ".msg",
    ".xml",
    ".tex",
}

TEXT_FALLBACK_EXTENSIONS = {
    ".md",
    ".markdown",
    ".txt",
    ".text",
    ".csv",
    ".xml",
    ".tex",
}


@dataclass
class SourceItem:
    source: str
    source_id: str
    title: str


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("_")
    return cleaned[:96] or "source"


def load_docling():
    try:
        from docling.document_converter import DocumentConverter  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Docling is not installed in the selected Python environment. "
            "Run `npm run setup:docling` or set DOC_INGEST_PYTHON to an environment "
            "where `pip install -r requirements-docling.txt` has been run."
        ) from exc
    return DocumentConverter


def discover_sources(values: list[str]) -> list[str]:
    sources: list[str] = []
    for value in values:
        if re.match(r"^https?://", value, flags=re.IGNORECASE):
            sources.append(value)
            continue
        path = Path(value)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    sources.append(str(child))
        elif path.is_file():
            sources.append(str(path))
        else:
            raise FileNotFoundError(value)
    return sources


def doc_to_dict(doc: Any) -> dict[str, Any]:
    for method in ("export_to_dict", "model_dump", "dict"):
        candidate = getattr(doc, method, None)
        if callable(candidate):
            try:
                return candidate()
            except TypeError:
                try:
                    return candidate(by_alias=True)
                except Exception:
                    continue
            except Exception:
                continue
    return {"repr": repr(doc)}


def export_markdown(doc: Any) -> str:
    candidate = getattr(doc, "export_to_markdown", None)
    if callable(candidate):
        return candidate()
    return str(doc)


def read_text_with_fallback(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8-replace"


def markdown_chunks(markdown: str, source: SourceItem, source_tier: str) -> list[dict[str, Any]]:
    lines = markdown.replace("\r\n", "\n").split("\n")
    chunks: list[dict[str, Any]] = []
    current_heading = "Document"
    current_level = 0
    buffer: list[str] = []
    chunk_index = 0

    def flush() -> None:
        nonlocal chunk_index, buffer
        text = "\n".join(buffer).strip()
        if not text:
            buffer = []
            return
        chunk_index += 1
        lowered = text.lower()
        chunk_type = "background"
        if any(term in lowered for term in ("shall", "must", "required", "minimum", "maximum", "limit")):
            chunk_type = "requirement_candidate"
        if any(term in lowered for term in ("equation", "formula", "=", ">=", "<=", " db", " ohm")):
            chunk_type = "equation_or_metric_candidate"
        if any(term in lowered for term in ("table", "|---", "<table")):
            chunk_type = "table_candidate"
        if any(term in lowered for term in ("figure", "fig.", "image", "mask", "bump map", "pin map", "ball map")):
            chunk_type = "figure_or_map_candidate"
        chunks.append(
            {
                "chunk_id": f"{source.source_id}_chunk_{chunk_index:04d}",
                "source_id": source.source_id,
                "source": source.source,
                "title": source.title,
                "heading": current_heading,
                "heading_level": current_level,
                "chunk_type": chunk_type,
                "source_tier": source_tier,
                "review_status": "unreviewed",
                "evidence_status": "candidate",
                "text": text,
                "topics": [],
                "claims": [],
                "relationships": [],
                "promotion_policy": "Do not promote to compliance limit until reviewed against governing evidence.",
            }
        )
        buffer = []

    heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
    for line in lines:
        match = heading_re.match(line)
        if match:
            flush()
            current_level = len(match.group(1))
            current_heading = match.group(2).strip()
        buffer.append(line)
    flush()
    return chunks


def convert_one(converter: Any, item: SourceItem, out_dir: Path, source_tier: str) -> dict[str, Any]:
    source_path = Path(item.source) if not re.match(r"^https?://", item.source, re.I) else None
    digest = sha256_file(source_path) if source_path else None
    result = converter.convert(item.source)
    doc = result.document
    markdown = export_markdown(doc)
    doc_json = doc_to_dict(doc)
    item_dir = out_dir / item.source_id
    chunk_dir = item_dir / "chunks"
    item_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir.mkdir(parents=True, exist_ok=True)

    markdown_path = item_dir / f"{item.source_id}.docling.md"
    json_path = item_dir / f"{item.source_id}.docling.json"
    chunks_path = chunk_dir / f"{item.source_id}.chunks.json"
    summary_path = item_dir / f"{item.source_id}.summary.json"

    chunks = markdown_chunks(markdown, item, source_tier)
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(json.dumps(doc_json, indent=2, ensure_ascii=False), encoding="utf-8")
    chunks_path.write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "source_id": item.source_id,
        "title": item.title,
        "source": item.source,
        "source_sha256": digest,
        "source_tier": source_tier,
        "markdown": str(markdown_path),
        "docling_json": str(json_path),
        "chunks": str(chunks_path),
        "chunk_count": len(chunks),
        "review_status": "unreviewed",
        "allowed_usage": [
            "candidate_strategy",
            "source_grounded_design_rule_after_review",
            "tier_0_compliance_only_if_governing_spec_and_reviewed",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def convert_text_fallback(
    item: SourceItem,
    out_dir: Path,
    source_tier: str,
    conversion_error: str,
) -> dict[str, Any]:
    source_path = Path(item.source)
    digest = sha256_file(source_path)
    text, encoding = read_text_with_fallback(source_path)
    item_dir = out_dir / item.source_id
    chunk_dir = item_dir / "chunks"
    item_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir.mkdir(parents=True, exist_ok=True)

    markdown = f"# {item.title}\n\n{text.strip()}\n"
    markdown_path = item_dir / f"{item.source_id}.docling.md"
    json_path = item_dir / f"{item.source_id}.docling.json"
    chunks_path = chunk_dir / f"{item.source_id}.chunks.json"
    summary_path = item_dir / f"{item.source_id}.summary.json"

    chunks = markdown_chunks(markdown, item, source_tier)
    markdown_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(
        json.dumps(
            {
                "fallback": "plain_text",
                "source": item.source,
                "encoding": encoding,
                "conversion_error": conversion_error,
                "text_length": len(text),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    chunks_path.write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = {
        "source_id": item.source_id,
        "title": item.title,
        "source": item.source,
        "source_sha256": digest,
        "source_tier": source_tier,
        "markdown": str(markdown_path),
        "docling_json": str(json_path),
        "chunks": str(chunks_path),
        "chunk_count": len(chunks),
        "conversion_status": "text_fallback",
        "text_encoding": encoding,
        "conversion_error": conversion_error,
        "review_status": "unreviewed",
        "allowed_usage": [
            "candidate_strategy",
            "source_grounded_design_rule_after_review",
            "tier_0_compliance_only_if_governing_spec_and_reviewed",
        ],
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert local/URL documents with Docling into reviewed-evidence candidates for the SIPI LLM wiki."
    )
    parser.add_argument("sources", nargs="*", help="File, directory, or URL sources to convert.")
    parser.add_argument("--out-dir", type=Path, required=False, help="Output directory for converted Docling artifacts.")
    parser.add_argument("--case-dir", type=Path, help="Case directory; defaults out-dir to <case>/knowledge_intake/processed/docling.")
    parser.add_argument("--source-tier", default="tier_1", choices=["tier_0", "tier_1", "tier_2", "tier_3"])
    parser.add_argument("--source-id-prefix", default="")
    parser.add_argument("--check", action="store_true", help="Only verify that Docling imports.")
    args = parser.parse_args()

    DocumentConverter = load_docling()
    if args.check:
        print(json.dumps({"ok": True, "docling_import": "ok"}, indent=2))
        return 0

    if not args.sources:
        parser.error("at least one source file, directory, or URL is required unless --check is used")

    if args.out_dir:
        out_dir = args.out_dir
    elif args.case_dir:
        out_dir = args.case_dir / "knowledge_intake" / "processed" / "docling"
    else:
        out_dir = Path.cwd() / "outputs" / "docling_ingest"
    out_dir.mkdir(parents=True, exist_ok=True)

    converter = DocumentConverter()
    discovered = discover_sources(args.sources)
    base_counts: dict[str, int] = {}
    for source in discovered:
        name = Path(source).stem if not re.match(r"^https?://", source, re.I) else re.sub(r"^https?://", "", source, flags=re.I)
        base_id = safe_id(f"{args.source_id_prefix}{name}")
        base_counts[base_id] = base_counts.get(base_id, 0) + 1
    used_ids: set[str] = set()
    summaries: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for source in discovered:
        source_path = Path(source) if not re.match(r"^https?://", source, re.I) else None
        name = source_path.stem if source_path else re.sub(r"^https?://", "", source, flags=re.I)
        base_id = safe_id(f"{args.source_id_prefix}{name}")
        if base_counts.get(base_id, 0) > 1 and source_path:
            source_id = safe_id(f"{base_id}_{source_path.suffix.lower().lstrip('.')}")
        else:
            source_id = base_id
        if source_id in used_ids:
            index = 2
            candidate = safe_id(f"{source_id}_{index}")
            while candidate in used_ids:
                index += 1
                candidate = safe_id(f"{source_id}_{index}")
            source_id = candidate
        used_ids.add(source_id)
        item = SourceItem(source=source, source_id=source_id, title=name)
        try:
            summaries.append(convert_one(converter, item, out_dir, args.source_tier))
        except Exception as exc:
            source_path = Path(source) if not re.match(r"^https?://", source, re.I) else None
            if source_path and source_path.suffix.lower() in TEXT_FALLBACK_EXTENSIONS:
                summaries.append(convert_text_fallback(item, out_dir, args.source_tier, str(exc)))
            else:
                errors.append({"source": source, "error": str(exc)})

    manifest = {
        "schema_version": "0.1",
        "kind": "docling_ingest_manifest",
        "out_dir": str(out_dir),
        "source_tier": args.source_tier,
        "source_count": len(summaries),
        "error_count": len(errors),
        "errors": errors,
        "items": summaries,
        "review_policy": [
            "Docling output is candidate evidence.",
            "Review source page/table/figure/equation evidence before promoting numeric limits.",
            "Promote reusable engineering knowledge into typed wiki cards only after source tier and applicability are recorded.",
        ],
    }
    manifest_path = out_dir / "docling_ingest_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": bool(summaries),
                "manifest": str(manifest_path),
                "source_count": len(summaries),
                "error_count": len(errors),
            },
            indent=2,
        )
    )
    return 0 if summaries else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        raise
