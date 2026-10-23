"""Launch a bounded local visual repair worker and retain process evidence."""

import argparse
import os
from pathlib import Path

from pdfocr.run import execute
from pdfocr.util import read_json, write_json

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--base", type=Path, default=Path("workspace/expanded"))
parser.add_argument("--selection", type=Path, default=Path("datasets/expanded/selection.json"))
args = parser.parse_args()
out = (args.base / "visual").resolve()
out.mkdir(parents=True, exist_ok=True)
request = {
    "vision_pin": read_json(root / "models/glm-ocr.json"),
    "text_pin": read_json(root / "models/boundary-small.json"),
    "index": str((args.base / "index.json").resolve()),
    "selection": str(args.selection.resolve()),
    "out": str(out),
    "algorithm": "visual-hyphen-v1; Paddle layout geometry, GLM crop OCR, exact edge matches, Qwen3 join-word approval, source-mapped separator removal",
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
    900,
    env,
)
write_json(out / "process.json", process)
if process.get("returncode") != 0:
    raise RuntimeError("Visual worker failed; inspect " + str(out / "worker.log"))
print(out / "results.json")
