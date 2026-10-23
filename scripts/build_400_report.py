"""Paired report: frozen PDFium 200 DPI versus fixed native pdfrune 400 DPI."""

import difflib
import html
import json
from pathlib import Path

from build_expanded_report import boundary_result, image_url

from pdfocr.book_compare import content_text, rates
from pdfocr.util import file_hash, read_json, write_json

ROOT = Path.cwd()
BASE = ROOT / "workspace/expanded400"
OLD = ROOT / "workspace/expanded"
MODELS = ["glm-ocr", "ovisocr3", "paddle-vl", "teleocr"]
LABELS = read_json(ROOT / "datasets/expanded/boundaries.json")


def verified_flow(path):
    mapping = read_json(path.with_suffix(".pages.json"))
    raw = Path(mapping["raw_file"]).read_text()
    text = path.read_text()
    assert file_hash(Path(mapping["raw_file"])) == mapping["raw_sha256"]
    if "output_sha256" in mapping:
        assert file_hash(path) == mapping["output_sha256"]
    offset = 0
    for span in mapping["spans"]:
        assert span["output_start"] == offset
        if span["kind"] == "source":
            assert (
                text[span["output_start"] : span["output_end"]]
                == raw[span["raw_start"] : span["raw_end"]]
            )
        offset = span["output_end"]
    assert offset == len(text)
    return text, mapping


def boundaries(path, book):
    text, mapping = verified_flow(path)
    results = []
    for label in (x for x in LABELS if x["book"] == book):
        decision = next(
            d
            for d in mapping["boundaries"]
            if (d["left_page"], d["right_page"]) == (label["left_page"], label["right_page"])
        )
        results.append(
            {
                "book": book,
                "left_page": label["left_page"],
                "right_page": label["right_page"],
                **boundary_result(label, decision, text, mapping),
            }
        )
    return results


def summarize(pages):
    return {
        "cer": sum(p["character_edits"] for p in pages)
        / sum(p["reference_characters"] for p in pages),
        "wer": sum(p["word_edits"] for p in pages) / sum(p["reference_words"] for p in pages),
    }


def probe_results():
    label = read_json(ROOT / "datasets/expanded400/probe-boundary.json")
    rows = []
    for dpi in [200, 400]:
        base = ROOT / f"workspace/expanded400-probe-{dpi}"
        index = read_json(base / "index.json")["books"][label["book"]]
        visual = read_json(base / "visual/results.json")
        for model in MODELS:
            run = Path(index[model])
            manifest = read_json(run / "manifest.json")
            assert manifest["status"] == "complete"
            flow = run.parents[1] / f"flow-{run.name}.proposed.md"
            text, mapping = verified_flow(flow)
            decision = next(
                d for d in mapping["boundaries"] if d["left_page"] == 34 and d["right_page"] == 35
            )
            row = {
                "dpi": dpi,
                "model": model,
                "run": str(run),
                "baseline": boundary_result(label, decision, text, mapping),
                "raw_left_end": read_json(run / "page-0034.json")["markdown"][-160:],
                "raw_right_start": read_json(run / "page-0035.json")["markdown"][:160],
                "visual": None,
            }
            if model in {"ovisocr3", "paddle-vl"}:
                text, mapping = verified_flow(
                    base / "visual" / label["book"] / f"{model}-visual.proposed.md"
                )
                decision = next(
                    d
                    for d in mapping["boundaries"]
                    if d["left_page"] == 34 and d["right_page"] == 35
                )
                evidence = next(d for d in visual["decisions"] if d["model"] == model)
                row["visual"] = {
                    **boundary_result(label, decision, text, mapping),
                    "evidence": evidence,
                }
            rows.append(row)
    for model in MODELS:
        a, b = [r for r in rows if r["model"] == model]
        x, y = [read_json(Path(r["run"]) / "manifest.json")["config"] for r in [a, b]]
        for field in [
            "model",
            "backend",
            "model_pin",
            "prompt",
            "layout_pin",
            "teleocr_binary_sha256",
        ]:
            assert x.get(field) == y.get(field), (model, field)
    return rows


def glm_diagnostics(new):
    bid = "makrobiotikoderd00hufeuoft"
    primary = next(m for m in new["models"] if m["name"] == "glm-ocr")
    cases = {
        "native-400-default": primary["runs"][bid]["path"],
        **read_json(BASE / "glm-page29-diagnostic/index.json"),
    }
    rows = []
    ref = ROOT / f"datasets/expanded/references/{bid}/page-0029.txt"
    for name, folder in cases.items():
        folder = Path(folder)
        manifest = read_json(folder / "manifest.json")
        value = read_json(folder / "page-0029.json")
        inp = next(p for p in manifest["inputs"] if p["page"] == 29)
        doc = read_json(Path(manifest["document"]) / "document.json")
        source = next(p for p in doc["pages"] if p["page"] == 29)
        rows.append(
            {
                "name": name,
                "run": str(folder),
                "dpi": source["dpi"],
                "renderer": source["renderer"],
                "render_sha256": source["image_sha256"],
                "input_size": inp["input_size"],
                "generation_tokens": value.get("generation_tokens"),
                "possibly_truncated": value.get("possibly_truncated", False),
                "characters": len(value["markdown"]),
                "markdown": value["markdown"],
                **rates(content_text(ref.read_text()), content_text(value["markdown"])),
            }
        )
    original = next(r for r in rows if r["name"] == "native-400-default")
    retry = next(r for r in rows if r["name"] == "native-400-cap1157")
    assert original["render_sha256"] == retry["render_sha256"]
    guarded = None
    flags = [(p["book"], p["page"]) for p in primary["inputs"] if p["possibly_truncated"]]
    if flags == [(bid, 29)] and not retry["possibly_truncated"]:
        scores = [retry if (p["book"], p["page"]) == (bid, 29) else p for p in primary["pages"]]
        guarded = {
            **summarize(scores),
            "note": "Single observed token-limit failure retried from the identical 400-DPI raster at cap1157. Primary score unchanged. No word replacement or new reference tuning; this is a diagnostic fallback, not independently validated production performance.",
        }
    return {"cases": rows, "single_case_retry_aggregate": guarded}


def measure(base, selection):
    index = read_json(base / "index.json")
    variants = read_json(base / "paddle-book-index.json")
    data = {
        "models": [],
        "documents": selection["books"],
        "visual": read_json(base / "visual/results.json"),
    }
    for name in [*MODELS, "paddle-book"]:
        row = {
            "name": name,
            "pages": [],
            "books": {},
            "boundaries": [],
            "visual_boundaries": [],
            "inputs": [],
            "inference_seconds": 0,
            "runs": {},
        }
        for book in selection["books"]:
            bid = book["id"]
            folder = Path(book["document"])
            doc = read_json(folder / "document.json")
            run = Path(variants[bid] if name == "paddle-book" else index["books"][bid][name])
            manifest = read_json(run / "manifest.json")
            assert (
                manifest["status"] == "complete"
                and manifest["source_sha256"] == doc["source_sha256"]
            )
            assert [p["page"] for p in manifest["pages"]] == doc["selected_pages"]
            row["runs"][bid] = {"path": str(run), "config": manifest["config"]}
            for page in manifest["pages"]:
                n = page["page"]
                value = read_json(run / page["result"])
                assert value["status"] == "ok"
                row["inference_seconds"] += value["seconds"]
                ref = ROOT / f"datasets/expanded/references/{bid}/page-{n:04d}.txt"
                inp = next(p for p in manifest["inputs"] if p["page"] == n)
                source = next(p for p in doc["pages"] if p["page"] == n)
                assert file_hash(Path(inp["image_path"])) == inp["image_sha256"]
                row["inputs"].append(
                    {
                        "book": bid,
                        "page": n,
                        "render_size": [source["width"], source["height"]],
                        "harness_input_size": inp["input_size"],
                        "input_sha256": inp["image_sha256"],
                        "possibly_truncated": value.get("possibly_truncated", False),
                    }
                )
                if ref.exists():
                    score = {
                        "book": bid,
                        "page": n,
                        **rates(content_text(ref.read_text()), content_text(value["markdown"])),
                    }
                    row["pages"].append(score)
            row["books"][bid] = summarize([p for p in row["pages"] if p["book"] == bid])
            if name != "paddle-book":
                row["boundaries"].extend(boundaries(folder / f"flow-{run.name}.proposed.md", bid))
                if name in {"ovisocr3", "paddle-vl"}:
                    visual_results = boundaries(
                        base / "visual" / bid / f"{name}-visual.proposed.md", bid
                    )
                    for result in visual_results:
                        evidence = next(
                            d
                            for d in data["visual"]["decisions"]
                            if d["book"] == bid
                            and d["model"] == name
                            and d["left_page"] == result["left_page"]
                        )
                        result["visual_applied"] = evidence["applied"]
                        result["false_added_visual_join"] = (
                            evidence["applied"] and result["expected_action"] != "join_word"
                        )
                        if evidence["applied"]:
                            result["action"] = "visual_join_word"
                            result["action_matches_label"] = (
                                result["expected_action"] == "join_word"
                            )
                            result["false_word_join"] = result["expected_action"] != "join_word"
                    row["visual_boundaries"].extend(visual_results)
        row.update(summarize(row["pages"]))
        row["correct_split_words"] = sum(b["word_join_correct"] is True for b in row["boundaries"])
        row["false_word_joins"] = sum(b["false_word_join"] for b in row["boundaries"])
        row["boundary_actions_matching"] = sum(b["action_matches_label"] for b in row["boundaries"])
        row["deferred_boundaries"] = sum(b["action"] == "uncertain" for b in row["boundaries"])
        row["visual_correct_split_words"] = sum(
            b["word_join_correct"] is True for b in row["visual_boundaries"]
        )
        data["models"].append(row)
    return data


def main():
    selection = read_json(ROOT / "datasets/expanded400/selection.json")
    prior_selection = read_json(ROOT / "datasets/expanded/selection.json")
    refs = read_json(ROOT / "datasets/expanded/reference-hashes.json")
    assert refs == selection["experiment"]["reference_hashes"]
    for path, digest in refs.items():
        assert file_hash(ROOT / "datasets/expanded" / path) == digest
    old, new = measure(OLD, prior_selection), measure(BASE, selection)
    for a, b in zip(old["models"], new["models"], strict=True):
        for bid in a["runs"]:
            x, y = a["runs"][bid]["config"], b["runs"][bid]["config"]
            for field in [
                "model",
                "backend",
                "model_pin",
                "prompt",
                "layout_pin",
                "teleocr_binary_sha256",
            ]:
                assert x.get(field) == y.get(field), (a["name"], bid, field)
        b["cer_change_percentage_points"] = 100 * (b["cer"] - a["cer"])
    new["visual_worker_seconds"] = read_json(BASE / "visual/process.json")["seconds"]
    old["visual_worker_seconds"] = read_json(OLD / "visual/process.json")["seconds"]
    probes = probe_results()
    diagnostics = glm_diagnostics(new)
    quality_flags = [
        {"model": m["name"], **p}
        for m in new["models"]
        if m["name"] in MODELS
        for p in m["inputs"]
        if p["possibly_truncated"]
    ]
    data = {
        "experiment": selection["experiment"],
        "reference_status": "Same 14 frozen provisional assistant visual transcriptions; not independent human gold. Prescription pages 70–71 remain qualitative.",
        "old": old,
        "new": new,
        "fraktur_dpi_probe": probes,
        "glm_repetition_diagnostics": diagnostics,
        "quality_flags": quality_flags,
    }
    out = BASE / "report"
    out.mkdir(exist_ok=True)
    write_json(out / "comparison.json", data)
    summary, book_rows, page_rows, flow_rows, visual_rows, dimensions, cards = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )
    markdown = [
        "# Native pdfrune 400-DPI rerun",
        "",
        data["reference_status"],
        "",
        "All four local models rerun on the same 16 pages: 64 fresh page outputs and 12 adjacent boundaries. Fixed pdfrune is strict, without fallback. Both DPI and renderer change versus the prior PDFium run, so this measures the combined change. Model weights, prompts, resize caps and scoring are unchanged.",
        "",
        "| Pipeline | 200-DPI CER | 400-DPI CER | Change, pp | 200-DPI WER | 400-DPI WER |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for a, b in zip(old["models"], new["models"], strict=True):
        name = b["name"]
        summary.append(
            f"<tr><td>{name}</td><td>{100 * a['cer']:.2f}%</td><td>{100 * b['cer']:.2f}%</td><td>{b['cer_change_percentage_points']:+.2f}</td><td>{100 * a['wer']:.2f}%</td><td>{100 * b['wer']:.2f}%</td></tr>"
        )
        markdown.append(
            f"| {name} | {100 * a['cer']:.2f}% | {100 * b['cer']:.2f}% | {b['cer_change_percentage_points']:+.2f} | {100 * a['wer']:.2f}% | {100 * b['wer']:.2f}% |"
        )
        for bid in a["books"]:
            x, y = a["books"][bid], b["books"][bid]
            book_rows.append(
                f"<tr><td>{bid}</td><td>{name}</td><td>{100 * x['cer']:.2f}%</td><td>{100 * y['cer']:.2f}%</td><td>{100 * (y['cer'] - x['cer']):+.2f}</td></tr>"
            )
        for x, y in zip(a["pages"], b["pages"], strict=True):
            assert (x["book"], x["page"]) == (y["book"], y["page"])
            page_rows.append(
                f"<tr><td>{y['book']}</td><td>{y['page']}</td><td>{name}</td><td>{100 * x['cer']:.2f}%</td><td>{100 * y['cer']:.2f}%</td><td>{100 * (y['cer'] - x['cer']):+.2f}</td></tr>"
            )
        if name != "paddle-book":
            flow_rows.append(
                f"<tr><td>{name}</td><td>{a['correct_split_words']}/4</td><td>{b['correct_split_words']}/4</td><td>{a['boundary_actions_matching']}/12</td><td>{b['boundary_actions_matching']}/12</td><td>{a['false_word_joins']}/8</td><td>{b['false_word_joins']}/8</td></tr>"
            )
        if name in {"ovisocr3", "paddle-vl"}:
            applied = [d for d in new["visual"]["decisions"] if d["model"] == name and d["applied"]]
            wrong = sum(d["false_added_visual_join"] for d in b["visual_boundaries"])
            visual_rows.append(
                f"<tr><td>{name}</td><td>{a['visual_correct_split_words']}/4</td><td>{b['visual_correct_split_words']}/4</td><td>{len(applied)}</td><td>{wrong}/8</td></tr>"
            )
        if name in MODELS:
            for bid in a["books"]:
                x = next(i for i in a["inputs"] if i["book"] == bid)
                y = next(i for i in b["inputs"] if i["book"] == bid)
                dimensions.append(
                    f"<tr><td>{bid}</td><td>{name}</td><td>{x['harness_input_size']}</td><td>{y['harness_input_size']}</td><td>{y['render_size']}</td></tr>"
                )
    for book in selection["books"]:
        bid = book["id"]
        doc = read_json(Path(book["document"]) / "document.json")
        for page in doc["pages"]:
            n = page["page"]
            columns = [
                f'<article><h3>Native 400-DPI scan</h3><img loading="lazy" src="{image_url(Path(book["document"]) / page["image"], (1200, 2200))}"></article>'
            ]
            for a, b in zip(old["models"], new["models"], strict=True):
                name = b["name"]
                x = read_json(Path(a["runs"][bid]["path"]) / f"page-{n:04d}.json")["markdown"]
                y = read_json(Path(b["runs"][bid]["path"]) / f"page-{n:04d}.json")["markdown"]
                diff = "\n".join(
                    difflib.unified_diff(
                        x.split(),
                        y.split(),
                        fromfile="200-DPI words",
                        tofile="400-DPI words",
                        lineterm="",
                    )
                )
                columns.append(
                    f"<article><h3>{name}</h3><details><summary>200-DPI output</summary><pre>{html.escape(x)}</pre></details><h4>400-DPI output</h4><pre>{html.escape(y)}</pre><details><summary>Word changes</summary><pre>{html.escape(diff)}</pre></details></article>"
                )
            ref = ROOT / f"datasets/expanded/references/{bid}/page-{n:04d}.txt"
            if ref.exists():
                columns.append(
                    f"<article><h3>Unchanged provisional reference</h3><pre>{html.escape(ref.read_text())}</pre></article>"
                )
            cards.append(
                f'<details class="page"><summary>{bid} — PDF {n}</summary><div class="row">'
                + "".join(columns)
                + "</div></details>"
            )
    boundary_cards = []
    for a, b in zip(old["models"], new["models"], strict=True):
        for x, y in zip(a["boundaries"], b["boundaries"], strict=True):
            boundary_cards.append(
                f"<tr><td>{b['name']}</td><td>{y['book']} {y['left_page']}→{y['right_page']}</td><td>{y['expected_action']}</td><td>{x['action']}: {x['word_join_correct']}</td><td>{y['action']}: {y['word_join_correct']}</td><td><pre>{html.escape(x['context'])}</pre></td><td><pre>{html.escape(y['context'])}</pre></td></tr>"
            )
    evidence = []
    for d in new["visual"]["decisions"]:
        if d["applied"] or d["book"] == "10289757bsb":
            crop_cards = "".join(
                f'<article><h4>{side} edge</h4><img loading="lazy" src="{image_url(d[side + "_edge"]["crop"], (1800, 650))}"><pre>{html.escape(d[side + "_edge"]["text"])}</pre></article>'
                for side in ["left", "right"]
                if d[side + "_edge"]
            )
            evidence.append(
                f'<details><summary>{d["model"]}: {d["book"]} {d["left_page"]}→{d["right_page"]}, {"APPLIED" if d["applied"] else "DEFERRED"}</summary><p>{html.escape(d["gate"]["reason"])}</p><div class="row">{crop_cards}</div></details>'
            )
    probe_rows = []
    probe_evidence = []
    for name in MODELS:
        a, b = [p for p in probes if p["model"] == name]

        def v(r):
            return str(r["visual"]["word_join_correct"]) if r["visual"] else "not tested"

        probe_rows.append(
            f"<tr><td>{name}</td><td>{a['baseline']['word_join_correct']}</td><td>{b['baseline']['word_join_correct']}</td><td>{v(a)}</td><td>{v(b)}</td></tr>"
        )
    for p in probes:
        crop_cards = ""
        if p["visual"]:
            e = p["visual"]["evidence"]
            crop_cards = "".join(
                f'<article><h4>{side} crop</h4><img loading="lazy" src="{image_url(e[side + "_edge"]["crop"], (1800, 650))}"><pre>{html.escape(e[side + "_edge"]["text"])}</pre></article>'
                for side in ["left", "right"]
                if e[side + "_edge"]
            )
        probe_evidence.append(
            f'<details><summary>{p["model"]}, {p["dpi"]} DPI, Fraktur 34→35</summary><p>Raw page edges</p><pre>{html.escape(p["raw_left_end"])}\n|||\n{html.escape(p["raw_right_start"])}</pre><p>Baseline: {html.escape(p["baseline"]["context"])}</p><div class="row">{crop_cards}</div></details>'
        )
    probe_section = (
        "<h2>Matched Fraktur hyphen probe: pages 34–35</h2><p>Same two supplementary pages rendered by fixed pdfrune at both 200 and 400 DPI; all four models rerun at each DPI (16 additional page outputs). The visible word is Per- + son. = Person. These pages have no full-page gold references and are excluded from the main CER. True means the exact expected word crosses the mapped boundary; this is one positive case per model, not a general success rate.</p><table><tr><th>Model</th><th>200 text repair</th><th>400 text repair</th><th>200 + visual</th><th>400 + visual</th></tr>"
        + "".join(probe_rows)
        + "</table>"
        + "".join(probe_evidence)
    )
    diagnostic_rows = "".join(
        f"<tr><td>{r['name']}</td><td>{r['renderer']} / {r['dpi']} DPI</td><td>{r['input_size']}</td><td>{100 * r['cer']:.2f}%</td><td>{r['generation_tokens']}</td><td>{r['possibly_truncated']}</td></tr>"
        for r in diagnostics["cases"]
    )
    retry = diagnostics["single_case_retry_aggregate"]
    retry_note = (
        f"The explicit lower-cap retry, substituted only for the token-limit failure, gives {100 * retry['cer']:.2f}% CER over the same 14 references. That diagnostic variant is separate from the primary score and does not establish a validated production retry policy."
        if retry
        else "No completed lower-cap retry was available for a guarded aggregate."
    )
    diagnostic_section = (
        "<h2>GLM repetition failure and controls</h2><p>The raw native-400 GLM output on PDF29 repeats text until its 8192-token limit. The primary error totals retain this failure. Character error rates can exceed 100% when insertion errors repeat large amounts of text. Source-preserving page-break repair does not fix a repetition loop.</p><table><tr><th>Case</th><th>Render</th><th>Harness pixels</th><th>Page29 CER</th><th>Tokens</th><th>Token-limit flag</th></tr>"
        + diagnostic_rows
        + "</table><p>"
        + retry_note
        + "</p>"
    )
    body = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>400-DPI pdfrune rerun</title><style>body{{font:16px/1.5 system-ui;margin:24px;background:#f7f9fc;color:#172536}}table{{border-collapse:collapse}}td,th{{border:1px solid #ccd4df;padding:9px;text-align:left;vertical-align:top}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.5 monospace}}.row{{display:flex;gap:14px;overflow:auto;align-items:start}}article{{flex:0 0 460px;padding:14px;background:white;border:1px solid #d3dbe6}}img{{width:100%}}summary{{cursor:pointer;padding:12px;background:#eaf0f8;margin:6px 0}}p{{max-width:1150px}}</style><h1>Fixed pdfrune at 400 DPI: paired rerun</h1><p>Same 16 pages, four local models, 64 fresh OCR outputs and 12 adjacent boundaries. All native renders visually reviewed, with no fallback. Same 14 frozen provisional visual references; prescription pages 70–71 remain qualitative. These are diagnostic results, not independently adjudicated benchmark scores.</p><p>Both renderer and DPI change against the frozen PDFium 200-DPI baseline. This measures their combined effect; it does not isolate DPI causally. Model pins, prompts, temperature, resize caps, assembly policies and scoring stay fixed. Lower CER/WER is better; negative changes indicate improvement.</p><table><tr><th>Pipeline</th><th>200 CER</th><th>400 CER</th><th>Change, pp</th><th>200 WER</th><th>400 WER</th></tr>{"".join(summary)}</table><p>Paddle book assembly retains notes and suppresses duplicate layout regions using the same policy at both resolutions. It reuses each run's saved region OCR, without replacement prose or extra recognition.</p><h2>Fraktur versus Antiqua</h2><table><tr><th>Book</th><th>Pipeline</th><th>200 CER</th><th>400 CER</th><th>Change, pp</th></tr>{"".join(book_rows)}</table><h2>Page-break repair</h2><p>Same local Qwen3 classifier and source-preserving rules. Correct joins require the exact expected word to cross the recorded boundary offset; substring matches elsewhere do not count. Four split-word cases and eight non-split controls. The Fraktur primary boundaries are non-split controls; do not interpret this as four Fraktur hyphen successes.</p><table><tr><th>Pipeline</th><th>200 correct split words</th><th>400 correct split words</th><th>200 wrong control joins</th><th>400 wrong control joins</th></tr>{"".join(flow_rows)}</table><h2>Local visual repair</h2><p>Same shared layout crops, local GLM crop recognition, matching edge-word gate and Qwen approval. Edits can remove only a mapped separator. All source spans and coordinates are verified. Evaluation labels are never prompted to the models. This tiny set cannot establish production false-join rates.</p><table><tr><th>Pipeline + visual</th><th>200 correct split words</th><th>400 correct split words</th><th>400 additional joins</th><th>Wrong added joins on controls</th></tr>{"".join(visual_rows)}</table>{"".join(evidence)}{probe_section}<h2>Actual input sizes</h2><p>Illustrative first selected page of each book: the raster DPI is not the final model input resolution. Existing harness resize caps remain fixed; model processors and layout pipelines may resize further. Thus the giant Antiqua pages receive similar capped input sizes, while the small Fraktur pages gain many more input pixels. Full per-page sizes and hashes are in the JSON report. Timings are observed inference, not controlled throughput measurements.</p><table><tr><th>Book</th><th>Model</th><th>200 harness pixels</th><th>400 harness pixels</th><th>400 render pixels</th></tr>{"".join(dimensions)}</table><h2>Page-level error changes</h2><table><tr><th>Book</th><th>PDF page</th><th>Pipeline</th><th>200 CER</th><th>400 CER</th><th>Change, pp</th></tr>{"".join(page_rows)}</table><h2>Inspect every scan and paired OCR output</h2>{"".join(cards)}<h2>All paired baseline boundary decisions</h2><table><tr><th>Model</th><th>Boundary</th><th>Expected</th><th>200 action / exact word</th><th>400 action / exact word</th><th>200 context</th><th>400 context</th></tr>{"".join(boundary_cards)}</table></html>"""
    diagnostic_section += "".join(
        f"<details><summary>Inspect GLM control output: {r['name']}</summary><pre>{html.escape(r['markdown'])}</pre></details>"
        for r in diagnostics["cases"]
    )
    body = body.replace(
        "<h2>Fraktur versus Antiqua</h2>", diagnostic_section + "<h2>Fraktur versus Antiqua</h2>"
    )
    body = body.replace(
        "<th>200 wrong control joins</th>",
        "<th>200 operations matching labels</th><th>400 operations matching labels</th><th>200 wrong control joins</th>",
    )
    body = body.replace(
        "<h1>Fixed pdfrune at 400 DPI: paired rerun</h1>",
        '<h1>Fixed pdfrune at 400 DPI: paired rerun</h1><p style="background:#fff3bf;padding:16px"><strong>Quality flag:</strong> GLM repeated a paragraph on Fraktur PDF29 and reached its token cap. This failure remains in the primary scores; see the controlled diagnostic below. A higher render DPI is not a guarantee of better OCR.</p>',
    )
    findings = (
        "<h2>What improved?</h2><p>400 DPI was not a general quality upgrade on these pages. "
        "Ovis remains the strongest unmodified recognizer in both runs. TeleOCR improved on every Fraktur page, "
        "but remains less accurate than Ovis and Paddle book assembly. Ovis and Paddle CER became slightly worse. "
        "The main comparison changes both renderer and DPI; the matched Fraktur probe and GLM controls narrow the interpretation.</p>"
        "<p>Exact split-word recovery stayed unchanged: Ovis 0/4 with text repair and 1/4 with visual repair; "
        "Paddle 1/4 and 3/4 respectively. Across all 12 labeled boundary operations, Paddle improved from 4 to 6 matches "
        "and Tele from 6 to 8, while Ovis fell from 4 to 3; GLM stayed at 8. No added word join occurred on the eight "
        "non-split controls for either visual-repair model. These provisional labels and small counts need review.</p>"
        "<p>The single Fraktur Per- / son. boundary stayed unresolved for every model at both DPIs. "
        "Paddle read the continuation more accurately at 400 DPI, but the GLM crop reader still read son as jon; "
        "the matching gate deferred. Source-preserving stitching cannot replace misrecognized letters.</p>"
        f"<p>The observed main visual-worker wall time increased from {old['visual_worker_seconds']:.1f}s to "
        f"{new['visual_worker_seconds']:.1f}s. It reads crops from the original rasters, so the giant first-book "
        "400-DPI crops cost substantially more. This is an observed run, not a controlled throughput benchmark.</p>"
    )
    body = body.replace(
        "<table><tr><th>Pipeline</th>", findings + "<table><tr><th>Pipeline</th>", 1
    )
    (out / "comparison.html").write_text(body)
    markdown.extend(
        [
            "",
            "## Per-book CER",
            "",
            "| Book | Pipeline | 200 DPI | 400 DPI |",
            "|---|---|---:|---:|",
        ]
    )
    for a, b in zip(old["models"], new["models"], strict=True):
        for bid in a["books"]:
            markdown.append(
                f"| {bid} | {b['name']} | {100 * a['books'][bid]['cer']:.2f}% | {100 * b['books'][bid]['cer']:.2f}% |"
            )
    markdown.extend(
        [
            "",
            "## Page-break continuity",
            "",
            "| Pipeline | Text-only 200 → 400 | With visual 200 → 400 |",
            "|---|---|---|",
        ]
    )
    for a, b in zip(old["models"], new["models"], strict=True):
        if b["name"] in MODELS:
            markdown.append(
                f"| {b['name']} | {a['correct_split_words']}/4 → {b['correct_split_words']}/4 | "
                + (
                    f"{a['visual_correct_split_words']}/4 → {b['visual_correct_split_words']}/4"
                    if b["name"] in {"ovisocr3", "paddle-vl"}
                    else "not tested"
                )
                + " |"
            )
    markdown.extend(
        [
            "",
            "## Matched Fraktur hyphen probe",
            "",
            "Two supplementary pages (34–35) were rerun with fixed pdfrune at both 200 and 400 DPI for all four models: 16 extra page outputs. The visible split is Per- + son. = Person. These pages have no full-page reference and are excluded from primary CER. The HTML/JSON includes exact baseline and visual continuity results and original crop evidence.",
            "",
            "Input DPI is distinguished from actual capped model-input sizes in the HTML/JSON. Native renderer commit: e174cbc6f80c1707ba048e46b9810cc85a8995d9. All source maps preserve exact OCR source characters; ambiguous joins remain review cases. No inference service or paid API was used.",
            "",
            "Reproduce from the project root:",
            "",
            "```bash",
            ".venv/bin/python scripts/prepare_400.py",
            ".venv/bin/python scripts/run_expanded.py --base workspace/expanded400 --selection datasets/expanded400/selection.json --phase ocr",
            ".venv/bin/python scripts/run_400_followup.py",
            ".venv/bin/python scripts/build_400_report.py",
            "```",
            "",
        ]
    )
    markdown.extend(
        [
            "",
            "## GLM repetition diagnostics",
            "",
            "The 400-DPI GLM page29 repetition reached its token limit and is retained in the primary CER. Insertion-heavy repetitions can yield CER above 100%.",
            "",
            "| Case | Page29 CER | Token-limit flag |",
            "|---|---:|---|",
        ]
    )
    for r in diagnostics["cases"]:
        markdown.append(f"| {r['name']} | {100 * r['cer']:.2f}% | {r['possibly_truncated']} |")
    markdown.extend(["", retry_note, ""])
    markdown.extend(
        [
            "",
            "## Interpretation",
            "",
            "400 DPI was not a general quality upgrade. Ovis remains strongest on this sample; TeleOCR improved on every Fraktur page but remains less accurate than Ovis and Paddle book assembly. The small Ovis/Paddle degradations are diagnostic observations, not universal rankings.",
            "",
            "Exact split-word results did not change: Ovis text-only 0/4 and visual 1/4; Paddle text-only 1/4 and visual 3/4. Across all 12 labeled boundary operations, Paddle improved 4→6 matches and Tele 6→8; Ovis fell 4→3; GLM stayed at 8. No additional visual word join occurred on the eight non-split controls for either model.",
            "",
            "The matched Fraktur Per- / son. probe was unresolved for every model at both DPIs. Paddle's continuation improved at 400 DPI, but GLM visual OCR misread son as jon and the gate deferred. Preserving source characters means the repair cannot silently replace those letters.",
            "",
            "GLM repeated page29 with both pdfrune and PDFium at 400 DPI. Native 200 DPI and a lower-cap retry of the identical native-400 raster completed normally. The single-case lower-cap retry gives 2.63% aggregate CER; its separate diagnostic score does not replace the primary failure or validate a general retry policy.",
            "",
            f"Observed visual-worker wall time: {old['visual_worker_seconds']:.1f}s → {new['visual_worker_seconds']:.1f}s. Same algorithm, larger original-image crops; timings are not controlled throughput comparisons.",
            "",
        ]
    )
    (out / "comparison.md").write_text("\n".join(markdown))
    print(
        json.dumps(
            [
                {
                    k: m[k]
                    for k in [
                        "name",
                        "cer",
                        "wer",
                        "books",
                        "correct_split_words",
                        "visual_correct_split_words",
                    ]
                }
                for m in new["models"]
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
