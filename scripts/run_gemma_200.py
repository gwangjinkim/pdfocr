"""Native200-DPI matched Gemma follow-up; no model downloads or service startup."""

import argparse
import hashlib
import io
import os
import sys
import time
from pathlib import Path

import gemma_benchmark as bench
import httpx
import pdfrune
from PIL import Image, ImageDraw

BASE = bench.ROOT / "workspace/gemma200"


def prepare(source_root):
    original = bench.read(bench.BASE / "inputs.json")
    provenance = {
        "dpi": 200,
        "renderer": "pdfrune",
        "renderer_fix_commit": "e174cbc6f80c1707ba048e46b9810cc85a8995d9",
        "fallback_allowed": False,
        "source_documents": original["source_documents"],
        "pages": [],
        "400dpi_render_controls": [],
        "note": "All18 current400-DPI renders must reproduce the frozen400 source pixels before isolating DPI.",
    }
    for bid, primary in bench.BOOKS.items():
        old_doc = bench.read(source_root / "workspace/expanded400" / bid / "document.json")
        pdf = Path(old_doc["source"])
        if not pdf.exists():
            pdf = source_root / "data" / (bid + ".pdf")
        assert bench.digest(pdf) == original["source_documents"][bid]
        numbers = primary + ([34, 35] if bid.startswith("makro") else [])
        with pdfrune.open(str(pdf)) as doc:
            for number in numbers:
                old = next(
                    p
                    for p in original["pages"]
                    if p["book"] == bid and p["page"] == number and p["dpi"] == 400
                )
                reference = Path(old["image"])
                reference = reference if reference.is_absolute() else bench.ROOT / reference
                assert bench.digest(reference) == old["sha256"]
                png400 = doc[number - 1].render(dpi=400).tobytes("png")
                exact = hashlib.sha256(png400).hexdigest() == old["sha256"]
                if not exact:
                    with Image.open(io.BytesIO(png400)) as a, Image.open(reference) as b:
                        exact = (
                            a.size == b.size
                            and a.convert("RGB").tobytes() == b.convert("RGB").tobytes()
                        )
                assert exact, (bid, number, "Renderer changed; cannot isolate DPI")
                provenance["400dpi_render_controls"].append(
                    {
                        "book": bid,
                        "page": number,
                        "pixel_identical": True,
                        "frozen_png_sha256": old["sha256"],
                    }
                )
                target = BASE / "inputs200" / bid / f"page-{number:04d}.png"
                target.parent.mkdir(parents=True, exist_ok=True)
                doc[number - 1].render(dpi=200).save(str(target))
                with Image.open(target) as image:
                    width, height = image.size
                provenance["pages"].append(
                    {
                        "book": bid,
                        "page": number,
                        "dpi": 200,
                        "image": str(target.relative_to(bench.ROOT)),
                        "width": width,
                        "height": height,
                        "sha256": bench.digest(target),
                        "renderer": "pdfrune",
                    }
                )
                bench.capped_image(target, bid, number, base=BASE, cache_name="inputs200cap2880")
                print("Prepared native200 and matched400 render", bid, number, flush=True)
        sheet = Image.new("RGB", (1200, ((len(numbers) + 3) // 4) * 490), "#eeeeee")
        draw = ImageDraw.Draw(sheet)
        for i, n in enumerate(numbers):
            with Image.open(BASE / "inputs200" / bid / f"page-{n:04d}.png") as im:
                im.thumbnail((290, 450))
                sheet.paste(im.convert("RGB"), (i % 4 * 300 + 5, i // 4 * 490 + 25))
            draw.text((i % 4 * 300 + 5, i // 4 * 490 + 5), f"PDF{n}, 200DPI", fill="black")
        sheet.save(BASE / (bid + "-contact.jpg"), quality=88)
    bench.save(BASE / "inputs.json", provenance)


def run(models):
    inputs = bench.read(BASE / "inputs.json")["pages"]
    with httpx.Client(base_url="http://127.0.0.1:11434", trust_env=False, timeout=30) as client:
        meta = bench.metadata(client, models)
        old = bench.read(bench.BASE / "model-provenance.json")
        assert meta["ollama"] == old["ollama"], "Runtime changed"
        for model in models:
            assert (
                meta["models"][model]["tag"]["digest"] == old["models"][model]["tag"]["digest"]
            ), "Weights changed"
        target = BASE / "model-provenance.json"
        if target.exists():
            meta["models"] = {**bench.read(target)["models"], **meta["models"]}
        bench.save(target, meta)
        for model in models:
            for page in inputs:
                bid, n = page["book"], page["page"]
                source = bench.ROOT / page["image"]
                assert bench.digest(source) == page["sha256"]
                image = bench.capped_image(source, bid, n, base=BASE, cache_name="inputs200cap2880")
                group = "probe" if n in [34, 35] else bid
                result = (
                    BASE
                    / "matched200cap2880"
                    / model.replace(":", "-")
                    / group
                    / f"page-{n:04d}.json"
                )
                bench.infer(client, model, [image], result, "matched200cap2880", [n], bid)
                assert bench.read(result)["status"] == "ok", result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "run"])
    parser.add_argument("--source-root", type=Path, default=bench.ROOT)
    parser.add_argument(
        "--models",
        nargs="+",
        choices=["gemma3:12b", "gemma4:12b"],
        default=["gemma3:12b", "gemma4:12b"],
    )
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare(args.source_root)
    else:
        run(args.models)


if __name__ == "__main__":
    started = time.time()
    path = BASE / f"process-{os.getpid()}.json"
    process = {"pid": os.getpid(), "started_at_unix": started, "argv": sys.argv, "exited": False}
    bench.save(path, process)
    try:
        main()
    except BaseException:
        process["returncode"] = 1
        raise
    else:
        process["returncode"] = 0
    finally:
        process.update(exited=True, seconds=time.time() - started)
        bench.save(path, process)
