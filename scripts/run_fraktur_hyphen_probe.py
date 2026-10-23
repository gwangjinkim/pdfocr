"""Separate native-resolution positive hyphen probe, excluded from main CER."""

import os
import subprocess
from pathlib import Path

from pdfocr.pdf import prepare
from pdfocr.run import execute, run_model
from pdfocr.util import read_json, write_json

root = Path.cwd()
base = root / "workspace/fraktur-hyphen-probe"
base.mkdir(exist_ok=True)
doc = base / "document"
book = "makrobiotikoderd00hufeuoft-native-hyphen"
if not (doc / "document.json").exists():
    prepare(
        Path("data/makrobiotikoderd00hufeuoft.pdf"),
        doc,
        "34-35",
        400,
        "pdfrune",
    )
index = {"books": {book: {}}}
for model in ["ovisocr3", "paddle-vl"]:
    run = run_model(doc, model, python=str(root / "runners/mlx/.venv/bin/python"), timeout=600)
    index["books"][book][model] = str(run)
    flow = doc / f"flow-{run.name}.proposed.md"
    if read_json(run / "manifest.json")["status"] != "complete":
        raise ValueError("OCR incomplete")
    if not flow.exists():
        subprocess.run(
            [
                str(root / ".venv/bin/pdfocr"),
                "repair",
                str(run),
                "--out",
                str(flow),
                "--timeout",
                "300",
            ],
            check=True,
        )
write_json(base / "index.json", index)
write_json(base / "selection.json", {"books": [{"id": book, "document": str(doc)}]})
out = base / "visual"
out.mkdir(exist_ok=True)
request = {
    "vision_pin": read_json(root / "models/glm-ocr.json"),
    "text_pin": read_json(root / "models/boundary-small.json"),
    "index": str(base / "index.json"),
    "selection": str(base / "selection.json"),
    "out": str(out),
    "purpose": "Supplementary Fraktur positive hyphen probe, PDF34-35, visible Per- + son = Person; selected by scan, not OCR. 400 DPI strict pdfrune. Excluded from main frozen CER sample.",
}
write_json(out / "request.json", request)
env = {
    **os.environ,
    "PYTHONPATH": str(root / "src"),
    "HF_HUB_OFFLINE": "1",
    "TOKENIZERS_PARALLELISM": "false",
}
process = execute(
    [
        str(root / "runners/mlx/.venv/bin/python"),
        str(root / "scripts/visual_worker.py"),
        str(out / "request.json"),
    ],
    out / "worker.log",
    300,
    env,
)
write_json(out / "process.json", process)
if process.get("returncode") != 0:
    raise RuntimeError("Visual probe failed")
