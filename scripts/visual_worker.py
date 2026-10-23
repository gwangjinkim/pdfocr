"""One local foreground visual-hyphen experiment. Reads no evaluation labels."""

import math
import sys
import time
from pathlib import Path

from mlx_vlm import generate, load
from mlx_vlm.prompt_utils import apply_chat_template
from PIL import Image

from pdfocr.borrowed.archive_stitching import Page, PageStitcher
from pdfocr.repair import MLXDecisionBackend
from pdfocr.util import file_hash, read_json, write_json
from pdfocr.visual_repair import body_text, evidence_gate, remove_boundary_separators


def main(request):
    model, processor = load(request["vision_pin"]["path"], local_files_only=True)
    if request.get("vision_backend") == "paddle":
        from pdfocr.local_pipelines import paddle_batch_axis_compat

        paddle_batch_axis_compat(model)
    text_backend = MLXDecisionBackend(request["text_pin"]["path"])
    stitcher = PageStitcher(text_backend)
    index = read_json(Path(request["index"]))
    selection = read_json(Path(request["selection"]))
    out = Path(request["out"])
    out.mkdir(parents=True, exist_ok=True)
    all_records = []
    for book in selection["books"]:
        name = book["id"]
        if request.get("book_ids") and name not in request["book_ids"]:
            continue
        docpath = Path(book["document"])
        doc = read_json(docpath / "document.json")
        runs = index["books"][name]
        layout_run = Path(runs["paddle-vl"])
        layout_manifest = read_json(layout_run / "manifest.json")
        edges = {}
        for record in doc["pages"]:
            n = record["page"]
            source = docpath / record["image"]
            if file_hash(source) != record["image_sha256"]:
                raise ValueError("Source pixels changed")
            im = Image.open(source).convert("RGB")
            w, h = im.size
            entry = next(p for p in layout_manifest["inputs"] if p["page"] == n)
            iw, ih = entry["input_size"]
            scale = [w / iw, h / ih]
            blocks = [
                b
                for b in read_json(layout_run / f"page-{n:04d}.json")["raw"]["blocks"]
                if b["label"]
                in {
                    "text",
                    "content",
                    "paragraph_title",
                    "doc_title",
                    "reference",
                    "reference_content",
                }
            ]
            edges[n] = {}
            if not blocks:
                continue
            for side, block in [("top", blocks[0]), ("bottom", blocks[-1])]:
                x0, y0, x1, y1 = [v * scale[i % 2] for i, v in enumerate(block["bbox"])]
                amount = min(y1 - y0, max(80, h * 0.095))
                a, b = (y0, min(y1, y0 + amount)) if side == "top" else (max(y0, y1 - amount), y1)
                box = [
                    max(0, math.floor(x0 - w * 0.006)),
                    max(0, math.floor(a - h * 0.003)),
                    min(w, math.ceil(x1 + w * 0.006)),
                    min(h, math.ceil(b + h * 0.003)),
                ]
                folder = out / name
                folder.mkdir(exist_ok=True)
                crop = folder / f"page-{n:04d}-{side}.png"
                im.crop(box).save(crop)
                if request.get("frozen_crop_base"):
                    frozen = read_json(
                        Path(request["frozen_crop_base"]) / name / f"page-{n:04d}-{side}.json"
                    )
                    if (
                        frozen["source_image_sha256"] != record["image_sha256"]
                        or frozen["box_source_pixels"] != box
                        or frozen["crop_sha256"] != file_hash(crop)
                    ):
                        raise ValueError("Reader comparison crop differs from frozen GLM input")
                t = time.monotonic()
                prompt = apply_chat_template(
                    processor,
                    model.config,
                    request.get("vision_prompt", "Text Recognition:"),
                    num_images=1,
                )
                response = generate(
                    model,
                    processor,
                    prompt,
                    image=[str(crop)],
                    max_tokens=1024,
                    temperature=0.0,
                    verbose=False,
                )
                edge = {
                    "page": n,
                    "side": side,
                    "vision_backend": request.get("vision_backend", "glm"),
                    "prompt": request.get("vision_prompt", "Text Recognition:"),
                    "label": block["label"],
                    "crop": str(crop.resolve()),
                    "source_image": str(source.resolve()),
                    "source_image_sha256": file_hash(source),
                    "box_source_pixels": box,
                    "crop_sha256": file_hash(crop),
                    "text": response.text,
                    "seconds": time.monotonic() - t,
                    "tokens": response.generation_tokens,
                    "possibly_truncated": response.generation_tokens >= 1024,
                }
                write_json(folder / f"page-{n:04d}-{side}.json", edge)
                edges[n][side] = edge
                print(name, n, side, flush=True)
        for model_name in ["ovisocr3", "paddle-vl"]:
            run = Path(runs[model_name])
            flow = docpath / f"flow-{run.name}.proposed.md"
            mapping = read_json(flow.with_suffix(".pages.json"))
            decisions = []
            pairs = []
            nums = doc["selected_pages"]
            for left, right in zip(nums, nums[1:]):
                if right != left + 1:
                    continue
                le = edges.get(left, {}).get("bottom")
                re = edges.get(right, {}).get("top")
                a = read_json(run / f"page-{left:04d}.json")["markdown"]
                b = read_json(run / f"page-{right:04d}.json")["markdown"]
                gate = evidence_gate(
                    left_page=left,
                    right_page=right,
                    left_ocr=a,
                    right_ocr=b,
                    visual_left=le["text"] if le else "",
                    visual_right=re["text"] if re else "",
                )
                decision = {
                    "book": name,
                    "model": model_name,
                    "left_page": left,
                    "right_page": right,
                    "gate": gate,
                    "left_edge": le,
                    "right_edge": re,
                    "approved": False,
                }
                if (
                    gate["eligible"]
                    and le
                    and re
                    and not le["possibly_truncated"]
                    and not re["possibly_truncated"]
                    and re["label"] not in {"paragraph_title", "doc_title"}
                ):
                    classify = stitcher.decide(
                        Page(left, body_text(a) + "-"), Page(right, body_text(b))
                    )
                    decision["classifier"] = classify
                    if classify["action"] == "join_word":
                        pairs.append((left, right))
                        decision["approved"] = True
                decisions.append(decision)
            result = remove_boundary_separators(flow.read_text(), mapping, pairs)
            dest = out / name / f"{model_name}-visual.proposed.md"
            dest.write_text(result["text"])
            result["map"]["output_file"] = str(dest.resolve())
            write_json(dest.with_suffix(".pages.json"), result["map"])
            applied = {(p["left_page"], p["right_page"]) for p in result["applied"]}
            for d in decisions:
                d["applied"] = (d["left_page"], d["right_page"]) in applied
            write_json(dest.with_suffix(".decisions.json"), decisions)
            all_records.extend(decisions)
            raw = Path(mapping["raw_file"]).read_text()
            cursor = 0
            for span in result["map"]["spans"]:
                assert span["output_start"] == cursor
                if span["kind"] == "source":
                    assert (
                        result["text"][span["output_start"] : span["output_end"]]
                        == raw[span["raw_start"] : span["raw_end"]]
                    )
                cursor = span["output_end"]
            assert cursor == len(result["text"])
    write_json(
        out / "results.json",
        {
            "request": request,
            "decisions": all_records,
            "all_source_spans_exact": True,
            "note": "Evaluation labels were not read by this worker. Visual OCR and lexical/classifier gates only. Separator removal; no replacement prose.",
        },
    )


if __name__ == "__main__":
    main(read_json(Path(sys.argv[1])))
