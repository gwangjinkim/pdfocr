"""Build a self-contained review from frozen runs, references and visual evidence."""

import base64
import html
import io
import re
from pathlib import Path

from PIL import Image

from pdfocr.book_compare import content_text, rates
from pdfocr.util import file_hash, read_json, write_json
from pdfocr.visual_repair import norm

ROOT = Path.cwd()
BASE = ROOT / "workspace/expanded"
OUT = BASE / "report"
OUT.mkdir(exist_ok=True)


def image_url(path, maximum=(1000, 1500)):
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail(maximum)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def boundary_result(label, decision, text, mapping):
    pos = decision["output_offset"]
    left = text[:pos]
    right = text[pos:]
    a = re.search(r"([^\W\d_]+)$", left)
    b = re.match(r"([^\W\d_]+)", right)
    lexical = (
        bool(
            a and b and label["expected_join"] and norm(a[1] + b[1]) == norm(label["expected_join"])
        )
        if label["expected_action"] == "join_word"
        else None
    )
    return {
        "expected_action": label["expected_action"],
        "action": decision["action"],
        "word_join_correct": lexical,
        "false_word_join": label["expected_action"] != "join_word"
        and decision["action"] == "join_word",
        "action_matches_label": decision["action"] == label["expected_action"],
        "context": text[max(0, pos - 90) : min(len(text), pos + 90)],
        "offset": pos,
    }


def main():
    selection = read_json(ROOT / "datasets/expanded/selection.json")
    index = read_json(BASE / "index.json")
    labels = read_json(ROOT / "datasets/expanded/boundaries.json")
    visual = read_json(BASE / "visual/results.json")
    data = {
        "selection": selection,
        "reference_status": "14 full-page provisional assistant visual transcriptions; two prescription pages reviewed without CER gold. No independent human adjudication.",
        "metrics_note": "CER/WER include case, historical spelling and punctuation; furniture/emphasis/internal line-wrap hyphens normalized. These are transcript edit rates, not semantic accuracy. Footnotes belong in the all-readable-text contract.",
        "models": [],
        "boundaries": [],
        "visual": visual,
        "references": read_json(ROOT / "datasets/expanded/reference-hashes.json"),
    }
    cards = []
    for name in ["glm-ocr", "ovisocr3", "paddle-vl", "teleocr"]:
        row = {
            "name": name,
            "pages": [],
            "books": {},
            "inference_seconds": 0,
            "worker_seconds": 0,
            "boundary_results": [],
        }
        for book in selection["books"]:
            bid = book["id"]
            run = Path(index["books"][bid][name])
            manifest = read_json(run / "manifest.json")
            doc = read_json(ROOT / book["document"] / "document.json")
            if (
                manifest["status"] != "complete"
                or manifest["source_sha256"] != doc["source_sha256"]
            ):
                raise ValueError("Invalid comparison run")
            rows = []
            for page in manifest["pages"]:
                value = read_json(run / page["result"])
                n = page["page"]
                row["inference_seconds"] += value["seconds"]
                ref = ROOT / "datasets/expanded/references" / bid / f"page-{n:04d}.txt"
                if not ref.exists():
                    continue
                truth = content_text(ref.read_text())
                pred = content_text(value["markdown"])
                score = {
                    "book": bid,
                    "page": n,
                    "reference_sha256": file_hash(ref),
                    **rates(truth, pred),
                    "run": str(run),
                    "possibly_truncated": value.get("possibly_truncated", False),
                }
                rows.append(score)
                row["pages"].append(score)
            row["books"][bid] = {
                "scored_pages": len(rows),
                "cer": sum(r["character_edits"] for r in rows)
                / sum(r["reference_characters"] for r in rows),
                "wer": sum(r["word_edits"] for r in rows) / sum(r["reference_words"] for r in rows),
            }
            row["worker_seconds"] += manifest["process"]["seconds"]
            flow = run.parents[1] / f"flow-{run.name}.proposed.md"
            mapping = read_json(flow.with_suffix(".pages.json"))
            text = flow.read_text()
            decisions = mapping["boundaries"]
            for label in [item for item in labels if item["book"] == bid]:
                decision = next(
                    d
                    for d in decisions
                    if d["left_page"] == label["left_page"]
                    and d["right_page"] == label["right_page"]
                )
                result = {
                    "book": bid,
                    "model": name,
                    "left_page": label["left_page"],
                    "right_page": label["right_page"],
                    **boundary_result(label, decision, text, mapping),
                }
                row["boundary_results"].append(result)
                data["boundaries"].append(result)
        row["cer"] = sum(r["character_edits"] for r in row["pages"]) / sum(
            r["reference_characters"] for r in row["pages"]
        )
        row["wer"] = sum(r["word_edits"] for r in row["pages"]) / sum(
            r["reference_words"] for r in row["pages"]
        )
        row["book_macro_cer"] = sum(b["cer"] for b in row["books"].values()) / len(row["books"])
        row["word_joins_correct"] = sum(
            b["word_join_correct"] is True for b in row["boundary_results"]
        )
        row["false_word_joins"] = sum(b["false_word_join"] for b in row["boundary_results"])
        row["deferred_boundaries"] = sum(
            b["action"] == "uncertain" for b in row["boundary_results"]
        )
        data["models"].append(row)
    visual_summary = []
    for name in ["ovisocr3", "paddle-vl"]:
        results = []
        for book in selection["books"]:
            bid = book["id"]
            flow = BASE / "visual" / bid / f"{name}-visual.proposed.md"
            mapping = read_json(flow.with_suffix(".pages.json"))
            text = flow.read_text()
            for label in [item for item in labels if item["book"] == bid]:
                decision = next(
                    d
                    for d in mapping["boundaries"]
                    if d["left_page"] == label["left_page"]
                    and d["right_page"] == label["right_page"]
                )
                result = boundary_result(label, decision, text, mapping)
                evidence = next(
                    d
                    for d in visual["decisions"]
                    if d["book"] == bid
                    and d["model"] == name
                    and d["left_page"] == label["left_page"]
                )
                result.update(
                    book=bid,
                    left_page=label["left_page"],
                    right_page=label["right_page"],
                    visual_applied=evidence["applied"],
                    gate=evidence["gate"],
                )
                if evidence["applied"]:
                    result["action"] = "visual_join_word"
                    result["false_word_join"] = label["expected_action"] != "join_word"
                results.append(result)
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
        visual_summary.append(
            {
                "model": name,
                "correct_split_words": sum(r["word_join_correct"] is True for r in results),
                "split_word_cases": 4,
                "applied": sum(r["visual_applied"] for r in results),
                "false_added_word_joins": sum(
                    r["visual_applied"] and r["expected_action"] != "join_word" for r in results
                ),
                "non_split_controls": 8,
                "results": results,
            }
        )
    book_variant = read_json(BASE / "paddle-book-index.json")
    variant_pages = []
    for bid, run in book_variant.items():
        for record in read_json(Path(run) / "manifest.json")["pages"]:
            ref = ROOT / "datasets/expanded/references" / bid / f"page-{record['page']:04d}.txt"
            if ref.exists():
                variant_pages.append(
                    {
                        "book": bid,
                        "page": record["page"],
                        **rates(
                            content_text(ref.read_text()),
                            content_text(read_json(Path(run) / record["result"])["markdown"]),
                        ),
                    }
                )
    data["paddle_book_variant"] = {
        "pages": variant_pages,
        "cer": sum(v["character_edits"] for v in variant_pages)
        / sum(v["reference_characters"] for v in variant_pages),
        "wer": sum(v["word_edits"] for v in variant_pages)
        / sum(v["reference_words"] for v in variant_pages),
        "method": "postprocessing of the identical saved real region OCR; retain footnotes, suppress IoU>0.9 duplicates across labels; no text rewriting",
    }
    data["visual_summary"] = visual_summary
    probe = read_json(ROOT / "workspace/fraktur-hyphen-probe/visual/results.json")
    data["fraktur_probe"] = {
        "pages": [34, 35],
        "book": "makrobiotikoderd00hufeuoft",
        "dpi": 400,
        "renderer": "pdfrune, strict native rendering",
        "excluded_from_primary_metrics": True,
        "visible_split_word": "Per- + son. = Person",
        "results": probe["decisions"],
        "applied_joins": sum(d["applied"] for d in probe["decisions"]),
    }
    write_json(OUT / "comparison.json", data)
    summary = "".join(
        f"<tr><td>{m['name']}</td><td>{100 * m['cer']:.2f}%</td><td>{100 * m['wer']:.2f}%</td><td>{100 * m['books']['10289757bsb']['cer']:.2f}%</td><td>{100 * m['books']['makrobiotikoderd00hufeuoft']['cer']:.2f}%</td><td>{m['word_joins_correct']}/4</td><td>{m['false_word_joins']}/8</td><td>{m['inference_seconds']:.1f}s</td></tr>"
        for m in data["models"]
    )
    pv = data["paddle_book_variant"]
    summary += f"<tr><td>Paddle book assembly (same OCR)</td><td>{100 * pv['cer']:.2f}%</td><td>{100 * pv['wer']:.2f}%</td><td colspan='5'>Retains footnotes; removes duplicate layout region. Additional OCR inference: zero.</td></tr>"
    vs = "".join(
        f"<tr><td>{v['model']}</td><td>{v['correct_split_words']}/4</td><td>{v['applied']}</td><td>{v['false_added_word_joins']}/8</td></tr>"
        for v in visual_summary
    )
    for book in selection["books"]:
        bid = book["id"]
        docpath = ROOT / book["document"]
        doc = read_json(docpath / "document.json")
        for p in doc["pages"]:
            n = p["page"]
            cells = [
                f'<article><h3>Source scan</h3><img src="{image_url(docpath / p["image"])}"></article>'
            ]
            for name, runpath in index["books"][bid].items():
                value = read_json(Path(runpath) / f"page-{n:04d}.json")
                cells.append(
                    f"<article><h3>{name}</h3><pre>{html.escape(value['markdown'])}</pre></article>"
                )
            if bid in book_variant:
                book_output = read_json(Path(book_variant[bid]) / f"page-{n:04d}.json")
                cells.append(
                    f"<article><h3>Paddle book assembly</h3><pre>{html.escape(book_output['markdown'])}</pre></article>"
                )
            reference = ROOT / "datasets/expanded/references" / bid / f"page-{n:04d}.txt"
            if reference.exists():
                cells.append(
                    f"<article><h3>Provisional reference</h3><pre>{html.escape(reference.read_text())}</pre></article>"
                )
            else:
                cells.append(
                    "<article><h3>Symbol/structure review</h3><p>No full CER gold: apothecary symbols have not been independently adjudicated. Compare lists, quantities and headings directly to the scan.</p></article>"
                )
            cards.append(
                f'<details class="page" data-book="{bid}"><summary>{bid} — PDF {n}</summary><div class="row">'
                + "".join(cells)
                + "</div></details>"
            )
    boundary_rows = "".join(
        f"<tr><td>{r['book']}</td><td>{r['left_page']}→{r['right_page']}</td><td>{r['model']}</td><td>{r['expected_action']}</td><td>{r['action']}</td><td>{r['word_join_correct'] if r['word_join_correct'] is not None else 'control'}</td><td><pre>{html.escape(r['context'])}</pre></td></tr>"
        for r in data["boundaries"]
    )
    evidence_cards = []
    for d in visual["decisions"]:
        if d["applied"] or (d["book"] == "10289757bsb" and d["left_page"] == 12):
            images = "".join(
                f'<article><h3>{side} edge</h3><img src="{image_url(d[side + "_edge"]["crop"], (1600, 600))}"><pre>{html.escape(d[side + "_edge"]["text"])}</pre></article>'
                for side in ["left", "right"]
                if d[side + "_edge"]
            )
            evidence_cards.append(
                f'<details><summary>{d["model"]}: {d["book"]} {d["left_page"]}→{d["right_page"]}: {"APPLIED" if d["applied"] else "DEFERRED"}</summary><p>{html.escape(d["gate"]["reason"])}</p><div class="row">{images}</div></details>'
            )
    probe_cards = []
    for decision in probe["decisions"]:
        images = "".join(
            f'<article><h3>{side} edge</h3><img src="{image_url(decision[side + "_edge"]["crop"], (1600, 600))}"><pre>{html.escape(decision[side + "_edge"]["text"])}</pre></article>'
            for side in ["left", "right"]
        )
        probe_cards.append(
            f'<details><summary>{decision["model"]}: Fraktur 34→35, DEFERRED</summary><p>{html.escape(decision["gate"]["reason"])}</p><div class="row">{images}</div></details>'
        )
    probe_section = (
        '<h2>Extra Fraktur hyphen probe: native pdfrune, 400 DPI</h2>'
        '<p>Two additional pages (PDF 34–35), run for Ovis and Paddle, are excluded from the primary scores above. '
        'The scan shows Per- + son. = Person. Ovis retained the hyphen but misread the continuation; '
        'Paddle dropped the hyphen, and the local GLM crop reader read son as jon. Both visual repairs deferred. '
        'This preserves a real failure: this visual reader is not yet reliable for Fraktur.</p>'
        + "".join(probe_cards)
    )
    body = f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Expanded local PDF OCR comparison</title><style>body{{font:16px/1.5 system-ui;margin:24px;color:#172536;background:#f7f9fc}}table{{border-collapse:collapse;max-width:100%}}td,th{{border:1px solid #ccd4df;padding:9px;text-align:left;vertical-align:top}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.5 monospace}}.row{{display:flex;gap:14px;overflow:auto;align-items:start}}article{{flex:0 0 430px;padding:14px;background:white;border:1px solid #d3dbe6}}img{{width:100%}}summary{{cursor:pointer;padding:12px;background:#eaf0f8;margin:6px 0}}p{{max-width:1100px}}select{{font:inherit;padding:8px}}</style><h1>16 pages, two Archive.org books, 12 page boundaries</h1><p>All four local models completed all 16 pages. Scores cover 14 full-page provisional visual references; prescription pages 70–71 remain qualitative symbol/structure tests. Historical spelling, case, punctuation and readable footnotes count. Lower edit rates are better. This is a small diagnostic sample, not an independent benchmark.</p><table><tr><th>Model</th><th>Overall CER</th><th>Overall WER</th><th>Antiqua CER (6 pages)</th><th>Fraktur CER (8 pages)</th><th>Correct split words</th><th>Wrong word joins on controls</th><th>16-page observed inference*</th></tr>{summary}</table><p>*Times include model-specific layout/crop processing; TeleOCR loads a CLI per page. Setup/build overlap and runtime differences prevent a controlled throughput ranking. All use the same verified 200-DPI page images within each book; profile resizing differs.</p><h2>Local visual hyphen repair</h2><p>Shared Paddle layout geometry selects body edges; GLM-OCR reads the image crops locally. The gate requires a visible terminal hyphen, matching OCR words on both sides, adjacency, and Qwen3 approval. Only a mapped inter-page separator can be removed. Raw OCR and source characters are untouched; all output spans were verified against raw sources. The models are not prompted with evaluation labels.</p><table><tr><th>Model + visual repair</th><th>Correct split words</th><th>Additional joins</th><th>Wrong additional joins on controls</th></tr>{vs}</table><p>There are four positive split-word boundaries and eight non-split controls, tested for each model. This tiny set does not establish a production false-join rate. The footnote boundary remains a review case; hallucinated word completions and lexical mismatches are deliberately deferred.</p>{"".join(evidence_cards)}{probe_section}<h2>Inspect every page</h2><p>Raw model text is escaped, not executed. The footnote on PDF 12 matters: Paddle's default Markdown assembly excludes it even though its raw region response retains it. That is a pipeline setting, not proof the recognizer cannot read notes.</p>{"".join(cards)}<h2>All baseline boundary decisions</h2><table><tr><th>Book</th><th>Pages</th><th>Model</th><th>Expected</th><th>Action</th><th>Split-word result</th><th>Exact output context</th></tr>{boundary_rows}</table><h2>Renderer repair</h2><p>The original pdfrune renderer skipped JPEG/JPX scans and painted invisible OCR. It has been repaired and installed: JPEG, JPEG2000, JBIG2 SMask compositing, and 3 Tr suppression are now native Rust. All 16 selected pages rendered without fallback in separate verification. This OCR comparison retains its frozen, independently verified PDFium input pixels to keep its model inputs unchanged. No inference server or paid API was used. <a href="pdfrune-rendering-repair.html">Inspect the pdfrune before/after repair</a>.</p></html>"""
    (OUT / "comparison.html").write_text(body)
    for m in data["models"]:
        print(
            m["name"],
            round(m["cer"] * 100, 3),
            round(m["wer"] * 100, 3),
            m["word_joins_correct"],
            "of 4 word joins",
        )
    print(
        "visual",
        [
            (v["model"], v["correct_split_words"], v["applied"], v["false_added_word_joins"])
            for v in visual_summary
        ],
    )


if __name__ == "__main__":
    main()
