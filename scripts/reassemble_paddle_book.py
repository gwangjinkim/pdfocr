"""Produce a declared book-assembly variant from saved real Paddle region OCR."""

import argparse
import copy
from pathlib import Path

from pdfocr.paddle_book import assemble_book
from pdfocr.stitch import stitch_run
from pdfocr.util import read_json, write_json

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--base", type=Path, default=Path("workspace/expanded"))
base = parser.parse_args().base
index = read_json(base / "index.json")
variants = {}
for book, runs in index["books"].items():
    source = Path(runs["paddle-vl"])
    run = source.parent / (source.name + "-book-v1")
    run.mkdir(exist_ok=True)
    m = copy.deepcopy(read_json(source / "manifest.json"))
    m["derived_from"] = str(source)
    m["config"]["model_name"] = "paddle-book"
    m["config"]["model"]["mode"] = "layout-crops-book-markdown"
    m["config"]["model"]["assembly_policy"] = "book-v1"
    m["postprocess_only"] = True
    for page in m["pages"]:
        value = read_json(source / page["result"])
        assembled = assemble_book(value["raw"]["blocks"])
        value["markdown"] = assembled["markdown"]
        value["book_assembly"] = assembled
        write_json(run / page["result"], value)
    write_json(run / "manifest.json", m)
    (run / "pages.md").write_text(
        "\n\n".join(
            f"<!-- source-page: {p['page']} -->\n\n" + read_json(run / p["result"])["markdown"]
            for p in m["pages"]
        )
    )
    stitch_run(run)
    variants[book] = str(run.resolve())
write_json(base / "paddle-book-index.json", variants)
