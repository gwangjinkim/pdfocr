"""Bounded follow-up: repair, book assembly and a matched Fraktur DPI probe."""

import os
import sys
import time
from pathlib import Path

import pdfocr.run as run_module
from pdfocr.pdf import prepare
from pdfocr.run import execute, run_model
from pdfocr.util import file_hash, read_json, write_json

ROOT = Path.cwd()
BASE = ROOT / "workspace/expanded400"
PYTHON = str(ROOT / ".venv/bin/python")
RUNNER = str(ROOT / "runners/mlx/.venv/bin/python")
MODELS = ["glm-ocr", "ovisocr3", "paddle-vl", "teleocr"]


def command(name, argv, timeout=1200):
    folder = BASE / "steps"
    folder.mkdir(exist_ok=True)
    process = execute(argv, folder / f"{name}.log", timeout, os.environ.copy())
    write_json(folder / f"{name}.process.json", process)
    if process.get("returncode") != 0:
        raise RuntimeError(f"{name} failed: inspect {folder}")
    print("Complete", name, flush=True)


def visual(base, selection):
    if (base / "visual/results.json").exists():
        return
    command(
        base.name + "-visual",
        [
            PYTHON,
            "scripts/run_visual_repair.py",
            "--base",
            str(base),
            "--selection",
            str(selection),
        ],
    )


def diagnose_glm(source):
    base = BASE / "glm-page29-diagnostic"
    base.mkdir(exist_ok=True)
    target = base / "index.json"
    index = read_json(target) if target.exists() else {}
    registry = run_module.registry
    for name, dpi, renderer, cap in [
        ("native-200", 200, "pdfrune", 2048),
        ("native-400-cap1157", 400, "pdfrune", 1157),
        ("pdfium-400", 400, "pdfium", 2048),
    ]:
        print("GLM page29 diagnostic", name, flush=True)
        folder = base / name
        if not (folder / "document.json").exists():
            prepare(source, folder, "29", dpi, renderer)
        existing = index.get(name)
        if existing and read_json(Path(existing) / "manifest.json")["status"] == "complete":
            continue
        # Only this explicitly declared diagnostic changes a resize cap.
        profiles = registry()
        profiles["glm-ocr"] = {**profiles["glm-ocr"], "longest_edge": cap}
        run_module.registry = lambda: profiles
        try:
            run = run_model(folder, "glm-ocr", python=RUNNER, timeout=300)
        finally:
            run_module.registry = registry
        assert read_json(run / "manifest.json")["status"] == "complete"
        index[name] = str(run.resolve())
        write_json(target, index)


def main():
    primary = read_json(BASE / "index.json")
    assert all(
        read_json(Path(p) / "manifest.json")["status"] == "complete"
        for models in primary["books"].values()
        for p in models.values()
    )
    selection = ROOT / "datasets/expanded400/selection.json"
    command(
        "primary-repair",
        [
            PYTHON,
            "scripts/run_expanded.py",
            "--base",
            str(BASE),
            "--selection",
            str(selection),
            "--phase",
            "repair",
        ],
    )
    command(
        "primary-book-assembly", [PYTHON, "scripts/reassemble_paddle_book.py", "--base", str(BASE)]
    )
    for bid, run in read_json(BASE / "paddle-book-index.json").items():
        flow = Path(run).parents[1] / f"flow-{Path(run).name}.proposed.md"
        if not flow.exists():
            command(
                "book-repair-" + bid,
                [
                    str(ROOT / ".venv/bin/pdfocr"),
                    "repair",
                    run,
                    "--model",
                    "boundary-small",
                    "--out",
                    str(flow),
                    "--timeout",
                    "600",
                ],
            )
    visual(BASE, selection)
    source = Path(
        "data/makrobiotikoderd00hufeuoft.pdf"
    )
    diagnose_glm(source)
    bid = "makrobiotikoderd00hufeuoft-probe"
    # Labels stay outside model requests and prompts.
    write_json(
        ROOT / "datasets/expanded400/probe-boundary.json",
        {
            "book": bid,
            "left_page": 34,
            "right_page": 35,
            "expected_action": "join_word",
            "expected_join": "Person",
            "visible": "Per- + son.",
        },
    )
    for dpi in [200, 400]:
        base = ROOT / f"workspace/expanded400-probe-{dpi}"
        base.mkdir(exist_ok=True)
        folder = base / "document"
        if not (folder / "document.json").exists():
            prepare(source, folder, "34-35", dpi, "pdfrune")
        selection = ROOT / f"datasets/expanded400/probe-{dpi}.json"
        write_json(
            selection,
            {
                "books": [{"id": bid, "document": str(folder), "pages": "34-35"}],
                "renderer": "pdfrune",
                "dpi": dpi,
                "note": "Same supplementary Fraktur pages at two DPIs with the fixed renderer. Excluded from primary CER; no full-page gold references.",
            },
        )
        target = base / "index.json"
        index = read_json(target) if target.exists() else {"books": {bid: {}}}
        for model in MODELS:
            print("Probe OCR", dpi, model, flush=True)
            existing = index["books"][bid].get(model)
            if existing and read_json(Path(existing) / "manifest.json")["status"] == "complete":
                run = Path(existing)
            else:
                run = run_model(folder, model, python=RUNNER, timeout=1200)
                index["books"][bid][model] = str(run.resolve())
                write_json(target, index)
            assert read_json(run / "manifest.json")["status"] == "complete"
            flow = folder / f"flow-{run.name}.proposed.md"
            if not flow.exists():
                command(
                    f"probe-{dpi}-{model}-repair",
                    [
                        str(ROOT / ".venv/bin/pdfocr"),
                        "repair",
                        str(run),
                        "--model",
                        "boundary-small",
                        "--out",
                        str(flow),
                        "--timeout",
                        "600",
                    ],
                )
        visual(base, selection)
    # Verify same source PDFs and unchanged frozen primary references.
    selected = read_json(ROOT / "datasets/expanded400/selection.json")
    for book in selected["books"]:
        assert file_hash(Path(book["source"])) == book["source_sha256"]
    for name, digest in selected["experiment"]["reference_hashes"].items():
        assert file_hash(ROOT / "datasets/expanded" / name) == digest


if __name__ == "__main__":
    start = time.time()
    process = {
        "pid": os.getpid(),
        "started_at_unix": start,
        "argv": [sys.executable, *sys.argv],
        "exited": False,
    }
    path = BASE / "followup-process.json"
    write_json(path, process)
    try:
        main()
    except BaseException:
        process.update(returncode=1)
        raise
    else:
        process.update(returncode=0)
    finally:
        process.update(exited=True, seconds=time.time() - start)
        write_json(path, process)
