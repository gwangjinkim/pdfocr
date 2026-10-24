"""Score frozen Gemma outputs and build a standalone, escaped comparison."""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import re
from pathlib import Path

from PIL import Image

from pdfocr.book_compare import content_text, rates
from pdfocr.util import file_hash, read_json, write_json
from pdfocr.visual_repair import norm

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "workspace/gemma"
REFS = ROOT / "datasets/expanded/references"
MODELS = ["gemma3-12b", "gemma4-12b"]
BOOKS = ["10289757bsb", "makrobiotikoderd00hufeuoft"]


def aggregate(rows):
    return {
        "scored_units": len(rows),
        "character_edits": sum(r["character_edits"] for r in rows),
        "reference_characters": sum(r["reference_characters"] for r in rows),
        "word_edits": sum(r["word_edits"] for r in rows),
        "reference_words": sum(r["reference_words"] for r in rows),
        "cer": sum(r["character_edits"] for r in rows)
        / sum(r["reference_characters"] for r in rows),
        "wer": sum(r["word_edits"] for r in rows) / sum(r["reference_words"] for r in rows),
    }


def score_matched(folder, model):
    rows = []
    outputs = []
    for bid in BOOKS:
        files = sorted((folder / model / bid).glob("page-*.json"))
        assert len(files) == 8, (model, bid, "missing pages")
        for path in files:
            value = read_json(path)
            assert value["status"] == "ok", path
            outputs.append(value)
            number = value["pages"][0]
            reference = REFS / bid / f"page-{number:04d}.txt"
            if reference.exists():
                rows.append(
                    {
                        "book": bid,
                        "page": number,
                        "reference_sha256": file_hash(reference),
                        **rates(
                            content_text(reference.read_text()), content_text(value["markdown"])
                        ),
                    }
                )
    return {
        "model": model,
        **aggregate(rows),
        "pages": rows,
        "books": {bid: aggregate([r for r in rows if r["book"] == bid]) for bid in BOOKS},
        "seconds": sum(x["seconds"] for x in outputs),
        "truncated_pages": [x["pages"][0] for x in outputs if x["possibly_truncated"]],
    }


def score_legacy(folder, model):
    rows, batches = [], []
    for bid in BOOKS:
        files = sorted((folder / model / bid).glob("page-*.json"))
        assert len(files) == 2, (model, bid, "missing batches")
        for path in files:
            value = read_json(path)
            assert value["status"] == "ok", path
            batches.append(
                {
                    "book": bid,
                    "pages": value["pages"],
                    "seconds": value["seconds"],
                    "characters": len(value["markdown"]),
                    "eval_count": value["response"].get("eval_count"),
                    "done_reason": value["response"].get("done_reason"),
                    "thinking_characters": len(value["response"]["message"].get("thinking", "")),
                }
            )
            refs = [REFS / bid / f"page-{n:04d}.txt" for n in value["pages"]]
            if not all(p.exists() for p in refs):
                continue
            truth = content_text("\n\n".join(p.read_text() for p in refs))
            rows.append(
                {
                    "book": bid,
                    "pages": value["pages"],
                    "reference_sha256s": [file_hash(p) for p in refs],
                    **rates(truth, content_text(value["markdown"])),
                }
            )
    return {
        "model": model,
        **aggregate(rows),
        "batches": batches,
        "scores": rows,
        "books": {bid: aggregate([r for r in rows if r["book"] == bid]) for bid in BOOKS},
    }


def verify_map(path):
    mapping = read_json(path.with_suffix(".pages.json"))
    text = path.read_text()
    raw = Path(mapping["raw_file"]).read_text()
    cursor = 0
    for span in mapping["spans"]:
        assert span["output_start"] == cursor
        if span["kind"] == "source":
            assert (
                text[span["output_start"] : span["output_end"]]
                == raw[span["raw_start"] : span["raw_end"]]
            )
        cursor = span["output_end"]
    assert cursor == len(text)
    return text, mapping


def boundaries(model, labels, arm="matched400cap2880", variant="raw"):
    results = []
    for bid in BOOKS + ["probe"]:
        text, mapping = verify_map(BASE / "repair" / arm / model / variant / (bid + ".md"))
        for label in [r for r in labels if r["book"] == bid]:
            decision = next(
                d
                for d in mapping["boundaries"]
                if d["left_page"] == label["left_page"] and d["right_page"] == label["right_page"]
            )
            pos = decision["output_offset"]
            left = re.search(r"([^\W\d_]+)$", text[:pos])
            right = re.match(r"([^\W\d_]+)", text[pos:])
            positive = label["expected_action"] == "join_word"
            correct = (
                bool(left and right and norm(left[1] + right[1]) == norm(label["expected_join"]))
                if positive
                else None
            )
            run = BASE / arm / model / bid
            if variant == "format-cleaned":
                run = BASE / "format-cleaned" / arm / model / bid
            a = read_json(run / f"page-{label['left_page']:04d}.json")["markdown"]
            b = read_json(run / f"page-{label['right_page']:04d}.json")["markdown"]
            results.append(
                {
                    "book": bid,
                    "left_page": label["left_page"],
                    "right_page": label["right_page"],
                    "expected_action": label["expected_action"],
                    "expected_join": label["expected_join"],
                    "action": decision["action"],
                    "word_join_correct": correct,
                    "false_word_join": not positive and decision["action"] == "join_word",
                    "action_matches_label": decision["action"] == label["expected_action"],
                    "raw_left_end": a[-200:],
                    "raw_right_start": b[:200],
                    "repaired_context": text[max(0, pos - 100) : pos + 100],
                }
            )
    primary = [r for r in results if r["book"] != "probe"]
    return {
        "model": model,
        "arm": arm,
        "variant": variant,
        "results": results,
        "correct_primary_words": sum(r["word_join_correct"] is True for r in primary),
        "wrong_primary_word_reconstructions": sum(
            r["expected_action"] == "join_word"
            and r["action"] == "join_word"
            and not r["word_join_correct"]
            for r in primary
        ),
        "primary_positive_cases": 4,
        "false_primary_word_joins": sum(r["false_word_join"] for r in primary),
        "primary_negative_cases": 8,
        "primary_action_matches": sum(r["action_matches_label"] for r in primary),
        "probe_correct": next(r["word_join_correct"] for r in results if r["book"] == "probe"),
        "probe_wrong_word_reconstruction": any(
            r["book"] == "probe" and r["action"] == "join_word" and not r["word_join_correct"]
            for r in results
        ),
        "source_maps_verified": 3,
    }


def thumb(path):
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((650, 900))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=80)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=BASE / "report")
    args = parser.parse_args()
    labels = read_json(ROOT / "datasets/expanded/boundaries.json")
    labels.append(
        {
            "book": "probe",
            "left_page": 34,
            "right_page": 35,
            "expected_action": "join_word",
            "expected_join": "Person",
        }
    )
    data = {
        "date": "2026-10-24",
        "reference_status": "Frozen provisional AI-assisted visual references, not independent human gold.",
        "scope": "16 primary pages, 14 CER/WER references, 12 primary boundaries; supplementary Fraktur 34–35 excluded from primary CER.",
        "matched": [
            dict(score_matched(BASE / "matched400cap2880", m), arm="matched400cap2880")
            for m in MODELS
        ]
        + [dict(score_matched(BASE / "budget1120", "gemma4-12b"), arm="budget1120")],
        "legacy": [score_legacy(BASE / "legacy72", "gemma3-12b")],
        "matched_format_cleaned": [
            dict(
                score_matched(BASE / "format-cleaned/matched400cap2880", m), arm="matched400cap2880"
            )
            for m in MODELS
        ]
        + [dict(score_matched(BASE / "format-cleaned/budget1120", "gemma4-12b"), arm="budget1120")],
        "boundary_repair": [boundaries(m, labels) for m in MODELS]
        + [boundaries("gemma4-12b", labels, "budget1120")]
        + [boundaries(m, labels, variant="format-cleaned") for m in MODELS]
        + [boundaries("gemma4-12b", labels, "budget1120", "format-cleaned")],
        "method": {
            "legacy": "Original plural-image prompt, multiple contiguous pages per request, PyMuPDF default 72 DPI, no generation options. Only stream=false and keep_alive=0 added for transport and cleanup. Current pinned models/runtime; not an archived 2025 measurement.",
            "matched": "Same fixed pdfrune 400-DPI source pages, Pillow RGB/LANCZOS cap2880, original prompt, one page/request; temp0 seed0 context16384 output8192, Gemma4 thinking disabled.",
            "batch_scoring": "Whole-excerpt CER/WER against concatenated frozen references. No inferred page segmentation; not identical to summed per-page CER. Only the three fully referenced batches count; symbols remain qualitative.",
            "normalization": "Unchanged content_text: NFC, long s to s, page-number-only furniture and Markdown heading/emphasis removed, line-end hyphens joined, whitespace collapsed; case/spelling/punctuation count. Returned-output scores keep code fences and commentary. Separate format-cleaned scores remove only a single outer fence and leading page-number metadata; body characters stay exact.",
            "boundary": "Unchanged local Qwen3-1.7B classifier and source-preserving rules. No extra visual repair. Raw answers and a separate presentation-only cleanup variant use the same classifier and source guards. Printed page numbers/code fences can prevent joins in the raw arm.",
            "historical": "Original article April6 2025; all new comparisons measured October24 2026, about18.6 months later. No assertion that original Gemma3 tag or defaults are frozen to2025.",
            "budget_control": "Same Gemma4 weights, prompt, cap2880, temperature0, seed0, context16384, output8192 and thinking=false; only the temporary Ollama child uses LLAMA_ARG_IMAGE_MAX_TOKENS=1120. Server log and prompt token counts confirm override. This is an installed-runtime control, not a run on the newest Ollama release.",
        },
    }
    data["model_provenance"] = read_json(BASE / "model-provenance.json")
    data["inputs"] = read_json(BASE / "inputs.json")
    data["budget_evidence"] = read_json(BASE / "budget1120/budget-evidence.json")
    data["temporary_service"] = read_json(BASE / "budget1120/service-process.json")
    data["optional_gemma4_batch_status"] = read_json(
        BASE / "legacy72/gemma4-12b/cancelled-diagnostic.json"
    )
    data["method"]["optional_batch"] = (
        "One optional Gemma4 default-thinking batch excerpt (A9–14) completed; the following unscored A70–71 request was interrupted to prioritize the main tests. Remaining Gemma4 batch requests were not run. This partial branch is displayed as a diagnostic only, without full-sample metrics."
    )
    for row in data["matched"]:
        print("MATCHED", row["model"], row["cer"] * 100, row["wer"] * 100, flush=True)
    for row in data["legacy"]:
        print("LEGACY", row["model"], row["cer"] * 100, row["wer"] * 100, flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    write_json(args.out / "comparison.json", data)
    sections = []
    markdown = [
        "# Gemma: the original workflow and the matched local OCR test",
        "",
        data["scope"],
        "",
        data["reference_status"],
        "",
    ]
    for key, title in [
        ("matched", "Matched 400-DPI per-page OCR (cap2880)"),
        (
            "matched_format_cleaned",
            "Same OCR after presentation-only cleanup (no letter corrections)",
        ),
        ("legacy", "Original-style 72-DPI batch workflow"),
    ]:
        rows = []
        markdown += [
            "## " + title,
            "",
            "| Model | Antiqua CER | Fraktur CER | Combined CER | Combined WER |",
            "|---|---:|---:|---:|---:|",
        ]
        for row in data[key]:
            cells = [
                row["model"] + (" (1120 image tokens)" if row.get("arm") == "budget1120" else ""),
                *(f"{row['books'][b]['cer'] * 100:.2f}%" for b in BOOKS),
                f"{row['cer'] * 100:.2f}%",
                f"{row['wer'] * 100:.2f}%",
            ]
            rows.append("<tr>" + "".join("<td>" + c + "</td>" for c in cells) + "</tr>")
            markdown.append("| " + " | ".join(cells) + " |")
        sections.append(
            f"<h2>{title}</h2><table><tr><th>Model</th><th>Antiqua CER</th><th>Fraktur CER</th><th>Combined CER</th><th>Combined WER</th></tr>{''.join(rows)}</table>"
        )
        markdown.append("")
    sections.append(
        "<h2>Guarded page-break repair</h2><table><tr><th>Model</th><th>Correct split words</th><th>Wrong reconstructions on split cases</th><th>False joins on non-split controls</th><th>Action matches</th><th>Fraktur Person probe</th></tr>"
        + "".join(
            f"<tr><td>{r['model']} ({r['arm']}, {r['variant']})</td><td>{r['correct_primary_words']}/4</td><td>{r['wrong_primary_word_reconstructions']}</td><td>{r['false_primary_word_joins']}/8</td><td>{r['primary_action_matches']}/12</td><td>{r['probe_correct']}; wrong reconstruction: {r['probe_wrong_word_reconstruction']}</td></tr>"
            for r in data["boundary_repair"]
        )
        + "</table>"
    )
    markdown += ["## Guarded page-break repair", ""]
    for row in data["boundary_repair"]:
        markdown += [
            f"- {row['model']} ({row['arm']}, {row['variant']}): {row['correct_primary_words']}/4 correct split words; {row['wrong_primary_word_reconstructions']} wrong primary word reconstructions; {row['false_primary_word_joins']}/8 false joins on non-split controls; {row['primary_action_matches']}/12 action matches; Person probe: {row['probe_correct']}, wrong reconstruction: {row['probe_wrong_word_reconstruction']}."
        ]
    cards = []
    inputs = data["inputs"]["pages"]
    for bid in BOOKS + ["probe"]:
        source_bid = BOOKS[1] if bid == "probe" else bid
        for path in sorted((BASE / "matched400cap2880" / MODELS[0] / bid).glob("page-*.json")):
            n = read_json(path)["pages"][0]
            image = Path(
                next(
                    p["image"]
                    for p in inputs
                    if p["book"] == source_bid and p["page"] == n and p["dpi"] == 400
                )
            )
            cells = [
                f'<article><h3>Scan</h3><img alt="PDF page {n}" src="{thumb(image)}"></article>'
            ]
            for model in MODELS:
                value = read_json(BASE / "matched400cap2880" / model / bid / path.name)
                cells.append(
                    f"<article><h3>{model}</h3><pre>{html.escape(value['markdown'])}</pre></article>"
                )
            ref = REFS / source_bid / path.name.replace(".json", ".txt")
            if ref.exists():
                cells.append(
                    f"<article><h3>Frozen reference</h3><pre>{html.escape(ref.read_text())}</pre></article>"
                )
            cards.append(
                f"<details><summary>{source_bid}: PDF {n}</summary><div class=row>{''.join(cells)}</div></details>"
            )
    batch_cards = []
    for model in MODELS:
        for path in sorted((BASE / "legacy72" / model).rglob("page-*.json")):
            value = read_json(path)
            batch_cards.append(
                f"<details><summary>{model}, {value['book']}, pages {value['pages']}</summary><p>{value['seconds']:.1f}s; done: {html.escape(str(value.get('response', {}).get('done_reason')))}</p><pre>{html.escape(value.get('markdown', value.get('error', '')))}</pre></details>"
            )
    methods = "".join(
        f"<p><strong>{html.escape(k)}:</strong> {html.escape(v)}</p>"
        for k, v in data["method"].items()
    )
    boundary_cards = "".join(
        f"<details><summary>{r['model']}: all boundary evidence</summary><pre>{html.escape(json.dumps(r, ensure_ascii=False, indent=2))}</pre></details>"
        for r in data["boundary_repair"]
    )
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Gemma OCR comparison</title><style>body{{font:16px/1.6 system-ui;margin:28px;background:#f7f9fc;color:#172536}}p{{max-width:1100px}}table{{border-collapse:collapse}}td,th{{border:1px solid #ccd4df;padding:10px;text-align:left}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.5 monospace}}summary{{padding:12px;margin:6px 0;background:#e8eff7;cursor:pointer}}.row{{display:flex;gap:14px;overflow:auto;align-items:start}}article{{flex:0 0 420px;background:white;padding:14px}}img{{width:100%}}</style><h1>Gemma: from the original script to the measured local OCR pipeline</h1><p>{data["scope"]}</p><p>{data["reference_status"]}</p>{"".join(sections)}<h2>Methods and limits</h2>{methods}<h2>Every page: same scan, raw answers, frozen reference</h2>{"".join(cards)}<h2>Original-style batch answers</h2>{"".join(batch_cards)}<h2>Page-break evidence</h2>{boundary_cards}</html>"""
    (args.out / "comparison.html").write_text(document)
    markdown += ["", "## Methods and limits", ""] + [
        f"**{k}:** {v}\n" for k, v in data["method"].items()
    ]
    (args.out / "comparison.md").write_text("\n".join(markdown).rstrip() + "\n")


if __name__ == "__main__":
    main()
