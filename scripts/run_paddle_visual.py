"""Swap only the local visual reader on frozen Fraktur boundary crops."""

import os
import sys
import time
from pathlib import Path

from pdfocr.run import execute
from pdfocr.util import file_hash, read_json, write_json

ROOT = Path.cwd()
BASE = ROOT / "workspace/paddle-visual-fraktur"
SOURCES = [
    (
        "controls-200",
        "workspace/expanded",
        "datasets/expanded/selection.json",
        "makrobiotikoderd00hufeuoft",
    ),
    (
        "controls-400",
        "workspace/expanded400",
        "datasets/expanded400/selection.json",
        "makrobiotikoderd00hufeuoft",
    ),
    (
        "probe-200",
        "workspace/expanded400-probe-200",
        "datasets/expanded400/probe-200.json",
        "makrobiotikoderd00hufeuoft-probe",
    ),
    (
        "probe-400",
        "workspace/expanded400-probe-400",
        "datasets/expanded400/probe-400.json",
        "makrobiotikoderd00hufeuoft-probe",
    ),
]


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    jobs = []
    for name, source, selection, book in SOURCES:
        out = BASE / name
        out.mkdir(exist_ok=True)
        request = {
            "vision_pin": read_json(ROOT / "models/paddle-vl.json"),
            "vision_backend": "paddle",
            "vision_prompt": "OCR:",
            "text_pin": read_json(ROOT / "models/boundary-small.json"),
            "index": str(ROOT / source / "index.json"),
            "selection": str(ROOT / selection),
            "book_ids": [book],
            "frozen_crop_base": str(ROOT / source / "visual"),
            "out": str(out),
            "algorithm": "visual-hyphen-v1; only visual reader/prompt changed from GLM to PaddleOCR-VL-1.6 BF16, OCR:. Exact frozen crops, same lexical gate, Qwen3 approval and source-mapped separator removal.",
            "implementation_sha256": {
                str(path.relative_to(ROOT)): file_hash(path)
                for path in [
                    ROOT / "scripts/visual_worker.py",
                    ROOT / "src/pdfocr/local_pipelines.py",
                    ROOT / "src/pdfocr/visual_repair.py",
                    ROOT / "src/pdfocr/borrowed/archive_stitching.py",
                ]
            },
        }
        request_path = out / "request.json"
        if request_path.exists() and read_json(request_path) != request:
            raise ValueError("Existing experiment has different inputs; use a new output folder")
        write_json(request_path, request)
        jobs.append(
            {
                "name": name,
                "book": book,
                "out": str(out),
                "glm_out": str(ROOT / source / "visual"),
                "request": str(request_path),
            }
        )
    write_json(BASE / "jobs.json", jobs)
    for job in jobs:
        out = Path(job["out"])
        if (out / "results.json").exists():
            continue
        print("Paddle boundary reader", job["name"], flush=True)
        env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "src"),
            "HF_HUB_OFFLINE": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
        process = execute(
            [
                str(ROOT / "runners/mlx/.venv/bin/python"),
                str(ROOT / "scripts/visual_worker.py"),
                job["request"],
            ],
            out / "worker.log",
            600,
            env,
        )
        write_json(out / "process.json", process)
        if process.get("returncode") != 0:
            raise RuntimeError(f"Paddle visual worker failed: {out}")
        print("Complete", job["name"], flush=True)


if __name__ == "__main__":
    BASE.mkdir(parents=True, exist_ok=True)
    started = time.time()
    process = {
        "pid": os.getpid(),
        "started_at_unix": started,
        "argv": [sys.executable, *sys.argv],
        "exited": False,
    }
    write_json(BASE / "controller-process.json", process)
    try:
        main()
    except BaseException:
        process["returncode"] = 1
        raise
    else:
        process["returncode"] = 0
    finally:
        process.update(exited=True, seconds=time.time() - started)
        write_json(BASE / "controller-process.json", process)
