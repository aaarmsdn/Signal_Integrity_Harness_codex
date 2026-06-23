from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


ROOT = Path(__file__).resolve().parents[2]

RAW_INGEST_EXTENSIONS = {
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

INTERFACE_FAMILY_TOKENS = {
    "ucie": {"ucie", "universal_chiplet"},
    "cxl": {"cxl", "compute_express_link"},
    "pcie": {"pcie", "pci_express", "pciexpress"},
    "usb": {"usb"},
    "hbm": {"hbm"},
    "ddr": {"ddr", "lpddr", "gddr"},
    "serdes": {"serdes"},
}

TEXT_PROBE_EXTENSIONS = {
    ".md",
    ".markdown",
    ".html",
    ".htm",
    ".txt",
    ".text",
    ".csv",
    ".xml",
    ".tex",
}


@dataclass
class WikiHit:
    path: Path
    title: str
    score: int
    snippets: list[str]
    meta: dict[str, Any]


def read_json(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    if path.is_dir():
        payload: dict[str, Any] = {
            "spec_evidence_dir": str(path),
        }
        for name in ("spec_manifest.json", "spec_inventory.json", "spec_candidates.json", "spec_review_queue.json"):
            candidate = path / name
            if candidate.exists():
                payload[name.replace(".json", "")] = json.loads(candidate.read_text(encoding="utf-8-sig"))
        return payload
    return json.loads(path.read_text(encoding="utf-8-sig"))


def clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip())


def words(text: str) -> set[str]:
    tokens = re.findall(r"[A-Za-z0-9_./+-]+", text.lower())
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "into",
        "must",
        "should",
        "case",
        "task",
        "design",
    }
    return {token for token in tokens if len(token) >= 3 and token not in stop}


def source_probe_text(path: Path, max_bytes: int = 160_000) -> str:
    if path.suffix.lower() not in TEXT_PROBE_EXTENSIONS:
        return ""
    try:
        raw = path.read_bytes()[:max_bytes]
    except OSError:
        return ""
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def markdown_title(path: Path, text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return clean_line(line.lstrip("#"))
    return path.stem


def parse_scalar(value: str) -> Any:
    text = value.strip()
    if text in {"null", "~"}:
        return None
    if text == "true":
        return True
    if text == "false":
        return False
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return float(text) if "." in text else int(text)
    if text.startswith('"') and text.endswith('"'):
        return text[1:-1].replace('\\"', '"')
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return [] if not inner else [parse_scalar(item.strip()) for item in inner.split(",")]
    return text


def parse_frontmatter(text: str) -> dict[str, Any]:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        return {}
    end = normalized.find("\n---", 4)
    if end < 0:
        return {}
    lines = normalized[4:end].splitlines()
    meta: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r"^([A-Za-z0-9_./-]+):\s*(.*)$", line)
        if not match:
            i += 1
            continue
        key, value = match.groups()
        if value:
            meta[key] = parse_scalar(value)
            i += 1
            continue
        values: list[Any] = []
        nested: dict[str, Any] = {}
        i += 1
        while i < len(lines) and (lines[i].startswith("  - ") or re.match(r"^  [A-Za-z0-9_./-]+:", lines[i])):
            item = lines[i]
            if item.startswith("  - "):
                values.append(parse_scalar(item[4:].strip()))
            else:
                sub = re.match(r"^  ([A-Za-z0-9_./-]+):\s*(.*)$", item)
                if sub:
                    nested[sub.group(1)] = parse_scalar(sub.group(2))
            i += 1
        meta[key] = values if values else nested if nested else None
    return meta


def is_graph_meta(meta: dict[str, Any]) -> bool:
    return meta.get("graph") is True or meta.get("graph") == "true"


def collect_wiki_hits(wiki_dir: Path, query_text: str, limit: int = 16) -> list[WikiHit]:
    query = words(query_text)
    hits: list[WikiHit] = []
    for path in sorted(wiki_dir.rglob("*.md")):
        relative_parts = path.relative_to(wiki_dir).parts
        if "templates" in relative_parts:
            continue
        if "raw" in relative_parts:
            # Raw staging files are not typed wiki cards. They enter retrieval
            # through data/sources.json after inventory/docling registration so
            # the report can label them as metadata-only or candidate evidence.
            continue
        text = path.read_text(encoding="utf-8-sig")
        meta = parse_frontmatter(text)
        if meta and not is_graph_meta(meta):
            continue
        lines = [clean_line(line) for line in text.splitlines()]
        score = 0
        snippets: list[str] = []
        for idx, line in enumerate(lines):
            if not line:
                continue
            line_words = words(line)
            overlap = query & line_words
            if line.startswith("#"):
                score += 2 * len(overlap)
            else:
                score += len(overlap)
            if overlap and len(snippets) < 7:
                start = max(0, idx - 1)
                stop = min(len(lines), idx + 2)
                snippet = " ".join(part for part in lines[start:stop] if part)
                snippets.append(snippet[:260])
        if score or not query:
            hits.append(WikiHit(path=path, title=markdown_title(path, text), score=score, snippets=snippets, meta=meta))
    return sorted(hits, key=lambda hit: (-hit.score, hit.path.name))[:limit]


def source_doc_text(doc: dict[str, Any]) -> str:
    fields: list[str] = []
    for key in ("id", "title", "kind", "topic", "summary", "publisher", "url"):
        value = doc.get(key)
        if value:
            fields.append(str(value))
    for key in ("concepts", "claims", "relationships", "paths", "sample_paths"):
        value = doc.get(key)
        if isinstance(value, list):
            fields.extend(json.dumps(item, ensure_ascii=False) for item in value[:20])
    return "\n".join(fields)


def collect_source_hits(source_json: Path, query_text: str, limit: int = 16) -> list[WikiHit]:
    if not source_json.exists():
        return []
    payload = json.loads(source_json.read_text(encoding="utf-8-sig"))
    query = words(query_text)
    hits: list[WikiHit] = []
    allowed_kinds = {
        "raw_source_inventory",
        "raw_source_group",
        "docling_source",
        "docling_chunk",
        "sipi_reference",
        "design_strategy",
        "formula",
        "tool_connector",
        "llm_wiki_method",
    }
    for doc in payload.get("documents", []):
        if doc.get("kind") not in allowed_kinds:
            continue
        text = source_doc_text(doc)
        if not text:
            continue
        doc_words = words(text)
        overlap = query & doc_words
        score = len(overlap)
        interface_terms = {"ucie", "hbm", "jedec", "pcie", "cxl", "ddr", "lpddr", "aib", "serdes"}
        matched_interfaces = query & doc_words & interface_terms
        if matched_interfaces:
            score += 8 * len(matched_interfaces)
        if doc.get("kind") == "raw_source_group" and overlap:
            score += 5
        if doc.get("kind") in {"docling_source", "docling_chunk"} and overlap:
            score += 3
        title = str(doc.get("title") or doc.get("id") or "Source Document")
        if query and not score:
            continue
        snippets: list[str] = []
        summary = clean_line(str(doc.get("summary") or ""))
        if summary:
            snippets.append(summary[:300])
        for claim in doc.get("claims", [])[:5]:
            snippets.append(clean_line(str(claim))[:300])
        if doc.get("kind") == "raw_source_group":
            snippets.append(
                "Raw source group metadata only: run Docling/spec extraction before using file contents as design evidence."
            )
        hits.append(
            WikiHit(
                path=Path("data") / f"sources.json#{doc.get('id', title)}",
                title=title,
                score=score,
                snippets=snippets[:7],
                meta={
                    "id": doc.get("id"),
                    "page_type": doc.get("kind"),
                    "source_tier": doc.get("source_tier"),
                    "source_ids": [doc.get("id")] if doc.get("id") else [],
                    "outputs_to": [],
                    "confidence": "metadata_only" if doc.get("kind") == "raw_source_group" else None,
                    "status": doc.get("review_status") or doc.get("evidence_status") or "registered",
                },
            )
        )
    return sorted(hits, key=lambda hit: (-hit.score, hit.title))[:limit]


def collect_docling_hits_from_root(root: Path, query_text: str, limit: int = 24) -> list[WikiHit]:
    if not root.exists():
        return []
    query = words(query_text)
    hits: list[WikiHit] = []
    for manifest_path in sorted(root.rglob("docling_ingest_manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        items = manifest.get("items")
        if not isinstance(items, list):
            items = [manifest] if manifest.get("chunks") or manifest.get("source") else []
        for summary in items:
            if not isinstance(summary, dict):
                continue
            chunks_path = summary.get("chunks")
            if chunks_path:
                chunk_file = Path(chunks_path)
                if not chunk_file.is_absolute():
                    chunk_file = (manifest_path.parent / chunk_file).resolve()
                if chunk_file.exists():
                    try:
                        chunks = json.loads(chunk_file.read_text(encoding="utf-8-sig"))
                    except Exception:
                        chunks = []
                    for chunk in chunks:
                        if not isinstance(chunk, dict):
                            continue
                        text = "\n".join(
                            str(chunk.get(key, ""))
                            for key in ("title", "heading", "chunk_type", "text")
                        )
                        overlap = query & words(text)
                        score = len(overlap)
                        if chunk.get("chunk_type") in {"requirement_candidate", "equation_or_metric_candidate", "table_candidate", "figure_or_map_candidate"}:
                            score += 3
                        if query and score <= 0:
                            continue
                        source_id = str(chunk.get("chunk_id") or chunk.get("source_id") or chunk_file.stem)
                        hits.append(
                            WikiHit(
                                path=chunk_file,
                                title=f"{chunk.get('title', summary.get('title', 'Docling Source'))} - {chunk.get('heading', 'Chunk')}",
                                score=score,
                                snippets=[clean_line(str(chunk.get("text", "")))[:360]],
                                meta={
                                    "id": source_id,
                                    "page_type": "docling_chunk",
                                    "source_tier": chunk.get("source_tier", summary.get("source_tier")),
                                    "source_ids": [chunk.get("source_id", summary.get("source_id"))],
                                    "outputs_to": spec_outputs_for_text(str(chunk.get("chunk_type", "")), text),
                                    "confidence": "candidate_content",
                                    "status": chunk.get("review_status") or chunk.get("evidence_status") or "unreviewed",
                                },
                            )
                        )
            text = "\n".join(str(summary.get(key, "")) for key in ("title", "source", "source_tier"))
            overlap = query & words(text)
            if overlap:
                hits.append(
                    WikiHit(
                        path=manifest_path,
                        title=str(summary.get("title") or summary.get("source_id") or "Docling Source"),
                        score=len(overlap) + 2,
                        snippets=[
                            "Docling source converted for this case; chunks are candidate content evidence and require review before compliance use."
                        ],
                        meta={
                            "id": f"docling_source_{summary.get('source_id', manifest_path.parent.name)}",
                            "page_type": "docling_source",
                            "source_tier": summary.get("source_tier"),
                            "source_ids": [summary.get("source_id")],
                            "outputs_to": [],
                            "confidence": "candidate_content",
                            "status": summary.get("review_status", "unreviewed"),
                        },
                    )
                )
    return sorted(hits, key=lambda hit: (-hit.score, hit.title))[:limit]


def spec_outputs_for_text(kind: str, text: str) -> list[str]:
    lowered = text.lower()
    outputs: list[str] = []
    if any(term in lowered for term in ("bump", "ball", "pin map", "bump map", "pitch", "channel reach", "routing")):
        outputs.append("design_strategy.routing")
    if any(term in lowered for term in ("stackup", "layer", "dielectric", "dk", "df", "material")):
        outputs.append("design_strategy.stackup")
    if any(
        term in lowered
        for term in (
            "impedance",
            "insertion loss",
            "return loss",
            "crosstalk",
            "next",
            "fext",
            "skew",
            "jitter",
            "s-parameter",
            "s parameter",
        )
    ):
        outputs.append("design_strategy.si_checks")
    if any(
        term in lowered
        for term in (
            "voltage transfer function",
            "vtf",
            "eye",
            "mask",
            "ber",
            "bathtub",
            "loading",
            "receiver termination",
            "rx termination",
            "tx:",
            "rx:",
            "equation",
        )
    ):
        outputs.append("design_strategy.validation_benches")
    if kind in {
        "table",
        "figure",
        "numeric_requirement_candidate",
        "graphical_or_map_candidate",
        "ber_or_eye_requirement_candidate",
        "eye_or_ber_requirement_candidate",
        "loading_or_transfer_function_candidate",
    } and not outputs:
        outputs.append("design_strategy.validation_benches")
    return sorted(set(outputs))


def collect_spec_evidence_hits(spec: dict[str, Any], query_text: str, limit: int = 32) -> list[WikiHit]:
    if not spec:
        return []
    candidates_doc = spec.get("spec_candidates")
    if not isinstance(candidates_doc, dict):
        return []
    query = words(query_text)
    candidates = candidates_doc.get("candidates")
    if not isinstance(candidates, list):
        return []
    hits: list[WikiHit] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        text = clean_line(str(candidate.get("text", "")))
        if not text:
            continue
        kind = str(candidate.get("kind", "spec_candidate"))
        label = str(candidate.get("label") or "")
        evidence_id = str(candidate.get("id") or f"spec_page_{candidate.get('page', 'unknown')}")
        searchable = " ".join([text, kind, label, str(candidate.get("page", ""))])
        overlap = query & words(searchable)
        score = len(overlap)
        if kind in {"numeric_requirement_candidate", "table"}:
            score += 2
        if kind in {"figure", "graphical_or_map_candidate"}:
            score += 1
        if any(term in searchable.lower() for term in ("vtf", "voltage transfer", "eye", "mask", "ber", "crosstalk", "impedance", "bump map")):
            score += 4
        if query and score <= 1:
            continue
        outputs = spec_outputs_for_text(kind, searchable)
        review_status = str(candidate.get("reviewer_status") or "unreviewed")
        source_pdf = candidate.get("source_pdf") or candidates_doc.get("source_pdf")
        hits.append(
            WikiHit(
                path=Path(str(candidate.get("raw_text_path") or candidate.get("page_render_path") or f"spec_evidence#{evidence_id}")),
                title=f"Spec Evidence {evidence_id}",
                score=score,
                snippets=[f"page {candidate.get('page', '?')} {kind} {label}: {text[:360]}"],
                meta={
                    "id": evidence_id,
                    "page_type": "spec_evidence_candidate",
                    "source_tier": "tier_0",
                    "source_ids": [str(source_pdf)] if source_pdf else [evidence_id],
                    "outputs_to": outputs,
                    "confidence": "candidate_content",
                    "status": review_status,
                    "missing_information": [
                        "Spec evidence candidate must be reviewed or approved before use as a compliance limit."
                    ]
                    if review_status not in {"approved_for_design", "reviewed", "visual_cross_checked"}
                    else [],
                },
            )
        )
    return sorted(hits, key=lambda hit: (-hit.score, hit.title))[:limit]


def select_raw_sources_for_request(raw_inventory: Path, query_text: str, limit: int) -> list[Path]:
    if not raw_inventory.exists() or limit <= 0:
        return []
    inventory = json.loads(raw_inventory.read_text(encoding="utf-8-sig"))
    raw_root = Path(inventory.get("raw_root", raw_inventory.parents[1] / "wiki" / "raw"))
    query = words(query_text)
    requested_families = {
        family
        for family, aliases in INTERFACE_FAMILY_TOKENS.items()
        if aliases & query or family in query_text.lower()
    }
    requested_versions = [
        token
        for token in re.findall(r"(?i)(?:rev(?:ision)?\s*)?(\d+\.\d+)", query_text)
        if "." in token
    ]
    candidates: list[tuple[int, Path]] = []
    for group in inventory.get("groups", []):
        group_text = " ".join(
            [
                str(group.get("key", "")),
                " ".join(str(item) for item in group.get("concepts", [])),
                " ".join(f"{item.get('extension', '')}:{item.get('count', '')}" for item in group.get("extensions", [])),
            ]
        )
        group_score = len(query & words(group_text))
        for rel in group.get("paths") or group.get("sample_paths", []):
            source = raw_root / rel
            if not source.exists() or not source.is_file():
                continue
            if source.suffix.lower() not in RAW_INGEST_EXTENSIONS:
                continue
            path_terms = words(str(rel))
            probe_terms = words(source_probe_text(source))
            path_lower = str(rel).lower()
            path_families = {
                family
                for family, aliases in INTERFACE_FAMILY_TOKENS.items()
                if any(alias in path_lower for alias in aliases)
            }
            if requested_families and path_families and not (requested_families & path_families):
                continue
            path_overlap = len(query & path_terms)
            content_overlap = len(query & probe_terms)
            path_score = group_score + (path_overlap * 6) + (content_overlap * 8)
            lower = path_lower
            if requested_families & path_families:
                path_score += 40
            if any(term in lower for term in ("spec", "specification", "datasheet")):
                path_score += 4
            if any(term in lower for term in ("readme", "index", "license", "copyright")):
                path_score -= 8
            for version in requested_versions:
                version_p = version.replace(".", "p")
                if version in lower or version_p in lower or f"rev{version_p}" in lower:
                    path_score += 30
                elif re.search(r"rev\d+p\d+|\d+p\d+", lower):
                    path_score -= 10
            if path_overlap <= 0 and content_overlap <= 0 and path_score < 8:
                continue
            candidates.append((path_score, source))
    selected: list[Path] = []
    seen: set[Path] = set()
    for _, source in sorted(candidates, key=lambda item: (-item[0], str(item[1]))):
        resolved = source.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        selected.append(resolved)
        if len(selected) >= limit:
            break
    return selected


def refresh_raw_source_inventory() -> dict[str, Any]:
    """Register wiki/raw before auto-ingest so fresh clones see user-provided sources."""
    script = ROOT / "sipi_harness" / "scripts" / "register_raw_source_inventory.mjs"
    if not script.exists():
        return {"ran": False, "ok": False, "error": f"missing script: {script}"}
    cp = subprocess.run(
        ["node", str(script)],
        cwd=str(ROOT / "sipi_harness"),
        capture_output=True,
        text=True,
    )
    return {
        "ran": True,
        "ok": cp.returncode == 0,
        "returncode": cp.returncode,
        "stdout_tail": cp.stdout[-2000:],
        "stderr_tail": cp.stderr[-2000:],
    }


def refresh_docling_source_registry(case_dir: Path) -> dict[str, Any]:
    """Register newly converted Docling chunks so graph/source search can see them."""
    script = ROOT / "sipi_harness" / "scripts" / "register_docling_sources.mjs"
    graph_script = ROOT / "sipi_harness" / "scripts" / "build_graph.mjs"
    if not script.exists():
        return {"ran": False, "ok": False, "error": f"missing script: {script}"}
    cp = subprocess.run(
        ["node", str(script), "--case-dir", str(case_dir)],
        cwd=str(ROOT / "sipi_harness"),
        capture_output=True,
        text=True,
    )
    graph = None
    if cp.returncode == 0 and graph_script.exists():
        graph_cp = subprocess.run(
            ["node", str(graph_script)],
            cwd=str(ROOT / "sipi_harness"),
            capture_output=True,
            text=True,
        )
        graph = {
            "returncode": graph_cp.returncode,
            "stdout_tail": graph_cp.stdout[-1000:],
            "stderr_tail": graph_cp.stderr[-1000:],
        }
    return {
        "ran": True,
        "ok": cp.returncode == 0,
        "returncode": cp.returncode,
        "stdout_tail": cp.stdout[-2000:],
        "stderr_tail": cp.stderr[-2000:],
        "graph_refresh": graph,
    }


def run_auto_ingest(
    case_dir: Path,
    request: str,
    raw_inventory: Path,
    limit: int,
    source_tier: str,
    run_docling: bool,
    run_spec_evidence: bool,
) -> dict[str, Any]:
    refresh = None
    if run_docling or run_spec_evidence:
        refresh = refresh_raw_source_inventory()
    selected = select_raw_sources_for_request(raw_inventory, request, limit)
    result: dict[str, Any] = {
        "enabled": run_docling or run_spec_evidence,
        "raw_inventory": str(raw_inventory),
        "raw_inventory_refresh": refresh,
        "selected_sources": [str(item) for item in selected],
        "docling": None,
        "spec_evidence": None,
        "errors": [],
    }
    if not selected:
        return result
    scripts_dir = ROOT / "sipi_harness" / "scripts"
    if run_docling:
        docling_extensions = {
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
        docling_sources = [item for item in selected if item.suffix.lower() in docling_extensions]
        if not docling_sources:
            result["docling"] = {
                "returncode": 0,
                "skipped": True,
                "reason": "no selected source is supported by Docling",
                "source_count": 0,
            }
        else:
            cmd = [
                "node",
                str(scripts_dir / "run_python.mjs"),
                str(scripts_dir / "ingest_docling_sources.py"),
                *[str(item) for item in docling_sources],
                "--case-dir",
                str(case_dir),
                "--source-tier",
                source_tier,
                "--source-id-prefix",
                "case_",
            ]
            cp = subprocess.run(cmd, cwd=str(ROOT / "sipi_harness"), capture_output=True, text=True)
            result["docling"] = {
                "runner": "node scripts/run_python.mjs",
                "source_count": len(docling_sources),
                "returncode": cp.returncode,
                "stdout": cp.stdout[-4000:],
                "stderr": cp.stderr[-4000:],
            }
            if cp.returncode != 0:
                result["errors"].append("docling_ingest_failed")
            else:
                result["docling_registry"] = refresh_docling_source_registry(case_dir)
    if run_spec_evidence:
        pdfs = [item for item in selected if item.suffix.lower() == ".pdf"]
        if pdfs:
            cmd = [
                sys.executable,
                str(scripts_dir / "extract_spec_evidence.py"),
                "--pdf",
                str(pdfs[0]),
                "--case-dir",
                str(case_dir),
                "--request",
                request,
                "--render",
                "candidates",
            ]
            cp = subprocess.run(cmd, cwd=str(ROOT / "sipi_harness"), capture_output=True, text=True)
            result["spec_evidence"] = {
                "source_pdf": str(pdfs[0]),
                "returncode": cp.returncode,
                "stdout": cp.stdout[-4000:],
                "stderr": cp.stderr[-4000:],
            }
            if cp.returncode != 0:
                result["errors"].append("spec_evidence_extract_failed")
    return result


def meta_list(meta: dict[str, Any], key: str) -> list[Any]:
    value = meta.get(key)
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def build_design_strategy_from_hits(hits: list[WikiHit]) -> dict[str, Any]:
    section_pages: dict[str, list[str]] = {
        "routing": [],
        "stackup": [],
        "si_checks": [],
        "pi_checks": [],
        "validation_benches": [],
    }
    section_claims: dict[str, list[dict[str, Any]]] = {
        "routing": [],
        "stackup": [],
        "si_checks": [],
        "pi_checks": [],
        "validation_benches": [],
    }
    lineage: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    has_blocker = False

    for hit in hits:
        meta = hit.meta or {}
        page_id = str(meta.get("id") or hit.path.stem)
        outputs = [str(item) for item in meta_list(meta, "outputs_to")]
        for output in outputs:
            section = output.replace("design_strategy.", "")
            if section in section_pages and page_id not in section_pages[section]:
                section_pages[section].append(page_id)
            if section in section_claims:
                for snippet in hit.snippets[:3]:
                    claim = {
                        "evidence_page": page_id,
                        "page_type": meta.get("page_type"),
                        "source_tier": meta.get("source_tier"),
                        "confidence": meta.get("confidence"),
                        "text": snippet,
                    }
                    if claim not in section_claims[section]:
                        section_claims[section].append(claim)
        lineage.append(
            {
                "page_id": page_id,
                "page_type": meta.get("page_type"),
                "source_tier": meta.get("source_tier"),
                "source_ids": meta_list(meta, "source_ids"),
                "confidence": meta.get("confidence"),
                "status": meta.get("status"),
                "outputs_to": outputs,
            }
        )
        for idx, item in enumerate(meta_list(meta, "missing_information")):
            has_blocker = True
            missing.append(
                {
                    "id": f"{page_id}_missing_{idx + 1}",
                    "severity": "blocker" if meta.get("source_tier") == "tier_0" else "warning",
                    "required_source_tier": "tier_0" if meta.get("source_tier") == "tier_0" else meta.get("source_tier"),
                    "text": item,
                    "evidence_page": page_id,
                }
            )
        for idx, item in enumerate(meta_list(meta, "evidence_gaps")):
            has_blocker = True
            if isinstance(item, dict):
                missing.append({**item, "evidence_page": page_id})
            else:
                missing.append(
                    {
                        "id": f"{page_id}_evidence_gap_{idx + 1}",
                        "severity": "blocker",
                        "required_source_tier": "tier_0",
                        "text": item,
                        "evidence_page": page_id,
                    }
                )

    return {
        "routing": {"evidence_pages": section_pages["routing"], "evidence_claims": section_claims["routing"][:20]},
        "stackup": {"evidence_pages": section_pages["stackup"], "evidence_claims": section_claims["stackup"][:20]},
        "si_checks": {"evidence_pages": section_pages["si_checks"], "evidence_claims": section_claims["si_checks"][:20]},
        "pi_checks": {"evidence_pages": section_pages["pi_checks"], "evidence_claims": section_claims["pi_checks"][:20]},
        "validation_benches": {
            "evidence_pages": section_pages["validation_benches"],
            "evidence_claims": section_claims["validation_benches"][:20],
        },
        "compliance": {
            "status": "blocked_until_tier_0_spec_loaded" if has_blocker else "strategy_ready",
            "evidence_pages": [
                item["page_id"]
                for item in lineage
                if item.get("page_type") in {"spec_constraint", "validation_metric", "validation_flow"}
            ],
        },
        "missing_spec_values": missing,
        "evidence_lineage": lineage,
    }


def extract_data_rate_gbps(request: str) -> float | None:
    match = re.search(r"(?i)(\d+(?:\.\d+)?)\s*(?:g(?:b|t)?/?s|gbps|gt/s)", request)
    return float(match.group(1)) if match else None


def extract_lane_count(request: str) -> int | None:
    match = re.search(r"(?i)\bx\s*(\d+)\b", request)
    return int(match.group(1)) if match else None


def find_spec_evidence_ids(spec: dict[str, Any], terms: list[str], limit: int = 8) -> list[str]:
    candidates_doc = spec.get("spec_candidates") if isinstance(spec, dict) else None
    if not isinstance(candidates_doc, dict):
        return []
    candidates = candidates_doc.get("candidates")
    if not isinstance(candidates, list):
        return []
    found: list[str] = []
    lowered_terms = [term.lower() for term in terms]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        searchable = " ".join(
            str(candidate.get(key, ""))
            for key in ("id", "label", "kind", "text", "page")
        ).lower()
        if any(term in searchable for term in lowered_terms):
            evidence_id = str(candidate.get("id") or f"page_{candidate.get('page', 'unknown')}")
            if evidence_id not in found:
                found.append(evidence_id)
        if len(found) >= limit:
            break
    return found


SPEC_REQUIREMENT_FAMILIES: dict[str, dict[str, Any]] = {
    "characteristic_impedance": {
        "domain": "frequency_or_tdr",
        "topics": ["impedance", "characteristic impedance", "tdr", "ohm"],
        "required_inputs": ["interconnect geometry", "reference impedance or TDR/solver result"],
        "default_bench": "impedance_or_tdr_check",
    },
    "insertion_loss": {
        "domain": "frequency",
        "topics": ["insertion loss", "vtf loss", "channel loss", "s-parameter", "s parameter", "transfer function", "vtf"],
        "required_inputs": ["Touchstone", "port order", "target frequency or Nyquist frequency"],
        "default_bench": "frequency_domain_loss_check",
    },
    "return_loss": {
        "domain": "frequency",
        "topics": ["return loss", "reflection", "s11", "s22"],
        "required_inputs": ["Touchstone", "port order", "reference impedance"],
        "default_bench": "frequency_domain_return_loss_check",
    },
    "crosstalk": {
        "domain": "frequency",
        "topics": ["crosstalk", "xt", "next", "fext", "aggressor"],
        "required_inputs": ["multiport Touchstone", "victim/aggressor mapping", "port order"],
        "default_bench": "frequency_domain_crosstalk_check",
    },
    "voltage_transfer_function": {
        "domain": "frequency",
        "topics": ["voltage transfer function", "vtf", "receiver voltage", "source voltage", "loading model"],
        "required_inputs": ["channel model", "source/load R and C", "victim/aggressor mapping"],
        "default_bench": "loaded_ac_transfer_check",
    },
    "eye_mask": {
        "domain": "statistical_transient",
        "topics": ["eye mask", "eye diagram", "eye height", "eye width", "rectangular eye", "diamond eye"],
        "required_inputs": ["channel model", "source/load model", "data rate", "mask geometry"],
        "default_bench": "eye_mask_check",
    },
    "ber_contour": {
        "domain": "statistical_transient",
        "topics": ["ber", "bit error rate", "ber contour", "bathtub", "ultra-low ber"],
        "required_inputs": ["statistical eye dataset", "target BER", "contour width/height outputs"],
        "default_bench": "ber_contour_check",
    },
    "skew_jitter": {
        "domain": "timing",
        "topics": ["skew", "jitter", "lane-to-lane skew", "phase margin", "timing margin"],
        "required_inputs": ["lane timing/delay", "jitter model or timing measurement"],
        "default_bench": "timing_margin_check",
    },
    "loading_model": {
        "domain": "bench_definition",
        "topics": ["termination", "tx:", "rx:", "capacitance", "loading model", "source/load", "r_tx", "r_rx", "effective transmitter", "effective receiver"],
        "required_inputs": ["source/load topology", "R/C values", "applicability by data rate"],
        "default_bench": "source_load_model_instantiation",
    },
}


GENERIC_BENCH_CAPABILITIES: dict[str, dict[str, Any]] = {
    "characteristic_impedance": {
        "implementation_id": "generic_impedance_geometry_or_tdr",
        "status": "generic_implementation_available",
        "tool": "geometry_or_tdr_report",
        "required_artifacts": ["stackup", "trace geometry", "reference plane", "optional TDR/field-solver result"],
        "notes": "Usable for a first-pass impedance check; final compliance requires the method requested by the spec.",
    },
    "insertion_loss": {
        "implementation_id": "generic_touchstone_insertion_loss",
        "status": "generic_implementation_available",
        "tool": "touchstone_sparameter_report",
        "required_artifacts": ["verified Touchstone", "port order", "frequency axis"],
        "notes": "Computes insertion-loss curves and requested-frequency samples from S-parameters.",
    },
    "return_loss": {
        "implementation_id": "generic_touchstone_return_loss",
        "status": "generic_implementation_available",
        "tool": "touchstone_sparameter_report",
        "required_artifacts": ["verified Touchstone", "port order", "reference impedance"],
        "notes": "Computes return-loss curves from S-parameters.",
    },
    "crosstalk": {
        "implementation_id": "generic_touchstone_crosstalk",
        "status": "generic_implementation_available",
        "tool": "touchstone_sparameter_report",
        "required_artifacts": ["verified multiport Touchstone", "victim/aggressor lane map", "port order"],
        "notes": "Computes NEXT/FEXT or aggregate crosstalk only when lane mapping is explicit.",
    },
    "skew_jitter": {
        "implementation_id": "generic_route_delay_or_touchstone_group_delay",
        "status": "generic_implementation_available",
        "tool": "route_length_and_group_delay_report",
        "required_artifacts": ["route lengths or verified Touchstone", "lane map", "material velocity assumption"],
        "notes": "Provides delay/skew checks; jitter decomposition still requires a spec/tool-specific model.",
    },
}


def generic_bench_implementation_for(requirement: dict[str, Any]) -> dict[str, Any] | None:
    family = str(requirement.get("metric_name", ""))
    capability = GENERIC_BENCH_CAPABILITIES.get(family)
    if not capability:
        return None
    return {
        "id": capability["implementation_id"],
        "implements_requirement": requirement.get("id"),
        "metric_name": family,
        "status": capability["status"],
        "tool": capability["tool"],
        "required_artifacts": capability["required_artifacts"],
        "source_requirement_evidence_ids": requirement.get("evidence_ids", []),
        "notes": capability["notes"],
    }


def blocked_bench_for(requirement: dict[str, Any]) -> dict[str, Any]:
    metric_name = str(requirement.get("metric_name", "unknown_metric"))
    return {
        "id": f"blocked_{metric_name}",
        "metric_name": metric_name,
        "implements_requirement": requirement.get("id"),
        "status": "blocked_no_generic_implementation",
        "required_action": "select_or_generate_tool_adapter_for_this_metric_family",
        "required_inputs": requirement.get("required_inputs", []),
        "source_requirement_evidence_ids": requirement.get("evidence_ids", []),
        "adapter_synthesis": {
            "status": "adapter_generation_possible_from_requirement_contract",
            "contract_id": f"adapter_contract_{metric_name}",
            "inputs": requirement.get("required_inputs", []),
            "source_evidence_ids": requirement.get("evidence_ids", []),
            "expected_outputs": [
                "machine-readable metric JSON",
                "plot images when applicable",
                "stage report section with source evidence IDs",
                "pass/fail/proxy status without inventing limits",
            ],
            "recommended_flow": adapter_recommendation_for_metric(metric_name),
        },
    }


def adapter_recommendation_for_metric(metric_name: str) -> dict[str, Any]:
    recommendations: dict[str, dict[str, Any]] = {
        "voltage_transfer_function": {
            "tool_family": "ADS_or_SPICE_AC",
            "bench_type": "loaded_ac_transfer",
            "implementation_notes": [
                "Instantiate source/load R/C topology from spec evidence.",
                "Drive the victim lane source and measure receiver/source voltage ratio.",
                "Drive aggressor lanes for crosstalk equations when requested.",
            ],
        },
        "loading_model": {
            "tool_family": "ADS_or_SPICE",
            "bench_type": "source_load_topology",
            "implementation_notes": [
                "Convert extracted Tx/Rx R/C values into reusable bench parameters.",
                "Do not assume termination unless the governing spec evidence says so.",
            ],
        },
        "eye_mask": {
            "tool_family": "ADS_ChannelSim_or_equivalent",
            "bench_type": "statistical_or_transient_eye",
            "implementation_notes": [
                "Use the spec-defined source/load model and data rate.",
                "Overlay the extracted mask geometry on the measured eye/contour.",
                "Report mask pass/fail only when the mask dimensions are tier-0 evidence.",
            ],
        },
        "ber_contour": {
            "tool_family": "ADS_ChannelSim_or_equivalent",
            "bench_type": "ber_contour",
            "implementation_notes": [
                "Enable the BER mode required by the spec target.",
                "Extract contour width/height at the target BER rather than estimating from density.",
            ],
        },
    }
    return recommendations.get(
        metric_name,
        {
            "tool_family": "engineer_selected",
            "bench_type": "custom_metric_adapter",
            "implementation_notes": [
                "Create an adapter only from the extracted requirement contract and reviewed evidence.",
                "Record any missing topology, equation, or loading information as a blocker.",
            ],
        },
    )


def candidate_search_text(candidate: dict[str, Any]) -> str:
    return " ".join(
        str(candidate.get(key, ""))
        for key in ("id", "kind", "label", "text", "page")
    )


def candidate_numeric_values(text: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for match in re.finditer(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?\s*(?:GHz|MHz|GT/s|Gbps|dB|ohm|Ohm|mV|V|pF|fF|ps|ns|UI|mm|um|%)?", text):
        raw = match.group(0).strip()
        if not raw:
            continue
        values.append({"raw": raw, "context": clean_line(text[max(0, match.start() - 55) : match.end() + 55])})
    return values[:20]


def candidate_families(candidate: dict[str, Any]) -> list[str]:
    searchable = candidate_search_text(candidate).lower()
    kind = str(candidate.get("kind", "")).lower()
    families: list[str] = []
    for family, rule in SPEC_REQUIREMENT_FAMILIES.items():
        if any(topic in searchable for topic in rule["topics"]):
            families.append(family)
    if kind in {"ber_or_eye_requirement_candidate", "eye_or_ber_requirement_candidate"}:
        for family in ("eye_mask", "ber_contour"):
            if family not in families:
                families.append(family)
    if kind == "loading_or_transfer_function_candidate":
        for family in ("voltage_transfer_function", "loading_model"):
            if family not in families:
                families.append(family)
    if kind in {"table", "numeric_requirement_candidate"} and any(term in searchable for term in ("loss", "crosstalk", "vtf", "termination")):
        for family in ("insertion_loss", "crosstalk", "voltage_transfer_function"):
            if family not in families:
                families.append(family)
    return families


def build_spec_bench_requirements(request: str, spec: dict[str, Any]) -> dict[str, Any] | None:
    """Build a spec-neutral executable bench requirement inventory.

    The result intentionally avoids interface-specific assumptions. It records
    discovered requirement families, candidate values, evidence IDs, and the
    required bench type. Compliance remains blocked until a downstream adapter
    implements every source-backed requirement with reviewed evidence.
    """
    candidates_doc = spec.get("spec_candidates") if isinstance(spec, dict) else None
    if not isinstance(candidates_doc, dict):
        return None
    candidates = candidates_doc.get("candidates")
    if not isinstance(candidates, list):
        return None

    request_terms = words(request)
    by_family: dict[str, list[dict[str, Any]]] = {family: [] for family in SPEC_REQUIREMENT_FAMILIES}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        searchable = candidate_search_text(candidate)
        families = candidate_families(candidate)
        if not families:
            continue
        score = len(words(searchable) & request_terms)
        if any(term in searchable.lower() for term in ("table", "equation", "figure", "shall", "required", "requirement")):
            score += 2
        evidence = {
            "id": str(candidate.get("id") or f"page_{candidate.get('page', 'unknown')}"),
            "page": candidate.get("page"),
            "kind": candidate.get("kind"),
            "label": candidate.get("label"),
            "text": clean_line(str(candidate.get("text", "")))[:900],
            "reviewer_status": candidate.get("reviewer_status", "unreviewed"),
            "source_id": candidate.get("source_id"),
            "source_pdf": candidate.get("source_pdf") or candidates_doc.get("source_pdf"),
            "numeric_values": candidate_numeric_values(str(candidate.get("text", ""))),
            "score": score,
        }
        for family in families:
            by_family[family].append(evidence)

    metric_requirements: list[dict[str, Any]] = []
    coverage: list[dict[str, Any]] = []
    for family, rule in SPEC_REQUIREMENT_FAMILIES.items():
        evidences = sorted(by_family.get(family, []), key=lambda item: (-int(item.get("score", 0)), str(item.get("id"))))
        if evidences:
            status = "source_candidates_found"
            review_status = "requires_review"
            top = evidences[:12]
            metric_requirements.append(
                {
                    "id": f"spec_req_{family}",
                    "metric_name": family,
                    "domain": rule["domain"],
                    "default_bench": rule["default_bench"],
                    "required_inputs": rule["required_inputs"],
                    "source_tier": "tier_0",
                    "evidence_ids": [item["id"] for item in top],
                    "evidence": top,
                    "pass_fail_equation": "extract_from_evidence_candidates",
                    "status": status,
                    "review_status": review_status,
                    "outputs_to": ["design_strategy.validation_benches"],
                }
            )
        else:
            status = "not_detected"
            review_status = "not_applicable_or_missing"
        coverage.append(
            {
                "metric_name": family,
                "domain": rule["domain"],
                "status": status,
                "review_status": review_status,
                "default_bench": rule["default_bench"],
                "evidence_count": len(evidences),
            }
        )

    if not metric_requirements:
        return None
    source_pdf = ""
    manifest = spec.get("spec_manifest")
    if isinstance(manifest, dict):
        source_pdf = str(manifest.get("source_pdf") or "")
    return {
        "schema_version": "spec_bench_requirements_v1",
        "status": "requirements_extracted_from_tier0_candidates",
        "source_tier": "tier_0",
        "source_pdf": source_pdf,
        "metric_requirements": metric_requirements,
        "coverage_matrix": coverage,
        "policy": [
            "Metric families are extracted from the governing spec evidence, not selected from memory.",
            "Candidate numeric values remain unreviewed until approved or cross-checked.",
            "A Bench stage must implement all detected source-backed metric families or mark the unimplemented families blocked.",
            "Generic S-parameter or geometry implementations may satisfy source-backed requirements only when their required artifacts and equations match the extracted evidence.",
            "Proxy-only results are not compliance results and must not replace source-backed benches.",
        ],
    }


def apply_spec_bench_requirements(strategy: dict[str, Any], requirements: dict[str, Any] | None) -> dict[str, Any]:
    if not requirements:
        return strategy
    strategy = dict(strategy)
    validation = dict(strategy.get("validation_benches", {}))
    generic_benches: list[dict[str, Any]] = []
    blocked_benches: list[dict[str, Any]] = []
    for requirement in requirements.get("metric_requirements", []):
        if not isinstance(requirement, dict):
            continue
        implementation = generic_bench_implementation_for(requirement)
        if implementation:
            generic_benches.append(implementation)
        else:
            blocked_benches.append(blocked_bench_for(requirement))
    validation["spec_requirements"] = requirements
    validation["required_benches"] = requirements.get("metric_requirements", [])
    validation["generic_implementation_benches"] = generic_benches
    validation["blocked_benches"] = blocked_benches
    validation["coverage_matrix"] = requirements.get("coverage_matrix", [])
    validation["bench_execution_status"] = (
        "partially_implemented_by_generic_benches"
        if generic_benches and blocked_benches
        else "implemented_by_generic_benches"
        if generic_benches
        else "blocked_no_generic_implementation"
    )
    if blocked_benches:
        compliance_status = "spec_requirements_extracted_bench_adapter_required"
    elif generic_benches:
        compliance_status = "spec_requirements_extracted_generic_benches_available"
    else:
        compliance_status = "spec_requirements_extracted_but_no_bench_implementation"
    strategy["validation_benches"] = validation
    strategy["compliance"] = {
        **dict(strategy.get("compliance", {})),
        "status": compliance_status,
        "spec_requirements_status": requirements.get("status"),
        "source_backed_metric_count": len(requirements.get("metric_requirements", [])),
        "generic_implemented_metric_count": len(generic_benches),
        "blocked_metric_count": len(blocked_benches),
    }
    return strategy


def wrap(text: str, width: int = 105) -> list[str]:
    lines: list[str] = []
    for raw in str(text).splitlines() or [""]:
        current = raw
        while len(current) > width:
            split_at = current.rfind(" ", 0, width)
            if split_at < 40:
                split_at = width
            lines.append(current[:split_at])
            current = current[split_at:].lstrip()
        lines.append(current)
    return lines


def add_text_page(pdf: PdfPages, title: str, lines: list[str]) -> None:
    fig = plt.figure(figsize=(8.27, 11.69))
    fig.text(0.08, 0.95, title, fontsize=15, weight="bold", va="top")
    y = 0.90
    for line in lines:
        for wrapped in wrap(line):
            if y < 0.07:
                pdf.savefig(fig, bbox_inches="tight")
                plt.close(fig)
                fig = plt.figure(figsize=(8.27, 11.69))
                fig.text(0.08, 0.95, f"{title} (continued)", fontsize=15, weight="bold", va="top")
                y = 0.90
            fig.text(0.08, y, wrapped, fontsize=8.5, va="top", family="monospace")
            y -= 0.023
    pdf.savefig(fig, bbox_inches="tight")
    plt.close(fig)


def yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def write_yaml(path: Path, data: Any, indent: int = 0) -> None:
    def emit(value: Any, level: int) -> list[str]:
        pad = "  " * level
        if isinstance(value, dict):
            if not value:
                return [f"{pad}{{}}"]
            lines: list[str] = []
            for key, item in value.items():
                if isinstance(item, (dict, list)):
                    if not item:
                        lines.append(f"{pad}{key}: {'[]' if isinstance(item, list) else '{}'}")
                    else:
                        lines.append(f"{pad}{key}:")
                        lines.extend(emit(item, level + 1))
                else:
                    lines.append(f"{pad}{key}: {yaml_scalar(item)}")
            return lines
        if isinstance(value, list):
            if not value:
                return [f"{pad}[]"]
            lines = []
            for item in value:
                if isinstance(item, (dict, list)):
                    lines.append(f"{pad}-")
                    lines.extend(emit(item, level + 1))
                else:
                    lines.append(f"{pad}- {yaml_scalar(item)}")
            return lines
        return [f"{pad}{yaml_scalar(value)}"]

    path.write_text("\n".join(emit(data, indent)) + "\n", encoding="utf-8")


def strategy_lines(strategy: dict[str, Any]) -> list[str]:
    if not strategy:
        return ["No strategy JSON supplied. Use this report as a wiki-derived planning scaffold."]
    lines = []
    for key in ("case", "application", "package", "data_rate_gbps", "lanes", "channel_length_mm"):
        if key in strategy:
            lines.append(f"{key}: {strategy[key]}")
    design = strategy.get("design", {})
    if isinstance(design, dict):
        lines.append("")
        lines.append("Design constraints:")
        for key, value in design.items():
            if isinstance(value, (str, int, float, bool)):
                lines.append(f"- {key}: {value}")
    testbenches = strategy.get("testbenches", [])
    if isinstance(testbenches, list) and testbenches:
        lines.append("")
        lines.append("Planned testbenches:")
        for bench in testbenches:
            if isinstance(bench, dict):
                lines.append(f"- {bench.get('name', 'bench')}: {bench.get('purpose', '')}")
    return lines


def intake_lines(intake: dict[str, Any]) -> list[str]:
    if not intake:
        return ["No knowledge intake JSON supplied."]
    lines = []
    for key in ("case", "request", "web_research_registry", "user_reference_registry"):
        if key in intake:
            lines.append(f"{key}: {intake[key]}")
    rules = intake.get("fusion_rules", [])
    if isinstance(rules, list) and rules:
        lines.extend(["", "Fusion rules:"])
        lines.extend(f"- {rule}" for rule in rules)
    return lines


def spec_evidence_lines(spec: dict[str, Any]) -> list[str]:
    if not spec:
        return ["No spec evidence JSON supplied."]
    if "spec_manifest" not in spec and "source_pdf" in spec:
        return [
            f"source_pdf: {spec.get('source_pdf')}",
            f"page: {spec.get('page')}",
            f"reviewer_status: {spec.get('reviewer_status')}",
            f"extraction_method: {spec.get('extraction_method')}",
        ]
    manifest = spec.get("spec_manifest", {})
    inventory = spec.get("spec_inventory", {})
    candidates = spec.get("spec_candidates", {})
    queue = spec.get("spec_review_queue", {})
    lines = [
        f"spec_evidence_dir: {spec.get('spec_evidence_dir', '(not directory bundle)')}",
        f"source_pdf: {manifest.get('source_pdf', '(missing)')}",
        f"source_sha256: {manifest.get('source_sha256', '(missing)')}",
        f"processed_pages: {inventory.get('processed_pages', manifest.get('processed_pages', '(missing)'))}",
        f"candidate_count: {candidates.get('candidate_count', 0)}",
        f"review_status: {queue.get('status', 'review_required')}",
        "",
        "Top ranked pages:",
    ]
    for page in (inventory.get("ranked_pages") or [])[:10]:
        lines.append(
            f"- page {page.get('page')} score={page.get('score')} candidates={page.get('candidate_count')} render={page.get('render_path')}"
        )
    lines.extend(["", "Candidate kinds:"])
    kind_counts: dict[str, int] = {}
    for candidate in candidates.get("candidates", []):
        kind = str(candidate.get("kind", "unknown"))
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
    for kind, count in sorted(kind_counts.items()):
        lines.append(f"- {kind}: {count}")
    return lines


def generate_report(
    case_dir: Path,
    case_name: str,
    request: str,
    wiki_dir: Path,
    strategy_path: Path | None,
    spec_evidence_path: Path | None,
    knowledge_intake_path: Path | None = None,
    source_json_path: Path | None = None,
    auto_ingest_sources: bool = False,
    auto_docling: bool = False,
    auto_spec_evidence: bool = False,
    auto_ingest_limit: int = 1,
    auto_source_tier: str = "tier_0",
    raw_inventory_path: Path | None = None,
    output: Path | None = None,
) -> dict[str, str]:
    case_dir.mkdir(parents=True, exist_ok=True)
    strategy_dir = case_dir / "strategy"
    strategy_dir.mkdir(parents=True, exist_ok=True)
    output = output or strategy_dir / "pre_pcb_wiki_design_strategy_report.pdf"
    md_output = output.with_suffix(".md")
    json_output = output.with_suffix(".json")
    yaml_output = strategy_dir / "design_strategy.yaml"

    raw_inventory_path = raw_inventory_path or ROOT / "sipi_harness" / "data" / "raw_source_inventory.json"
    auto_ingest = run_auto_ingest(
        case_dir=case_dir,
        request=request,
        raw_inventory=raw_inventory_path,
        limit=auto_ingest_limit,
        source_tier=auto_source_tier,
        run_docling=auto_ingest_sources or auto_docling,
        run_spec_evidence=auto_ingest_sources or auto_spec_evidence,
    )
    if not spec_evidence_path and (case_dir / "spec_evidence").exists():
        spec_evidence_path = case_dir / "spec_evidence"

    strategy = read_json(strategy_path)
    spec = read_json(spec_evidence_path)
    intake = read_json(knowledge_intake_path)
    query_text = " ".join(
        [
            request,
            json.dumps(strategy, ensure_ascii=False),
            json.dumps(spec, ensure_ascii=False),
            json.dumps(intake, ensure_ascii=False),
        ]
    )
    wiki_hits = collect_wiki_hits(wiki_dir, query_text)
    source_json_path = source_json_path or ROOT / "sipi_harness" / "data" / "sources.json"
    source_hits = collect_source_hits(source_json_path, query_text)
    case_docling_root = case_dir / "knowledge_intake" / "processed" / "docling"
    global_docling_root = ROOT / "sipi_harness" / "wiki" / "raw" / "extracted_evidence" / "docling"
    direct_docling_hits = [
        *collect_docling_hits_from_root(case_docling_root, query_text),
        *collect_docling_hits_from_root(global_docling_root, query_text),
    ]
    spec_hits = collect_spec_evidence_hits(spec, query_text)
    combined: dict[str, WikiHit] = {}
    for hit in [*wiki_hits, *source_hits, *direct_docling_hits, *spec_hits]:
        key = str(hit.meta.get("id") or hit.path)
        if key not in combined or hit.score > combined[key].score:
            combined[key] = hit
    hits = sorted(combined.values(), key=lambda hit: (-hit.score, str(hit.path)))[:24]
    design_strategy = build_design_strategy_from_hits(hits)
    spec_bench_requirements = build_spec_bench_requirements(query_text, spec)
    design_strategy = apply_spec_bench_requirements(design_strategy, spec_bench_requirements)
    raw_source_usage = {
        "searched_sources_json": bool(source_json_path and source_json_path.exists()),
        "source_hit_count": len(source_hits),
        "docling_hit_count": len(
            [
                hit
                for hit in [*source_hits, *direct_docling_hits]
                if str(hit.meta.get("page_type", "")).startswith("docling")
            ]
        ),
        "case_docling_hit_count": len(direct_docling_hits),
        "spec_evidence_hit_count": len(spec_hits),
        "raw_group_hit_count": len([hit for hit in source_hits if hit.meta.get("page_type") == "raw_source_group"]),
        "policy": [
            "raw_source_group hits prove only that local source files exist",
            "docling_chunk hits provide candidate content evidence but remain unreviewed until promoted",
            "spec_evidence_candidate hits come from case-local PDF extraction and require review before compliance use",
            "numeric compliance thresholds still require reviewed tier-0 spec evidence",
        ],
    }
    blocker_count = len(
        [
            item
            for item in design_strategy.get("missing_spec_values", [])
            if str(item.get("severity", "")).lower() == "blocker"
        ]
    )
    compliance_status = str(design_strategy.get("compliance", {}).get("status", ""))
    pre_pcb_status = (
        "pre_pcb_strategy_blocked"
        if blocker_count or compliance_status.startswith("blocked")
        else "pre_pcb_strategy_ready"
    )
    pre_pcb_gate_status = (
        "blocked_missing_tier0_or_required_evidence"
        if pre_pcb_status == "pre_pcb_strategy_blocked"
        else "required_before_layout"
    )

    summary = {
        "case": case_name,
        "request": request,
        "status": pre_pcb_status,
        "wiki_dir": str(wiki_dir),
        "strategy_json": str(strategy_path) if strategy_path else None,
        "spec_evidence": str(spec_evidence_path) if spec_evidence_path else None,
        "knowledge_intake": str(knowledge_intake_path) if knowledge_intake_path else None,
        "source_json": str(source_json_path) if source_json_path else None,
        "auto_ingest": auto_ingest,
        "spec_adapter_policy": {
            "built_in_adapters": "not_shipped_in_default_runtime",
            "note": "Source-backed requirements remain in generic_implementation_benches or blocked_benches. Missing spec benches must be handled by case-local adapter planning and implementation.",
        },
        "spec_evidence_status": {
            "provided": bool(spec),
            "bundle": bool(spec.get("spec_manifest")),
            "candidate_count": spec.get("spec_candidates", {}).get("candidate_count") if isinstance(spec.get("spec_candidates"), dict) else None,
            "review_status": spec.get("spec_review_queue", {}).get("status") if isinstance(spec.get("spec_review_queue"), dict) else None,
            "bench_requirement_count": len((spec_bench_requirements or {}).get("metric_requirements", [])),
            "bench_requirement_status": (spec_bench_requirements or {}).get("status"),
        },
        "output_pdf": str(output),
        "wiki_hits": [
            {
                "path": str(hit.path),
                "title": hit.title,
                "score": hit.score,
                "id": hit.meta.get("id"),
                "page_type": hit.meta.get("page_type"),
                "source_tier": hit.meta.get("source_tier"),
                "source_ids": meta_list(hit.meta, "source_ids"),
                "outputs_to": meta_list(hit.meta, "outputs_to"),
                "snippets": hit.snippets,
            }
            for hit in hits
        ],
        "raw_source_usage": raw_source_usage,
        "design_strategy": design_strategy,
        "pre_pcb_gate": {
            "status": pre_pcb_gate_status,
            "checks": [
                "spec evidence is extracted and traceable",
                "web research and user references are collected or explicitly waived",
                "knowledge intake is fused into the design strategy",
                "design constraints are listed",
                "geometry sanity gates are defined before PCB generation",
                "EM and circuit verification benches are named before layout",
                "final reports and pass/fail metrics are identified",
            ],
        },
        "stage_reports_required": [
            "00_strategy_report.pdf",
            "01_pcb_package_report.pdf",
            "02_em_solve_report.pdf",
            "03_bench_report.pdf",
        ],
    }

    md_lines = [
        f"# {case_name} Pre-PCB Wiki Design Strategy Report",
        "",
        f"- Strategy status: `{pre_pcb_status}`",
        f"- Pre-PCB gate: `{pre_pcb_gate_status}`",
        f"- Blocking values: `{blocker_count}`",
        "",
        "## Request",
        request or "(not provided)",
        "",
        "## Strategy",
        *strategy_lines(strategy),
        "",
        "## Knowledge Intake",
        *intake_lines(intake),
        "",
        "## Automatic Source Ingest",
        f"- Enabled: {auto_ingest.get('enabled')}",
        f"- Selected sources: {len(auto_ingest.get('selected_sources', []))}",
        *[f"  - {item}" for item in auto_ingest.get("selected_sources", [])],
        f"- Errors: {', '.join(auto_ingest.get('errors', [])) or '(none)'}",
        "",
        "## Spec Evidence",
        *spec_evidence_lines(spec),
        "",
        "## Wiki Evidence Used",
    ]
    for hit in hits:
        md_lines.extend(["", f"### {hit.title}", f"- Source: `{hit.path}`", f"- Score: {hit.score}"])
        for snippet in hit.snippets:
            md_lines.append(f"- {snippet}")
    md_lines.extend(
        [
            "",
            "## Evidence-Mapped Design Strategy",
            f"- Compliance status: {design_strategy['compliance']['status']}",
            f"- Routing evidence: {', '.join(design_strategy['routing']['evidence_pages']) or '(none)'}",
            f"- Stackup evidence: {', '.join(design_strategy['stackup']['evidence_pages']) or '(none)'}",
            f"- SI check evidence: {', '.join(design_strategy['si_checks']['evidence_pages']) or '(none)'}",
            f"- Validation bench evidence: {', '.join(design_strategy['validation_benches']['evidence_pages']) or '(none)'}",
            f"- Source-backed bench requirements: {len(design_strategy['validation_benches'].get('required_benches', []))}",
            f"- Generic implementation benches: {len(design_strategy['validation_benches'].get('generic_implementation_benches', []))}",
            f"- Blocked benches needing adapter/topology: {len(design_strategy['validation_benches'].get('blocked_benches', []))}",
            f"- Missing/blocking values: {len(design_strategy['missing_spec_values'])}",
            "",
            "## Spec Bench Requirement Coverage",
            *[
                f"- {item.get('metric_name')}: {item.get('status')} / {item.get('default_bench')} / evidence={item.get('evidence_count')}"
                for item in design_strategy["validation_benches"].get("coverage_matrix", [])
            ],
            "",
            "## Pre-PCB Gate",
            "- Do not generate or modify PCB geometry until this report exists for the active case.",
            "- The PCB stage must carry these strategy assumptions into the manifest and design report.",
            "- If spec evidence, figure extraction, geometry gates, or final verification benches are missing, mark the case as planning/proxy.",
        ]
    )
    md_output.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    json_output.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    write_yaml(yaml_output, summary)

    with PdfPages(output) as pdf:
        add_text_page(
            pdf,
            "Pre-PCB Wiki Design Strategy",
            [
                f"Case: {case_name}",
                f"Request: {request or '(not provided)'}",
                f"Wiki directory: {wiki_dir}",
                f"Strategy JSON: {strategy_path or '(not provided)'}",
                f"Spec evidence: {spec_evidence_path or '(not provided)'}",
                f"Knowledge intake: {knowledge_intake_path or '(not provided)'}",
                f"Source registry: {source_json_path or '(not provided)'}",
                f"Auto source ingest: {auto_ingest.get('enabled')}",
                f"Auto selected sources: {len(auto_ingest.get('selected_sources', []))}",
                "",
                "Purpose:",
                "This report captures the web/user-reference/wiki-derived design strategy before PCB/package layout starts.",
                "It is a planning gate, not a compliance result.",
                "",
                "Raw source policy:",
                "Files under wiki/raw are useful only after they are registered and, for content-level retrieval, converted by Docling or spec extraction.",
                "Raw source group metadata alone must not become a design rule or compliance threshold.",
            ],
        )
        add_text_page(pdf, "Knowledge Intake", intake_lines(intake))
        add_text_page(pdf, "Spec Evidence", spec_evidence_lines(spec))
        add_text_page(
            pdf,
            "Spec Bench Requirement Coverage",
            [
                f"{item.get('metric_name')}: {item.get('status')} | {item.get('default_bench')} | evidence={item.get('evidence_count')}"
                for item in design_strategy["validation_benches"].get("coverage_matrix", [])
            ]
            or ["No spec-derived bench requirement coverage was generated."],
        )
        add_text_page(pdf, "Strategy Inputs", strategy_lines(strategy))
        for hit in hits:
            lines = [f"Source: {hit.path}", f"Score: {hit.score}", ""]
            lines.extend(f"- {snippet}" for snippet in hit.snippets)
            add_text_page(pdf, f"Wiki: {hit.title}", lines)
        add_text_page(
            pdf,
            "Pre-PCB Gate Checklist",
            [
                "[ ] Governing spec evidence extracted with page/figure/table identifiers.",
                "[ ] Web research collected and summarized with URLs, access dates, and reusable claims.",
                "[ ] User-provided/user-approved references registered and extracted where needed.",
                "[ ] Web research and user references fused into the case design strategy.",
                "[ ] Figure-derived maps visually checked or marked proxy.",
                "[ ] Stackup, materials, layer count, and geometry constraints recorded.",
                "[ ] Pad/via/trace clearance and routed-length/delay-skew gates defined.",
                "[ ] EM solver port intent and frequency coverage defined.",
                "[ ] Frequency-domain/transient-domain benchmark benches, exact equations, loading models, and report outputs defined.",
                "[ ] Case manifest will record whether each stage is exact, estimated, or proxy.",
            ],
        )
    return {"pdf": str(output), "markdown": str(md_output), "json": str(json_output), "yaml": str(yaml_output)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a pre-PCB wiki-derived design strategy PDF.")
    parser.add_argument("--case-dir", required=True)
    parser.add_argument("--case-name", default=None)
    parser.add_argument("--request", default="")
    parser.add_argument(
        "--request-file",
        default=None,
        help="Optional UTF-8 text file containing the request. Prefer this for non-ASCII prompts on Windows.",
    )
    parser.add_argument("--wiki-dir", default=str(ROOT / "sipi_harness" / "wiki"))
    parser.add_argument("--strategy-json", default=None)
    parser.add_argument("--spec-evidence", default=None)
    parser.add_argument("--knowledge-intake", default=None)
    parser.add_argument(
        "--source-json",
        default=str(ROOT / "sipi_harness" / "data" / "sources.json"),
        help="Optional source registry generated from raw/docling intake.",
    )
    parser.add_argument(
        "--auto-ingest-sources",
        action="store_true",
        help="Select request-relevant raw sources, run Docling candidate ingest, and extract PDF spec evidence before strategy retrieval.",
    )
    parser.add_argument(
        "--auto-docling",
        action="store_true",
        help="Select request-relevant raw sources and run Docling candidate ingest before strategy retrieval.",
    )
    parser.add_argument(
        "--auto-spec-evidence",
        action="store_true",
        help="Select the best request-relevant PDF raw source and run spec evidence extraction before strategy retrieval.",
    )
    parser.add_argument("--auto-ingest-limit", type=int, default=1)
    parser.add_argument("--auto-source-tier", default="tier_0", choices=["tier_0", "tier_1", "tier_2", "tier_3"])
    parser.add_argument(
        "--raw-inventory",
        default=str(ROOT / "sipi_harness" / "data" / "raw_source_inventory.json"),
        help="Raw source inventory generated by npm run register:raw-sources.",
    )
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    case_dir = Path(args.case_dir).resolve()
    request = args.request
    if args.request_file:
        request = Path(args.request_file).read_text(encoding="utf-8-sig").strip()
    result = generate_report(
        case_dir=case_dir,
        case_name=args.case_name or case_dir.name,
        request=request,
        wiki_dir=Path(args.wiki_dir).resolve(),
        strategy_path=Path(args.strategy_json).resolve() if args.strategy_json else None,
        spec_evidence_path=Path(args.spec_evidence).resolve() if args.spec_evidence else None,
        knowledge_intake_path=Path(args.knowledge_intake).resolve() if args.knowledge_intake else None,
        source_json_path=Path(args.source_json).resolve() if args.source_json else None,
        auto_ingest_sources=args.auto_ingest_sources,
        auto_docling=args.auto_docling,
        auto_spec_evidence=args.auto_spec_evidence,
        auto_ingest_limit=args.auto_ingest_limit,
        auto_source_tier=args.auto_source_tier,
        raw_inventory_path=Path(args.raw_inventory).resolve() if args.raw_inventory else None,
        output=Path(args.output).resolve() if args.output else None,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
