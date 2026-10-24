"""Score explicit Gemma3 tiling, compare frozen baselines, and export evidence."""

import argparse
import base64
import html
import io
import json
import shutil
from collections import Counter
from pathlib import Path

import build_gemma_report as common
from PIL import Image, ImageDraw
from verify_gemma_results import verify_map

from pdfocr.book_compare import content_text, rates
from pdfocr.gemma_format import unwrap_presentation
from pdfocr.gemma_tiles import TILE_PROMPT, band_boxes
from pdfocr.util import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "workspace/gemma3-tiles"
MODEL = "gemma3-12b"
NAME = "pdfocr-gemma3-tiling-comparison"


def build_data(base=BASE):
    previous = read_json(ROOT / "results/pdfocr-gemma-200dpi-comparison.json")
    provenance = read_json(base / "model-provenance.json")
    baseline = read_json(ROOT / "results/gemma/model-provenance.json")
    assert provenance["ollama"] == baseline["ollama"]
    assert (
        provenance["models"]["gemma3:12b"]["tag"]["digest"]
        == baseline["models"]["gemma3:12b"]["tag"]["digest"]
    )
    labels = read_json(ROOT / "datasets/expanded/boundaries.json") + [
        {
            "book": "probe",
            "left_page": 34,
            "right_page": 35,
            "expected_action": "join_word",
            "expected_join": "Person",
        }
    ]
    rows = []
    original_base, original_map = common.BASE, common.verify_map
    try:
        common.verify_map = verify_map
        for dpi in [200, 400]:
            experiment = base / f"dpi{dpi}"
            common.BASE = experiment
            inputs = read_json(experiment / "inputs.json")
            assert inputs["complete"] and len(inputs["pages"]) == 18
            raw = common.score_matched(experiment / "tiles4", MODEL)
            clean = common.score_matched(experiment / "format-cleaned/tiles4", MODEL)
            controls = []
            quality = []
            for p in inputs["pages"]:
                group = "probe" if p["page"] in [34, 35] else p["book"]
                path = experiment / "tiles4" / MODEL / group / f"page-{p['page']:04d}.json"
                value = read_json(path)
                paragraphs = [" ".join(x.split()) for x in value["markdown"].split("\n\n")]
                repeated = [
                    {"occurrences": count, "characters": len(text), "sample": text[:140]}
                    for text, count in Counter(paragraphs).items()
                    if len(text) >= 120 and count > 1
                ]
                if repeated or value["response"].get("eval_count", 0) >= 8192:
                    quality.append(
                        {
                            "book": p["book"],
                            "page": p["page"],
                            "exact_repeated_long_paragraphs": repeated,
                            "generation_tokens": value["response"].get("eval_count"),
                            "done_reason": value["response"].get("done_reason"),
                            "output_ceiling_reached": value["response"].get("eval_count", 0)
                            >= 8192,
                        }
                    )
                request = value["request_without_image_bytes"]
                assert request["model"] == "gemma3:12b" and request["keep_alive"] == 0
                assert request["stream"] is False
                assert request["options"] == {
                    "temperature": 0,
                    "seed": 0,
                    "num_ctx": 16384,
                    "num_predict": 8192,
                }
                assert request["messages"][0]["content"] == TILE_PROMPT
                views = p["tiling"]["views"]
                frozen = next(
                    x
                    for x in previous["rows"][0]["input_token_comparison"]
                    if x["book"] == group and x["page"] == p["page"]
                )
                assert views[0]["sha256"] == frozen[f"image_sha256_{dpi}"]
                assert p["capped_overview_sha256"] == views[0]["sha256"]
                assert len(views) == 5 and p["prompt_eval_count"] >= 1280
                assert [x["sha256"] for x in views] == [
                    x["sha256"] for x in request["messages"][0]["images"]
                ]
                width, height = p["tiling"]["parent_size"]
                assert [x["box"] for x in views[1:]] == [list(b) for b in band_boxes(width, height)]
                assert all(x["exact_source_crop"] for x in views[1:])
                normal = read_json(experiment / "format-cleaned/tiles4" / MODEL / group / path.name)
                assert normal["markdown"] == unwrap_presentation(value["markdown"])["markdown"]
                evidence = p["tiling"].get("same_prompt_overview_control")
                if evidence:
                    control = read_json(experiment / "overview-control" / MODEL / group / path.name)
                    assert (
                        control["request_without_image_bytes"]["messages"][0]["content"]
                        == TILE_PROMPT
                    )
                    delta = (
                        value["response"]["prompt_eval_count"]
                        - control["response"]["prompt_eval_count"]
                    )
                    assert delta >= 1024 and delta == evidence["extra_prompt_tokens"]
                    ref = (
                        ROOT
                        / "datasets/expanded/references"
                        / p["book"]
                        / f"page-{p['page']:04d}.txt"
                    )
                    truth = content_text(ref.read_text())
                    controls.append(
                        {
                            "book": p["book"],
                            "page": p["page"],
                            "overview": rates(
                                truth,
                                content_text(unwrap_presentation(control["markdown"])["markdown"]),
                            ),
                            "tiles": rates(truth, content_text(normal["markdown"])),
                            "overview_prompt_tokens": control["response"]["prompt_eval_count"],
                            "tiled_prompt_tokens": value["response"]["prompt_eval_count"],
                            "extra_prompt_tokens": delta,
                        }
                    )
            assert len(controls) == 2
            rows.append(
                {
                    "dpi": dpi,
                    "raw": raw,
                    "clean": clean,
                    "inputs": inputs,
                    "baseline": previous["rows"][0][f"clean{dpi}"],
                    "gemma4_high": previous["rows"][2][f"clean{dpi}"],
                    "repairs": [
                        common.boundaries(MODEL, labels, "tiles4", v)
                        for v in ["raw", "format-cleaned"]
                    ],
                    "baseline_repairs": previous["rows"][0][f"repairs{dpi}"],
                    "same_prompt_controls": controls,
                    "quality_flags": quality,
                }
            )
    finally:
        common.BASE, common.verify_map = original_base, original_map
    processes = [read_json(p) for p in base.glob("process-*.json")]
    assert processes and all(x["exited"] for x in processes)
    return {
        "date": "2026-10-24",
        "model_provenance": provenance,
        "processes": processes,
        "rows": rows,
        "reference_status": previous["reference_status"],
        "method": "Explicit overview plus four overlapping full-width horizontal bands from the same frozen RGB/LANCZOS cap2880 inputs; native pdfrune at both DPIs. Complete pixel coverage, exact crop hashes and five submitted image hashes verified. >=1280 total prompt tokens on all pages; two same-prompt overview controls per DPI confirm >=1024 extra tokens. Not a native pan-and-scan implementation. Original prompt replaced by an explicit one-page/multiple-view instruction; this is a stack comparison, not a crop-only ablation across all pages. Same frozen model digest, Ollama0.30.10, temp0/seed0/context16384/output8192. 16 primary pages plus two supplementary Fraktur probe pages per DPI; 14 provisional full-page references; unchanged cleanup/scorer/Qwen3 repair/guards.",
        "limits": "Single deterministic run; provisional AI-assisted references, not independent human gold. Four split-word primary positives are Antiqua; Fraktur has one separate positive. No throughput ranking; extra views add compute. Same-prompt overview controls cover only two pages per DPI, not a full-sample prompt ablation.",
        "loaded_models_at_end": read_json(base / "loaded-models-at-end.json"),
    }


def portable(value):
    if isinstance(value, dict):
        return {
            k: v if k in {"markdown", "content", "thinking"} else portable(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [portable(v) for v in value]
    if isinstance(value, str):
        for old, new in [
            (str(ROOT) + "/", ""),
            (str(Path.home() / ".cache/huggingface/hub") + "/", "model-cache/"),
            (str(ROOT.parent / "pdfocr") + "/", "source-lab/"),
            (str(Path.home()) + "/", "user-home/"),
        ]:
            value = value.replace(old, new)
    return value


def export(data, outputs):
    dest = ROOT / "results/gemma3-tiles"
    for source in BASE.rglob("*"):
        if (
            not source.is_file()
            or source.suffix not in {".json", ".jsonl", ".md"}
            or "report" in source.relative_to(BASE).parts
        ):
            continue
        target = dest / source.relative_to(BASE)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".json":
            write_json(target, portable(read_json(source)))
        elif source.suffix == ".jsonl":
            target.write_text(
                "\n".join(
                    json.dumps(portable(json.loads(s)), ensure_ascii=False)
                    for s in source.read_text().splitlines()
                    if s.strip()
                )
                + "\n"
            )
        elif source.name.endswith(".boundaries.md"):
            target.write_text(portable(source.read_text()))
        else:
            shutil.copyfile(source, target)
    write_json(ROOT / "results" / (NAME + ".json"), portable(data))
    shutil.copyfile(ROOT / "results" / (NAME + ".json"), outputs / (NAME + ".json"))


def html_report(data, markdown):
    # This report emits escaped text and tables, without client scripts or a server.
    parts = []
    in_table = False
    for line in markdown.splitlines() + [""]:
        if line.startswith("|"):
            cells = [x.strip() for x in line.strip("|").split("|")]
            if all(set(x) <= {"-", ":"} for x in cells):
                continue
            tag = "td" if in_table else "th"
            if not in_table:
                parts.append("<table>")
            in_table = True
            parts.append(
                "<tr>" + "".join(f"<{tag}>{html.escape(x)}</{tag}>" for x in cells) + "</tr>"
            )
            continue
        if in_table:
            parts.append("</table>")
            in_table = False
        if line.startswith("# "):
            parts.append("<h1>" + html.escape(line[2:]) + "</h1>")
        elif line.startswith("## "):
            parts.append("<h2>" + html.escape(line[3:]) + "</h2>")
        elif line:
            parts.append("<p>" + html.escape(line) + "</p>")
    parts.append("<h2>Inspect all 36 tiled page transcriptions</h2>")
    for row in data["rows"]:
        dpi = row["dpi"]
        for p in row["inputs"]["pages"]:
            bid, number = p["book"], p["page"]
            group = "probe" if number in [34, 35] else bid
            filename = f"page-{number:04d}.json"
            current = read_json(BASE / f"dpi{dpi}/tiles4" / MODEL / group / filename)
            prefix = "gemma200/matched200cap2880" if dpi == 200 else "gemma/matched400cap2880"
            earlier = read_json(ROOT / "results" / prefix / MODEL / group / filename)
            sheet = Image.new("RGB", (1100, 390), "#eef2f6")
            draw = ImageDraw.Draw(sheet)
            for i, view in enumerate(p["tiling"]["views"]):
                with Image.open(view["path"]) as im:
                    im = im.convert("RGB")
                    im.thumbnail((210, 350))
                    sheet.paste(im, (i * 220 + 5, 30))
                draw.text((i * 220 + 5, 5), view["role"], fill="black")
            buffer = io.BytesIO()
            sheet.save(buffer, format="JPEG", quality=85)
            url = "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode()
            details = {
                "input": portable(p),
                "response_tokens": current["response"]["prompt_eval_count"],
                "possibly_truncated": current["possibly_truncated"],
            }
            parts.append(
                f"<details><summary>{html.escape(bid)} PDF{number}, {dpi} DPI</summary>"
                f'<img alt="Overview and four submitted bands" src="{url}">'
                '<div class="columns"><article><h3>Frozen single-image baseline</h3><pre>'
                + html.escape(earlier["markdown"])
                + "</pre></article><article><h3>New five-view transcription</h3><pre>"
                + html.escape(current["markdown"])
                + "</pre></article></div><details><summary>Crop and token evidence</summary><pre>"
                + html.escape(json.dumps(details, ensure_ascii=False, indent=2))
                + "</pre></details></details>"
            )
    for row in data["rows"]:
        parts.append(
            f"<details><summary>All {row['dpi']}-DPI boundary decisions</summary><pre>"
            + html.escape(json.dumps(row["repairs"], ensure_ascii=False, indent=2))
            + "</pre></details>"
        )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        "<title>Gemma 3 verified tiling comparison</title><style>"
        "body{font:16px/1.6 system-ui;margin:24px;color:#172536;background:#f7f9fc}"
        "p{max-width:1050px}table{display:block;overflow:auto;border-collapse:collapse;margin:20px 0}"
        "td,th{padding:10px;border:1px solid #ccd4df;text-align:left}th{background:#e8eff7}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.5 monospace}"
        "summary{padding:12px;margin:6px 0;background:#e8eff7;cursor:pointer}"
        ".columns{display:flex;gap:18px;overflow:auto}article{flex:1;min-width:360px;background:white;padding:14px}"
        "img{max-width:100%;height:auto}</style>" + "".join(parts) + "</html>"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outputs", type=Path, required=True)
    parser.add_argument("--verify-published", action="store_true")
    args = parser.parse_args()
    if args.verify_published:
        data = build_data(ROOT / "results/gemma3-tiles")
        assert data == read_json(ROOT / "results" / (NAME + ".json"))
        print("Verified all published tiling metrics, crops, prompt tokens and source maps")
        return
    data = build_data()
    args.outputs.mkdir(parents=True, exist_ok=True)

    def pct(x):
        return f"{x * 100:.2f}%"

    md = [
        "# Gemma 3 12B with verified explicit tiling",
        "",
        data["reference_status"],
        "",
        data["method"],
        "",
        data["limits"],
        "",
    ]
    for variant in ["clean", "raw"]:
        md += [
            "## " + ("Presentation-only cleanup" if variant == "clean" else "Returned output"),
            "",
            "| DPI | Antiqua CER | Fraktur CER | Combined CER | WER | Output-limit pages |",
            "|---|---:|---:|---:|---:|---|",
        ]
        for row in data["rows"]:
            r = row[variant]
            md.append(
                "| "
                + " | ".join(
                    [
                        str(row["dpi"]),
                        *[pct(r["books"][b]["cer"]) for b in common.BOOKS],
                        pct(r["cer"]),
                        pct(r["wer"]),
                        str(r["truncated_pages"]),
                    ]
                )
                + " |"
            )
        md += [""]
    md += [
        "## Cleaned Gemma 3 baseline versus tiling",
        "",
        "| DPI | Antiqua baseline → tiled | Fraktur baseline → tiled | Combined baseline → tiled |",
        "|---|---:|---:|---:|",
    ]
    for row in data["rows"]:
        a, b = row["baseline"], row["clean"]
        md.append(
            "| "
            + " | ".join(
                [
                    str(row["dpi"]),
                    *[
                        pct(a["books"][k]["cer"]) + " → " + pct(b["books"][k]["cer"])
                        for k in common.BOOKS
                    ],
                    pct(a["cer"]) + " → " + pct(b["cer"]),
                ]
            )
            + " |"
        )
    md += [
        "",
        "## Boundary repair",
        "",
        "| DPI | Variant | Correct primary words | Wrong primary reconstructions | False joins on 8 controls | Action matches | Person correct | Wrong probe join |",
        "|---|---|---:|---:|---:|---:|---|---|",
    ]
    for row in data["rows"]:
        for r in row["repairs"]:
            md.append(
                "| "
                + " | ".join(
                    [
                        str(row["dpi"]),
                        r["variant"],
                        f"{r['correct_primary_words']}/4",
                        str(r["wrong_primary_word_reconstructions"]),
                        f"{r['false_primary_word_joins']}/8",
                        f"{r['primary_action_matches']}/12",
                        str(r["probe_correct"]),
                        str(r["probe_wrong_word_reconstruction"]),
                    ]
                )
                + " |"
            )
    md += [
        "",
        "## Same-prompt overview controls",
        "",
        "| DPI | Book and page | Overview CER | Tiled CER | Overview tokens | Tiled tokens |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in data["rows"]:
        for c in row["same_prompt_controls"]:
            md.append(
                f"| {row['dpi']} | {c['book']} PDF{c['page']} | {pct(c['overview']['cer'])} | {pct(c['tiles']['cer'])} | {c['overview_prompt_tokens']} | {c['tiled_prompt_tokens']} |"
            )
    md += [
        "",
        "## Output quality flags",
        "",
        "Exact repeated paragraphs of at least 120 characters are flagged without rewriting the output. A normal stop does not prove a single complete transcription.",
        "",
    ]
    for row in data["rows"]:
        for flag in row["quality_flags"]:
            md.append(
                f"- {row['dpi']}DPI, {flag['book']} PDF{flag['page']}: "
                f"{len(flag['exact_repeated_long_paragraphs'])} repeated long paragraph patterns; "
                f"{flag['generation_tokens']} generated tokens; stop reason {flag['done_reason']}; "
                f"output ceiling reached: {flag['output_ceiling_reached']}."
            )
    text = "\n".join(md) + "\n"
    (ROOT / "results" / (NAME + ".md")).write_text(text)
    (args.outputs / (NAME + ".md")).write_text(text)
    (args.outputs / (NAME + ".html")).write_text(html_report(data, text))
    export(data, args.outputs)
    print(text)


if __name__ == "__main__":
    main()
