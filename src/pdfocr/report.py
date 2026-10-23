from __future__ import annotations

import html
import re
import unicodedata
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from .util import atomic_text, file_hash, read_json, write_json


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


def evaluate(run: Path, references: Path) -> dict:
    manifest = read_json(run / "manifest.json")
    scores, cerrors, chars, werrors, words = [], 0, 0, 0, 0
    for page in manifest["pages"]:
        name = f"page-{page['page']:04d}"
        candidates = [references / f"{name}.md", references / f"{name}.txt"]
        ref = next((p for p in candidates if p.exists()), None)
        if ref is None:
            scores.append({"page": page["page"], "status": "missing_reference"})
            continue
        value = read_json(run / page["result"])
        truth = normalize(ref.read_text())
        predicted = normalize(value.get("markdown", ""))
        ce = Levenshtein.distance(truth, predicted)
        we = Levenshtein.distance(truth.split(), predicted.split())
        cerrors += ce
        chars += len(truth)
        werrors += we
        words += len(truth.split())
        scores.append(
            {
                "page": page["page"],
                "status": page["status"],
                "reference_sha256": file_hash(ref),
                "character_edits": ce,
                "reference_characters": len(truth),
                "word_edits": we,
                "cer": ce / len(truth) if truth else None,
                "wer": we / len(truth.split()) if truth.split() else None,
            }
        )
    result = {
        "metric": "NFC + whitespace normalized character/word edit rates; lower is better",
        "caveat": "Markup differences count as edits; these are not semantic accuracy or table-structure scores. Rates may exceed 1.",
        "cer": cerrors / chars if chars else None,
        "wer": werrors / words if words else None,
        "reference_coverage": sum(p["status"] != "missing_reference" for p in scores),
        "pages": scores,
    }
    write_json(run / "evaluation.json", result)
    return result


def quality(run: Path) -> dict:
    manifest = read_json(run / "manifest.json")
    pages = []
    for record in manifest["pages"]:
        result = read_json(run / record["result"])
        text = result.get("markdown", "")
        flags = []
        if record["status"] != "ok":
            flags.append("failed")
        if not text.strip():
            flags.append("empty_output")
        if result.get("possibly_truncated"):
            flags.append("possibly_truncated")
        lines = [s.strip() for s in text.splitlines() if len(s.strip()) > 20]
        if len(lines) > 10 and len(set(lines)) < len(lines) * 0.5:
            flags.append("heavy_repetition")
        if len(re.findall(r"```", text)) % 2:
            flags.append("unclosed_code_fence")
        pages.append({"page": record["page"], "flags": flags, "characters": len(text)})
    result = {
        "status": manifest["status"],
        "pages": pages,
        "caveat": "Heuristics identify review candidates, not proof of correctness. Visual comparison and ground truth remain necessary.",
    }
    write_json(run / "quality.json", result)
    return result


def compare(document: Path) -> Path:
    document = document.resolve()
    doc = read_json(document / "document.json")
    runs = sorted((document / "runs").glob("*/manifest.json"))
    cards = []
    for page in doc["pages"]:
        cells = [
            f'<div class="cell"><h3>pdfrune source raster</h3><img alt="Source page {page["page"]}" src="{html.escape((document / page["image"]).as_uri(), quote=True)}"></div>'
        ]
        for path in runs:
            manifest = read_json(path)
            run = path.parent
            quality(run)
            record = next((r for r in manifest["pages"] if r["page"] == page["page"]), None)
            value = read_json(run / record["result"]) if record else {}
            config = manifest["config"]
            label = f"{config['model_name']} / {config['backend']} / {config['model']['mode']}"
            status = record["status"] if record else "missing"
            cells.append(
                f'<div class="cell"><h3>{html.escape(label)}</h3><p>{html.escape(status)}</p><pre>{html.escape(value.get("markdown", value.get("error", "No output")))}</pre><p><a href="{html.escape((run / "reading.md").as_uri(), quote=True)}">Reading copy</a> · <a href="{html.escape((run / "boundaries.json").as_uri(), quote=True)}">Boundary review</a></p></div>'
            )
        cards.append(
            f'<section data-page="{page["page"]}"><h2>Source page {page["page"]}</h2><div class="row">{"".join(cells)}</div></section>'
        )
    options = '<option value="all">All pages</option>' + "".join(
        f"<option>{p['page']}</option>" for p in doc["pages"]
    )
    body = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>PDF OCR comparison</title><style>
body{font:16px system-ui;background:#f6f7f9;color:#172030;margin:24px}header{position:sticky;top:0;background:#f6f7f9;padding:8px 0;z-index:1}h1{margin:0}p{line-height:1.5}.row{display:flex;gap:16px;overflow:auto;align-items:flex-start}.cell{flex:0 0 480px;background:white;border:1px solid #d8dde5;border-radius:10px;padding:16px;box-sizing:border-box}.cell img{width:100%}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace}h3{font-size:15px}select{font:inherit;padding:8px}section{margin-bottom:36px}a{color:#1353a5}[hidden]{display:none}
</style><header><h1>PDF OCR comparison</h1><p>Raw text is escaped for safety. Compare it to the source raster; this viewer does not execute model HTML or Mermaid. Check source rendering against your original PDF first.</p><label>Page <select id="page">OPTIONS</select></label></header>CARDS<script>
document.getElementById('page').addEventListener('change',e=>document.querySelectorAll('section').forEach(s=>s.hidden=e.target.value!=='all'&&s.dataset.page!==e.target.value));
</script></html>""".replace("OPTIONS", options).replace("CARDS", "".join(cards))
    path = document / "comparison.html"
    atomic_text(path, body)
    return path
