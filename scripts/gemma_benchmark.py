"""Compare the original multi-image Gemma workflow and matched 400-DPI OCR.

Connects only to an existing loopback Ollama. Never starts/stops its service.
Requests unload their model on completion. No reference text enters a request.
Run with the isolated runners/legacy interpreter; outputs are resumable.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "workspace/gemma"
PROMPT = "Extract all readable text from these images and format it as structured Markdown."
BOOKS = {
    "10289757bsb": [9, 10, 11, 12, 13, 14, 70, 71],
    "makrobiotikoderd00hufeuoft": [25, 26, 27, 28, 29, 30, 200, 201],
}


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(source_root):
    import fitz
    from PIL import Image

    provenance = {"pymupdf": fitz.VersionBind, "pages": [], "source_documents": {}}
    for bid, numbers in BOOKS.items():
        original = read(source_root / "workspace/expanded400" / bid / "document.json")
        pdf = Path(original["source"])
        if not pdf.exists():
            pdf = source_root / "data" / (bid + ".pdf")
        assert digest(pdf) == original["source_sha256"]
        provenance["source_documents"][bid] = original["source_sha256"]
        with fitz.open(pdf) as document:
            for number in sorted(set(numbers + ([34, 35] if bid.startswith("makro") else []))):
                # Exactly the original renderer call, RGB construction and PNG encoding.
                pix = document[number - 1].get_pixmap()
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                target = BASE / "inputs72" / bid / f"page-{number:04d}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(buffer.getvalue())
                provenance["pages"].append(
                    {
                        "book": bid,
                        "page": number,
                        "width": pix.width,
                        "height": pix.height,
                        "dpi": 72,
                        "image": str(target.relative_to(ROOT)),
                        "sha256": digest(target),
                    }
                )
        for record in original["pages"]:
            image = source_root / "workspace/expanded400" / bid / record["image"]
            assert digest(image) == record["image_sha256"]
            provenance["pages"].append(
                {
                    "book": bid,
                    "page": record["page"],
                    "width": record["width"],
                    "height": record["height"],
                    "dpi": 400,
                    "image": str(image),
                    "sha256": digest(image),
                }
            )
    probe = read(source_root / "workspace/expanded400-probe-400/document/document.json")
    bid = "makrobiotikoderd00hufeuoft"
    for record in probe["pages"]:
        image = source_root / "workspace/expanded400-probe-400/document" / record["image"]
        assert digest(image) == record["image_sha256"]
        provenance["pages"].append(
            {
                "book": bid,
                "page": record["page"],
                "width": record["width"],
                "height": record["height"],
                "dpi": 400,
                "image": str(image),
                "sha256": digest(image),
            }
        )
    save(BASE / "inputs.json", provenance)
    print("Prepared original PyMuPDF 72-DPI inputs and verified fixed 400-DPI hashes", flush=True)


def metadata(client, models):
    tags = client.get("/api/tags").raise_for_status().json()["models"]
    records = {}
    for model in models:
        record = next(x for x in tags if x["name"] == model)
        show = client.post("/api/show", json={"model": model}).raise_for_status().json()
        assert "vision" in show.get("capabilities", [])
        records[model] = {"tag": record, "show": show}
    return {"ollama": client.get("/api/version").raise_for_status().json(), "models": records}


def infer(client, model, images, path, arm, pages, bid):
    if path.exists() and read(path).get("status") == "ok":
        print("Cached", path.relative_to(ROOT), flush=True)
        return
    import base64

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": PROMPT,
                "images": [base64.b64encode(p.read_bytes()).decode() for p in images],
            }
        ],
        "stream": False,
        "keep_alive": 0,
    }
    if arm.startswith(("matched200", "matched400")):
        payload["options"] = {"temperature": 0, "seed": 0, "num_ctx": 16384, "num_predict": 8192}
        if model.startswith("gemma4"):
            payload["think"] = False
    request = {k: v for k, v in payload.items() if k != "messages"}
    request["messages"] = [
        {"role": "user", "content": PROMPT, "images": [{"sha256": digest(p)} for p in images]}
    ]
    result = {
        "model": model,
        "book": bid,
        "pages": pages,
        "arm": arm,
        "request_without_image_bytes": request,
    }
    start = time.time()
    print("START", model, arm, bid, pages, flush=True)
    try:
        response = client.post("/api/chat", json=payload, timeout=1200)
        response.raise_for_status()
        value = response.json()
        if value.get("error"):
            raise RuntimeError(value["error"])
        result.update(
            status="ok",
            response=value,
            markdown=value["message"]["content"],
            possibly_truncated=value.get("done_reason") == "length",
        )
    except Exception as exc:
        result.update(status="error", error=str(exc))
    result["seconds"] = time.time() - start
    save(path, result)
    print("END", result["status"], round(result["seconds"], 1), "s", flush=True)


def run(client, models, arms):
    inputs = read(BASE / "inputs.json")["pages"]
    meta_path = BASE / "model-provenance.json"
    meta = metadata(client, models)
    if meta_path.exists():
        old = read(meta_path)
        for model in models:
            if model in old["models"]:
                assert (
                    old["models"][model]["tag"]["digest"] == meta["models"][model]["tag"]["digest"]
                ), ("Mutable model tag changed; use a new experiment directory", model)
        meta["models"] = {**old["models"], **meta["models"]}
    save(meta_path, meta)
    for model in models:
        for arm in arms:
            for bid, numbers in BOOKS.items():
                # Each batch is a contiguous selected excerpt, preserving original code
                # semantics without inventing adjacency across PDF 14->70 or 30->200.
                groups = [numbers[:6], numbers[6:]] if arm == "legacy72" else [[n] for n in numbers]
                for pages in groups:
                    dpi = 72 if arm == "legacy72" else 400
                    images = [
                        Path(
                            next(
                                p["image"]
                                for p in inputs
                                if p["book"] == bid and p["page"] == n and p["dpi"] == dpi
                            )
                        )
                        for n in pages
                    ]
                    images = [p if p.is_absolute() else ROOT / p for p in images]
                    if arm == "matched400cap2880":
                        images = [capped_image(p, bid, n) for p, n in zip(images, pages)]
                    stem = "page-" + "-".join(f"{n:04d}" for n in pages)
                    infer(
                        client,
                        model,
                        images,
                        BASE / arm / model.replace(":", "-") / bid / (stem + ".json"),
                        arm,
                        pages,
                        bid,
                    )
            bid = "makrobiotikoderd00hufeuoft"
            for pages in [[34, 35]] if arm == "legacy72" else [[34], [35]]:
                dpi = 72 if arm == "legacy72" else 400
                images = [
                    Path(
                        next(
                            p["image"]
                            for p in inputs
                            if p["book"] == bid and p["page"] == n and p["dpi"] == dpi
                        )
                    )
                    for n in pages
                ]
                images = [p if p.is_absolute() else ROOT / p for p in images]
                if arm == "matched400cap2880":
                    images = [capped_image(p, bid, n) for p, n in zip(images, pages)]
                infer(
                    client,
                    model,
                    images,
                    BASE
                    / arm
                    / model.replace(":", "-")
                    / "probe"
                    / ("page-" + "-".join(f"{n:04d}" for n in pages) + ".json"),
                    arm,
                    pages,
                    bid,
                )


def capped_image(source, bid, number, *, base=None, cache_name="inputs400cap2880"):
    from PIL import Image

    target = (base or BASE) / cache_name / bid / source.name
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            image = image.convert("RGB")
            image.thumbnail((2880, 2880), Image.Resampling.LANCZOS)
            image.save(target)
            save(
                target.with_suffix(".json"),
                {
                    "book": bid,
                    "page": number,
                    "source_sha256": digest(source),
                    "input_sha256": digest(target),
                    "input_size": list(image.size),
                    "longest_edge": 2880,
                    "method": "Pillow RGB; thumbnail LANCZOS, no upscaling; PNG",
                },
            )
    assert read(target.with_suffix(".json"))["source_sha256"] == digest(source)
    assert read(target.with_suffix(".json"))["input_sha256"] == digest(target)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "pull", "run"])
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=["gemma3:12b", "gemma4:12b"],
        default=["gemma3:12b", "gemma4:12b"],
    )
    parser.add_argument(
        "--arms",
        nargs="+",
        choices=["matched400", "matched400cap2880", "legacy72"],
        default=["matched400cap2880", "legacy72"],
    )
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.source_root)
        return
    with httpx.Client(base_url="http://127.0.0.1:11434", trust_env=False, timeout=30) as client:
        if args.phase == "pull":
            for model in args.models:
                print("Explicit local model download", model, flush=True)
                start = time.time()
                last = 0
                with client.stream("POST", "/api/pull", json={"model": model}, timeout=1200) as r:
                    r.raise_for_status()
                    for line in r.iter_lines():
                        value = json.loads(line)
                        if value.get("error"):
                            raise RuntimeError(value["error"])
                        if time.time() - last > 15 or value.get("status") == "success":
                            print(value, flush=True)
                            last = time.time()
                print("Download finished", round(time.time() - start, 1), "s", flush=True)
        else:
            run(client, args.models, args.arms)


if __name__ == "__main__":
    start = time.time()
    process = {"pid": os.getpid(), "started_at_unix": start, "argv": sys.argv, "exited": False}
    path = BASE / ("process-" + str(os.getpid()) + ".json")
    save(path, process)
    try:
        main()
    except BaseException:
        process["returncode"] = 1
        raise
    else:
        process["returncode"] = 0
    finally:
        process.update(exited=True, seconds=time.time() - start)
        save(path, process)
