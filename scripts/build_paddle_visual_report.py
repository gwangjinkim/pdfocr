"""Evaluate the reader swap using frozen labels, pixels and source maps."""

import html
import json
import re
from pathlib import Path

from build_expanded_report import boundary_result, image_url

from pdfocr.util import file_hash, read_json, write_json
from pdfocr.visual_repair import WORD, body_text, norm

ROOT = Path.cwd()
BASE = ROOT / "workspace/paddle-visual-fraktur"


def verified_flow(path, baseline=None):
    mapping = read_json(path.with_suffix(".pages.json"))
    text = path.read_text()
    raw = Path(mapping["raw_file"]).read_text()
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
    if baseline:
        original = baseline.read_text()
        for removal in sorted(
            mapping["visual_separator_removals"], key=lambda x: x["old_start"], reverse=True
        ):
            assert (
                original[removal["old_start"] : removal["old_end"]] == removal["removed_separator"]
            )
            assert removal["removed_separator"].isspace()
            original = original[: removal["old_start"]] + original[removal["old_end"] :]
        assert original == text
    return text, mapping


def score(label, path, baseline=None):
    text, mapping = verified_flow(path, baseline)
    decision = next(
        d
        for d in mapping["boundaries"]
        if (d["left_page"], d["right_page"]) == (label["left_page"], label["right_page"])
    )
    return {**boundary_result(label, decision, text, mapping), "file": str(path)}


def main():
    jobs = read_json(BASE / "jobs.json")
    control_labels = [
        d
        for d in read_json(ROOT / "datasets/expanded/boundaries.json")
        if d["book"] == "makrobiotikoderd00hufeuoft"
    ]
    positive = read_json(ROOT / "datasets/expanded400/probe-boundary.json")
    rows = []
    for job in jobs:
        request = read_json(Path(job["request"]))
        index = read_json(Path(request["index"]))["books"][job["book"]]
        paddle = read_json(Path(job["out"]) / "results.json")
        glm = read_json(Path(job["glm_out"]) / "results.json")
        labels = control_labels if job["name"].startswith("controls") else [positive]
        for model in ["ovisocr3", "paddle-vl"]:
            run = Path(index[model])
            baseline = run.parents[1] / f"flow-{run.name}.proposed.md"
            new_path = Path(job["out"]) / job["book"] / f"{model}-visual.proposed.md"
            old_path = Path(job["glm_out"]) / job["book"] / f"{model}-visual.proposed.md"
            for label in labels:

                def evidence(result):
                    return next(
                        d
                        for d in result["decisions"]
                        if d["book"] == job["book"]
                        and d["model"] == model
                        and d["left_page"] == label["left_page"]
                        and d["right_page"] == label["right_page"]
                    )

                pe, ge = evidence(paddle), evidence(glm)
                for side in ["left_edge", "right_edge"]:
                    for field in ["crop_sha256", "source_image_sha256", "box_source_pixels"]:
                        assert pe[side][field] == ge[side][field]
                    assert file_hash(Path(pe[side]["crop"])) == pe[side]["crop_sha256"]
                    assert (
                        file_hash(Path(pe[side]["source_image"])) == pe[side]["source_image_sha256"]
                    )
                left = read_json(run / f"page-{label['left_page']:04d}.json")["markdown"]
                right = read_json(run / f"page-{label['right_page']:04d}.json")["markdown"]
                a = re.search("(" + WORD + r")(?P<hyphen>[-¬\u00ad])?\s*$", body_text(left))
                b = re.match("(" + WORD + ")", body_text(right))
                repairable = bool(
                    label["expected_action"] == "join_word"
                    and a
                    and b
                    and not a["hyphen"]
                    and norm(a[1] + b[1]) == norm(label["expected_join"])
                )
                rows.append(
                    {
                        "job": job["name"],
                        "dpi": int(job["name"].split("-")[-1]),
                        "model": model,
                        "book": job["book"],
                        "left_page": label["left_page"],
                        "right_page": label["right_page"],
                        "expected_action": label["expected_action"],
                        "expected_word": label["expected_join"],
                        "source_stems_correct_and_hyphen_missing": repairable,
                        "raw_left_end": left[-180:],
                        "raw_right_start": right[:180],
                        "baseline": score(label, baseline),
                        "glm": {**score(label, old_path, baseline), "evidence": ge},
                        "paddle": {**score(label, new_path, baseline), "evidence": pe},
                        "added_false_join": pe["applied"]
                        and label["expected_action"] != "join_word",
                    }
                )
    positives = [r for r in rows if r["expected_action"] == "join_word"]
    controls = [r for r in rows if r["expected_action"] != "join_word"]
    applied = [r for r in rows if r["paddle"]["evidence"]["applied"]]
    summary = {
        "cases": len(rows),
        "positive_model_resolution_cases": len(positives),
        "unique_positive_boundaries": 1,
        "repairable_missing_hyphen_cases": sum(
            r["source_stems_correct_and_hyphen_missing"] for r in positives
        ),
        "correct_added_joins": sum(r["paddle"]["word_join_correct"] is True for r in applied),
        "applied_joins": len(applied),
        "false_added_joins_on_controls": sum(r["added_false_join"] for r in controls),
        "negative_model_resolution_cases": len(controls),
        "unique_negative_boundaries": len({(r["left_page"], r["right_page"]) for r in controls}),
        "all_source_spans_exact": True,
        "only_separator_deletions": True,
        "frozen_glm_crop_pixels_match": True,
    }
    assert len(rows) == 28 and len(positives) == 4 and len(controls) == 24
    assert (
        len(applied) == 1
        and summary["correct_added_joins"] == 1
        and summary["false_added_joins_on_controls"] == 0
    )
    result = {
        "date": "2026-10-23",
        "reader": "PaddleOCR-VL-1.6 BF16, local MLX, OCR: prompt",
        "vision_pin": read_json(ROOT / "models/paddle-vl.json"),
        "text_pin": read_json(ROOT / "models/boundary-small.json"),
        "summary": summary,
        "cases": rows,
        "limits": "One positive physical boundary and six negative physical boundaries, repeated at two resolutions and against two OCR sources. These are dependent tests, not a production false-join-rate estimate. Provisional assistant visual labels; no independent human gold.",
        "method": "Only the crop reader/prompt changes versus GLM. Same frozen image crops, page OCR, lexical gate, Qwen3 classifier, adjacency guard and separator-only source edits. The worker reads no evaluation labels.",
    }
    out = BASE / "report"
    out.mkdir(exist_ok=True)
    write_json(out / "comparison.json", result)
    positive_rows = "".join(
        f"<tr><td>{r['dpi']}</td><td>{r['model']}</td><td>{r['source_stems_correct_and_hyphen_missing']}</td><td>{r['glm']['word_join_correct']}</td><td>{r['paddle']['word_join_correct']}</td><td>{'APPLIED' if r['paddle']['evidence']['applied'] else 'DEFERRED'}</td><td>{html.escape(r['paddle']['evidence']['gate']['reason'])}</td></tr>"
        for r in positives
    )
    control_rows = []
    for dpi in [200, 400]:
        for model in ["ovisocr3", "paddle-vl"]:
            group = [r for r in controls if r["dpi"] == dpi and r["model"] == model]
            control_rows.append(
                f"<tr><td>{dpi}</td><td>{model}</td><td>{len(group)}</td><td>{sum(r['glm']['evidence']['applied'] for r in group)}</td><td>{sum(r['paddle']['evidence']['applied'] for r in group)}</td></tr>"
            )
    details = []
    for job in jobs:
        cases = [r for r in rows if r["job"] == job["name"]]
        pairs = sorted({(r["left_page"], r["right_page"]) for r in cases})
        for left, right in pairs:
            group = [r for r in cases if (r["left_page"], r["right_page"]) == (left, right)]
            first = group[0]
            pe = first["paddle"]["evidence"]
            ge = first["glm"]["evidence"]
            crops = "".join(
                f'<article><h3>{side} source crop</h3><img src="{image_url(pe[side + "_edge"]["crop"], (1800, 650))}"><h4>GLM read</h4><pre>{html.escape(ge[side + "_edge"]["text"])}</pre><h4>Paddle read</h4><pre>{html.escape(pe[side + "_edge"]["text"])}</pre></article>'
                for side in ["left", "right"]
            )
            target = "".join(
                f"<article><h3>{r['model']} page OCR</h3><pre>{html.escape(r['raw_left_end'])}\n|||\n{html.escape(r['raw_right_start'])}</pre><p>{'JOIN APPLIED' if r['paddle']['evidence']['applied'] else 'DEFERRED'}: {html.escape(r['paddle']['evidence']['gate']['reason'])}</p><h4>Exact final output context</h4><pre>{html.escape(r['paddle']['context'])}</pre></article>"
                for r in group
            )
            details.append(
                f'<details><summary>{job["name"]}: PDF {left}→{right}, {first["expected_action"]}</summary><div class="row">{crops}{target}</div></details>'
            )
    page = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Paddle local visual repair on Fraktur</title><style>body{{font:16px/1.5 system-ui;margin:24px;color:#172536;background:#f7f9fc}}p{{max-width:1100px}}table{{border-collapse:collapse}}td,th{{padding:10px;border:1px solid #ccd4df;text-align:left;vertical-align:top}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.5 monospace}}.row{{display:flex;gap:14px;overflow:auto;align-items:start}}article{{flex:0 0 470px;background:white;padding:14px;border:1px solid #d3dbe6}}img{{width:100%}}summary{{cursor:pointer;padding:12px;margin:8px 0;background:#eaf0f8}}.success{{background:#d9f2e3;padding:16px}}</style><h1>PaddleOCR-VL as the local Fraktur repair reader</h1><p class="success"><strong>One correct recovery: Per + son. → Person.</strong> Paddle's 400-DPI crop reads preserve Per- and recognize son.; the existing gate and local Qwen classifier approve removing the inter-page space. GLM read jon. and deferred. No word joins were added on the six non-split boundaries tested against both OCR outputs at both resolutions (24 control decisions).</p><p>The reader is PaddleOCR-VL-1.6 BF16 on local MLX, using its OCR: task prompt. Only the visual reader/prompt changes. Frozen crop hashes match the GLM experiment exactly; raw page OCR, geometry, temperature, 1024-token cap, lexical matching, adjacency and source-preserving rules stay fixed. No paid API or inference service.</p><h2>Positive Fraktur boundary: PDF34–35</h2><table><tr><th>DPI</th><th>Page OCR</th><th>Correct stems, missing hyphen</th><th>GLM final word correct</th><th>Paddle final word correct</th><th>Paddle repair</th><th>Gate</th></tr>{positive_rows}</table><p>At 200 DPI Paddle's crop read still drops the hyphen; its underlying page OCR also reads the continuation as ion. Ovis retains the original hyphen but reads ion. at both resolutions, so a separator-only repair cannot recover Person without changing source letters. Only the Paddle 400-DPI source has correct stems and a dropped hyphen: that one repairable case succeeds.</p><h2>False-join controls</h2><table><tr><th>DPI</th><th>Page OCR</th><th>Control decisions</th><th>GLM added joins</th><th>Paddle added joins</th></tr>{"".join(control_rows)}</table><p><strong>Scope:</strong> one distinct positive boundary and six distinct negative boundaries, repeated across resolutions and OCR sources. This does not establish production safety or a false-join rate. The controls cover normal prose continuation, a paragraph boundary and a chapter-to-body continuation. Evaluation labels are not prompted to the models.</p><h2>Source preservation</h2><p>The successful repair deletes one inter-page space. Every source-character span, output offset and SHA256 was checked; all other reading copies remain identical to their baseline. The original page OCR is preserved. Existing letter-recognition mistakes remain in the reading copy.</p><p><a href="paddle-fraktur-400dpi-repaired.md">Inspect the repaired reading copy</a> · <a href="paddle-fraktur-400dpi-raw.md">Raw page-separated OCR</a> · <a href="paddle-fraktur-400dpi-repaired.pages.json">Source map</a></p><h2>Inspect every positive and negative pair</h2>{"".join(details)}</html>"""
    (out / "comparison.html").write_text(page)
    lines = [
        "# Paddle local visual repair on Fraktur",
        "",
        "PaddleOCR-VL-1.6 BF16 / local MLX, OCR: prompt. Same frozen crops, gate, Qwen3 classifier and page OCR as the GLM experiment.",
        "",
        "**Result: one correct added join, no false joins on 24 control decisions.**",
        "",
        "At 400 DPI, Paddle reads Per- and son. and recovers Person in the Paddle OCR reading copy. GLM read jon. and deferred. The only edit deletes the inter-page space; every raw source character is preserved.",
        "",
        "At 200 DPI the crop read still drops the hyphen and the page OCR continuation is ion. Ovis keeps the hyphen but misreads ion. at both resolutions. Those cases defer; no letters are silently replaced.",
        "",
        "| DPI | Target page OCR | GLM word correct | Paddle word correct |",
        "|---:|---|---|---|",
    ]
    lines.extend(
        f"| {r['dpi']} | {r['model']} | {r['glm']['word_join_correct']} | {r['paddle']['word_join_correct']} |"
        for r in positives
    )
    lines.extend(
        [
            "",
            "The 24 negative decisions repeat six physical non-split boundaries at two resolutions against two OCR sources. There is only one physical positive boundary; one of its four OCR/resolution variants has correct stems and a dropped hyphen. That repairable variant succeeds. This is useful evidence, not a validated production false-join rate.",
            "",
            "All frozen crop/source hashes, exact source maps and separator-only edits were verified. No dependencies or model weights were downloaded, and no inference service was started.",
            "",
            "Reproduce from the project root:",
            "",
            "```bash",
            ".venv/bin/python scripts/run_paddle_visual.py",
            ".venv/bin/python scripts/build_paddle_visual_report.py",
            "```",
            "",
        ]
    )
    (out / "comparison.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
