"""Freeze and render the authorized 400-DPI experiment; no inference or fallback."""

import importlib.metadata
import os
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

from pdfocr.pdf import prepare
from pdfocr.util import file_hash, read_json, write_json


def main():
    root = Path.cwd()
    base = root / "workspace/expanded400"
    base.mkdir(parents=True, exist_ok=True)
    selection_path = root / "datasets/expanded400/selection.json"
    previous = read_json(root / "datasets/expanded/selection.json")
    if not selection_path.exists():
        selection = {
            **previous,
            "experiment": {
                "dpi": 400,
                "renderer": "pdfrune",
                "fallback_allowed": False,
                "render_pixel_budget": 100_000_000,
                "prior_selection": str(root / "datasets/expanded/selection.json"),
                "prior_report": str(root / "workspace/expanded/report/comparison.json"),
                "reference_hashes": read_json(root / "datasets/expanded/reference-hashes.json"),
                "model_profiles": read_json(root / "src/pdfocr/models.json"),
                "renderer_fix_commit": "e174cbc6f80c1707ba048e46b9810cc85a8995d9",
                "note": "Both renderer and DPI change versus frozen PDFium 200-DPI inputs. Model versions, prompts and profile resize caps remain fixed. No causal isolation of DPI alone.",
            },
        }
        selection["render_qa"] = "Pending native 400-DPI render review before OCR."
        selection["books"] = []
        for book in previous["books"]:
            old_doc = read_json(root / book["document"] / "document.json")
            selection["books"].append(
                {
                    **book,
                    "document": str(base / book["id"]),
                    "source": old_doc["source"],
                    "source_sha256": old_doc["source_sha256"],
                }
            )
        write_json(selection_path, selection)
    selection = read_json(selection_path)
    for book in selection["books"]:
        source, folder = Path(book["source"]), Path(book["document"])
        assert file_hash(source) == book["source_sha256"]
        if not (folder / "document.json").exists():
            print("Rendering", book["id"], book["pages"], "native 400 DPI", flush=True)
            prepare(source, folder, book["pages"], 400, "pdfrune", max_pixels=100_000_000)
        doc = read_json(folder / "document.json")
        assert (
            doc["selected_pages"]
            == read_json(
                root
                / next(b["document"] for b in previous["books"] if b["id"] == book["id"])
                / "document.json"
            )["selected_pages"]
        )
        sheet = Image.new("RGB", (4 * 360, 2 * 650), "#dddddd")
        draw = ImageDraw.Draw(sheet)
        for i, page in enumerate(doc["pages"]):
            assert page["renderer"] == "pdfrune" and page["dpi"] == 400
            assert page["renderer_fallback_reason"] is None
            assert file_hash(folder / page["image"]) == page["image_sha256"]
            with Image.open(folder / page["image"]) as im:
                im.thumbnail((350, 610))
                sheet.paste(im.convert("RGB"), (i % 4 * 360 + 5, i // 4 * 650 + 30))
            draw.text(
                (i % 4 * 360 + 5, i // 4 * 650 + 7),
                f"PDF {page['page']}: {page['width']} x {page['height']}",
                fill="black",
            )
        sheet.save(base / f"{book['id']}-contact.jpg", quality=90)
        print("Rendered", book["id"], "all", len(doc["pages"]), "pages, no fallback", flush=True)
    metadata = importlib.metadata.distribution("pdfrune")
    native = [Path(metadata.locate_file(f)) for f in metadata.files if str(f).endswith(".so")]
    write_json(
        base / "renderer-provenance.json",
        {
            "version": metadata.version,
            "native_extensions": {str(p): file_hash(p) for p in native},
            "source_files": {
                str(p): file_hash(p)
                for p in (root / "vendor-pdfrune/crates/pdfrune/src").rglob("*.rs")
            },
            "repair": read_json(root / "docs/pdfrune-repair.json"),
        },
    )


if __name__ == "__main__":
    start = time.time()
    path = Path("workspace/expanded400/prepare-process.json")
    details = {
        "pid": os.getpid(),
        "started_at_unix": start,
        "argv": [sys.executable, *sys.argv],
        "exited": False,
    }
    write_json(path, details)
    try:
        main()
    except BaseException:
        details.update(returncode=1)
        raise
    else:
        details.update(returncode=0)
    finally:
        details.update(exited=True, seconds=time.time() - start)
        write_json(path, details)
