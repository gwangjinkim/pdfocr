"""Matched native 200 versus native 400 Gemma scores, tokens and page-breaks."""

import base64
import html
import io
import json
from pathlib import Path

import build_gemma_report as common
from PIL import Image

from pdfocr.util import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "workspace/gemma200"
CONFIGS = [
    ("Gemma 3 12B", "gemma3-12b", "matched200cap2880", "matched400cap2880"),
    ("Gemma 4 12B, default image budget", "gemma4-12b", "matched200cap2880", "matched400cap2880"),
    ("Gemma 4 12B, 1120 image tokens maximum", "gemma4-12b", "budget1120", "budget1120"),
]


def build_data(base=BASE):
    old = read_json(ROOT / "results/pdfocr-gemma-comparison.json")
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
    previous = common.BASE
    common.BASE = base
    rows = []
    try:
        for name, model, arm, oldarm in CONFIGS:
            raw = common.score_matched(base / arm, model)
            clean = common.score_matched(base / "format-cleaned" / arm, model)
            raw400 = next(r for r in old["matched"] if r["model"] == model and r["arm"] == oldarm)
            clean400 = next(
                r
                for r in old["matched_format_cleaned"]
                if r["model"] == model and r["arm"] == oldarm
            )
            assert [(r["book"], r["page"], r["reference_sha256"]) for r in raw["pages"]] == [
                (r["book"], r["page"], r["reference_sha256"]) for r in raw400["pages"]
            ]
            inputs = []
            for bid in common.BOOKS + ["probe"]:
                for path in sorted((base / arm / model / bid).glob("page-*.json")):
                    value = read_json(path)
                    n = value["pages"][0]
                    oldpath = ROOT / "results/gemma" / oldarm / model / bid / path.name
                    before = read_json(oldpath)
                    request = value["request_without_image_bytes"]
                    earlier = before["request_without_image_bytes"]
                    assert {k: v for k, v in request.items() if k != "messages"} == {
                        k: v for k, v in earlier.items() if k != "messages"
                    }
                    assert request["messages"][0]["content"] == earlier["messages"][0]["content"]
                    inputs.append(
                        {
                            "book": bid,
                            "page": n,
                            "prompt_tokens200": value["response"].get("prompt_eval_count"),
                            "prompt_tokens400": before["response"].get("prompt_eval_count"),
                            "image_sha256_200": request["messages"][0]["images"][0]["sha256"],
                            "image_sha256_400": earlier["messages"][0]["images"][0]["sha256"],
                        }
                    )
            repairs = [
                common.boundaries(model, labels, arm, variant)
                for variant in ["raw", "format-cleaned"]
            ]
            oldrepairs = [
                r for r in old["boundary_repair"] if r["model"] == model and r["arm"] == oldarm
            ]
            rows.append(
                {
                    "name": name,
                    "model": model,
                    "arm200": arm,
                    "arm400": oldarm,
                    "raw200": raw,
                    "clean200": clean,
                    "raw400": raw400,
                    "clean400": clean400,
                    "repairs200": repairs,
                    "repairs400": oldrepairs,
                    "input_token_comparison": inputs,
                }
            )
    finally:
        common.BASE = previous
    inputs = read_json(base / "inputs.json")
    assert len(inputs["400dpi_render_controls"]) == 18
    assert all(p["pixel_identical"] for p in inputs["400dpi_render_controls"])
    service = read_json(base / "budget1120/service-process.json")
    assert service["exited"] and service["loaded_models_after_unload"] == {"models": []}
    return {
        "date": "2026-10-24",
        "rows": rows,
        "inputs": inputs,
        "provenance": read_json(base / "model-provenance.json"),
        "high_budget_provenance": read_json(base / "budget1120/model-provenance.json"),
        "temporary_service": service,
        "budget_evidence": read_json(base / "budget1120/budget-evidence.json"),
        "reference_status": old["reference_status"],
        "method": "Same 18 pages, native repaired pdfrune at 200/400DPI, all 18 current 400-DPI renders match frozen pixels. Same pinned Q4_K_M models, Ollama 0.30.10, prompt, temperature 0 / seed 0 / context 16384 / output 8192, Gemma 4 thinking disabled, RGB/LANCZOS cap 2880 with no upscaling. Only render DPI changes; final image dimensions and visual-token usage can therefore change. Same frozen 14 CER/WER references, normalization and optional presentation-only body-slice cleanup. Same Qwen3 classifier and rules; 12 primary boundaries plus one supplementary Fraktur split. Runtime image budgets are held constant within each configuration.",
        "limits": "Single temperature-zero run per page; no independent human gold or statistical generalization claim. The earlier specialized 200-DPI table used PDFium and is not relabeled as a new native 200 run. Concurrent timings are not a throughput benchmark. 1,120 is a ceiling, not a requirement to upscale small images.",
    }


def pct(value):
    return f"{100 * value:.2f}%"


def main():
    data = build_data()
    out = BASE / "report"
    out.mkdir(exist_ok=True)
    write_json(out / "comparison.json", data)
    md = [
        "# Gemma: matched 200-DPI and 400-DPI comparison",
        "",
        data["reference_status"],
        "",
        data["method"],
        "",
        data["limits"],
        "",
    ]
    sections = []
    for key, title in [
        ("clean", "Presentation-only cleanup; no OCR letters corrected"),
        ("raw", "Returned-output scores, with wrappers retained"),
    ]:
        md += [
            "## " + title,
            "",
            "| Model | Antiqua CER 200→400 | Fraktur CER 200→400 | Combined CER 200→400 | WER 200→400 |",
            "|---|---:|---:|---:|---:|",
        ]
        table = []
        for row in data["rows"]:
            a, b = row[key + "200"], row[key + "400"]
            cells = [
                row["name"],
                *[
                    pct(a["books"][bid]["cer"]) + " → " + pct(b["books"][bid]["cer"])
                    for bid in common.BOOKS
                ],
                pct(a["cer"]) + " → " + pct(b["cer"]),
                pct(a["wer"]) + " → " + pct(b["wer"]),
            ]
            md.append("| " + " | ".join(cells) + " |")
            table.append(
                "<tr>" + "".join("<td>" + html.escape(c) + "</td>" for c in cells) + "</tr>"
            )
            if key == "clean":
                print(
                    row["name"],
                    "200CER",
                    pct(a["cer"]),
                    "A",
                    pct(a["books"][common.BOOKS[0]]["cer"]),
                    "F",
                    pct(a["books"][common.BOOKS[1]]["cer"]),
                    flush=True,
                )
        sections.append(
            f"<h2>{title}</h2><table><tr><th>Model</th><th>Antiqua CER 200→400</th><th>Fraktur CER 200→400</th><th>Combined CER 200→400</th><th>WER 200→400</th></tr>{''.join(table)}</table>"
        )
        md.append("")
    boundary = []
    md += [
        "## Page-break repair after presentation-only cleanup",
        "",
        "| Model | DPI | Correct split words | Wrong reconstructions on primary positives | False joins on 8 negatives | Action matches | Person probe correct | Wrong probe join |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in data["rows"]:
        for dpi in [200, 400]:
            r = next(r for r in row[f"repairs{dpi}"] if r["variant"] == "format-cleaned")
            cells = [
                row["name"],
                str(dpi),
                f"{r['correct_primary_words']}/4",
                str(r["wrong_primary_word_reconstructions"]),
                f"{r['false_primary_word_joins']}/8",
                f"{r['primary_action_matches']}/12",
                str(r["probe_correct"]),
                str(r["probe_wrong_word_reconstruction"]),
            ]
            md.append("| " + " | ".join(cells) + " |")
            boundary.append(
                "<tr>" + "".join("<td>" + html.escape(c) + "</td>" for c in cells) + "</tr>"
            )
    sections.append(
        "<h2>Page-break repair after presentation-only cleanup</h2><table><tr><th>Model</th><th>DPI</th><th>Correct split words</th><th>Wrong primary word reconstructions</th><th>False joins on 8 controls</th><th>Action matches</th><th>Person probe correct</th><th>Wrong probe join</th></tr>"
        + "".join(boundary)
        + "</table>"
    )
    details = []
    for row in data["rows"]:
        details.append(
            "<details><summary>All boundary contexts and image-token counts: "
            + html.escape(row["name"])
            + "</summary><pre>"
            + html.escape(
                json.dumps(
                    {k: row[k] for k in ["repairs200", "repairs400", "input_token_comparison"]},
                    ensure_ascii=False,
                    indent=2,
                )
            )
            + "</pre></details>"
        )
    cards = []
    for p in data["inputs"]["pages"]:
        bid, n = p["book"], p["page"]
        group = "probe" if n in [34, 35] else bid
        source = ROOT / p["image"]
        with Image.open(source) as im:
            im = im.convert("RGB")
            im.thumbnail((580, 900))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=82)
        url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        cells = [f'<article><h3>Native200-DPI scan</h3><img alt="PDF{n}" src="{url}"></article>']
        for row in data["rows"]:
            for dpi in [200, 400]:
                prefix = BASE if dpi == 200 else ROOT / "results/gemma"
                value = read_json(
                    prefix / row[f"arm{dpi}"] / row["model"] / group / f"page-{n:04d}.json"
                )
                cells.append(
                    f"<article><h3>{html.escape(row['name'])}, {dpi}DPI</h3><pre>{html.escape(value['markdown'])}</pre></article>"
                )
        cards.append(
            f"<details><summary>{bid}, PDF{n}</summary><div class=row>{''.join(cells)}</div></details>"
        )
    document = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Gemma200 versus 400DPI</title><style>body{{font:16px/1.6 system-ui;margin:28px;color:#172536;background:#f7f9fc}}table{{border-collapse:collapse}}td,th{{padding:10px;border:1px solid #ccd4df;text-align:left}}p{{max-width:1100px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.5 monospace}}summary{{padding:12px;margin:6px 0;background:#e8eff7;cursor:pointer}}.row{{display:flex;gap:14px;overflow:auto;align-items:start}}article{{flex:0 0 420px;background:white;padding:14px}}img{{width:100%}}</style><h1>Gemma: native 200 versus 400DPI</h1><p>{html.escape(data["reference_status"])}</p><p>{html.escape(data["method"])}</p><p>{html.escape(data["limits"])}</p>{"".join(sections)}<h2>Inspect every page</h2>{"".join(cards)}<h2>Boundary and token evidence</h2>{"".join(details)}</html>"""
    (out / "comparison.html").write_text(document)
    (out / "comparison.md").write_text("\n".join(md).rstrip() + "\n")


if __name__ == "__main__":
    main()
