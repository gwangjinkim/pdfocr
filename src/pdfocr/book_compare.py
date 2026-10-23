"""Reproducible, explicitly provisional comparison of a small reviewed corpus."""

from __future__ import annotations

import difflib
import html
import json
import re
import unicodedata
from pathlib import Path

from rapidfuzz.distance import Levenshtein

from .util import file_hash, read_json, write_json


def content_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("ſ", "s")
    text = re.sub(r"^\s*(?:[-—–]\s*)?\d{1,4}(?:\s*[-—–])?\s*$", "", text, flags=re.M)
    text = re.sub(r"(?<=\w)[-¬\u00ad]\s*\n\s*(?=\w)", "", text)
    # Only presentation markup present in this plain-prose corpus.
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)
    text = text.replace("*", "").replace("_", "")
    return " ".join(text.split())


def rates(truth: str, prediction: str) -> dict:
    ce = Levenshtein.distance(truth, prediction)
    we = Levenshtein.distance(truth.split(), prediction.split())
    return {
        "character_edits": ce,
        "reference_characters": len(truth),
        "word_edits": we,
        "reference_words": len(truth.split()),
        "cer": ce / len(truth),
        "wer": we / len(truth.split()),
    }


def review(document: Path, runs: list[Path], references: Path, repairs: dict[str, Path], out: Path):
    doc = read_json(document / "document.json")
    data = {
        "source_sha256": doc["source_sha256"],
        "pages": [p["page"] for p in doc["pages"]],
        "reference_status": "provisional assistant visual transcription; no independent human gold review",
        "scope": "Two historical German prose pages, one inter-page word split. Not a general benchmark.",
        "normalization": "NFC; long s→s; page-number-only lines and Markdown emphasis removed; within-page line-end hyphens joined; whitespace collapsed. Case, spelling and punctuation count. Inter-page hyphen kept for per-page scoring.",
        "models": [],
    }
    fragments = []
    for run in runs:
        manifest = read_json(run / "manifest.json")
        if manifest["status"] != "complete":
            raise ValueError(f"Incomplete run cannot be ranked: {run}")
        name = manifest["config"]["model_name"]
        pages = []
        truths = []
        predictions = []
        for p in doc["pages"]:
            idx = p["page"]
            value = read_json(run / f"page-{idx:04d}.json")
            ref = references / f"page-{idx:04d}.txt"
            truth = content_text(ref.read_text())
            prediction = content_text(value["markdown"])
            truths.append(truth)
            predictions.append(prediction)
            page = {
                "page": idx,
                "reference_sha256": file_hash(ref),
                **rates(truth, prediction),
                "seconds": value["seconds"],
                "possibly_truncated": value.get("possibly_truncated", False),
            }
            pages.append(page)
            differences = "\n".join(
                difflib.unified_diff(
                    truth.split(),
                    prediction.split(),
                    fromfile="reference words",
                    tofile=name + " words",
                    lineterm="",
                )
            )
            fragments.append(
                f"<details><summary>{html.escape(name)} — PDF page {idx}: word diff</summary><pre>{html.escape(differences)}</pre></details>"
            )
        # Aggregate edits are sums per page so page boundaries cannot mask omissions.
        ce = sum(p["character_edits"] for p in pages)
        we = sum(p["word_edits"] for p in pages)
        row = {
            "name": name,
            "run": str(run.resolve()),
            "config": manifest["config"],
            "pages": pages,
            "cer": ce / sum(p["reference_characters"] for p in pages),
            "wer": we / sum(p["reference_words"] for p in pages),
            "inference_seconds": sum(p["seconds"] for p in pages),
            "worker_seconds": manifest.get("process", {}).get("seconds"),
            "raw_page_end": read_json(run / "page-0009.json")["markdown"][-160:],
            "raw_next_start": read_json(run / "page-0010.json")["markdown"][:160],
        }
        if name in repairs:
            repair = repairs[name]
            decisions = [
                json.loads(line)
                for line in repair.with_suffix(".boundaries.jsonl").read_text().splitlines()
                if line.strip()
            ]
            repaired = content_text(repair.read_text())
            row["boundary"] = {
                "decisions": decisions,
                "expected_word": "ansteckenden",
                "word_present": "ansteckenden" in repaired,
                "duplicated_suffix": "ansteckendenden" in repaired,
                "repair_file": str(repair.resolve()),
                "seconds": read_json(repair.with_suffix(".process.json"))["seconds"],
            }
        data["models"].append(row)
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "comparison.json", data)
    rows = "".join(
        f"<tr><td>{html.escape(m['name'])}</td><td>{100 * m['cer']:.2f}%</td><td>{100 * m['wer']:.2f}%</td><td>{m['inference_seconds']:.1f}s</td><td>{m['worker_seconds']:.1f}s</td><td>{'yes' if m.get('boundary', {}).get('word_present') else 'no'}</td></tr>"
        for m in data["models"]
    )
    cards = []
    import base64
    import io

    from PIL import Image

    for page in doc["pages"]:
        with Image.open(document / page["image"]) as im:
            im.thumbnail((1500, 1500))
            buf = io.BytesIO()
            im.convert("RGB").save(buf, format="JPEG", quality=85)
        image64 = base64.b64encode(buf.getvalue()).decode()
        cells = [
            f'<div><h3>Source PDF page {page["page"]}</h3><img src="data:image/jpeg;base64,{image64}"></div>'
        ]
        for run in runs:
            manifest = read_json(run / "manifest.json")
            value = read_json(run / f"page-{page['page']:04d}.json")
            cells.append(
                f"<div><h3>{html.escape(manifest['config']['model_name'])}</h3><pre>{html.escape(value['markdown'])}</pre></div>"
            )
        cards.append('<section class="pages">' + "".join(cells) + "</section>")
    title = "Local OCR comparison — Archive.org 10289757bsb, PDF 9–10"
    body = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{title}</title><style>body{{font:16px/1.5 system-ui;max-width:1600px;margin:30px auto;padding:16px;color:#182533;background:#f8f9fb}}table{{border-collapse:collapse}}th,td{{padding:10px;border:1px solid #ccd2da;text-align:left}}.pages{{display:flex;gap:16px;overflow:auto;margin:30px 0;align-items:start}}.pages>div{{flex:0 0 480px;background:white;padding:16px;box-sizing:border-box}}img{{width:100%}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 monospace}}summary{{cursor:pointer;padding:8px}}</style><h1>{title}</h1><p>{html.escape(data["scope"])} References: {html.escape(data["reference_status"])}.</p><p>Character/word edit rates below are content-normalized, lower is better. Inference includes layout and region OCR where applicable. Worker wall time includes model loading; TeleOCR loads once per page in this CLI adapter. These timings are not throughput benchmarks.</p><table><tr><th>Model</th><th>CER</th><th>WER</th><th>2-page inference</th><th>Worker wall</th><th>Repaired target word</th></tr>{rows}</table><p>All models use the same prepared source pixels with model-specific resizing. Raw outputs are escaped, never executed. Inspect the text and scans; a low edit rate does not prove correct page flow.</p>{"".join(cards)}<h2>Word-level differences</h2>{"".join(fragments)}<h2>Boundary evidence</h2><pre>{html.escape(json.dumps({m["name"]: m.get("boundary") for m in data["models"]}, ensure_ascii=False, indent=2))}</pre></html>"""
    (out / "comparison.html").write_text(body)
    return data
