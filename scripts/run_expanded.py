"""Bounded foreground comparison across the fixed two-book sample."""

import argparse
import subprocess
from pathlib import Path

from pdfocr.run import run_model
from pdfocr.util import read_json, write_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=["ocr", "repair"], default="ocr")
    parser.add_argument("--base", type=Path, default=Path("workspace/expanded"))
    parser.add_argument("--selection", type=Path, default=Path("datasets/expanded/selection.json"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if Path.cwd() != root:
        parser.error("Run from the project root")
    target = args.base / "index.json"
    index = read_json(target) if target.exists() else {"books": {}, "errors": []}
    for book in read_json(args.selection)["books"]:
        name = book["id"]
        doc = Path(book["document"])
        runs = index["books"].setdefault(name, {})
        for model in ["glm-ocr", "ovisocr3", "paddle-vl", "teleocr"]:
            print(args.phase, name, model, flush=True)
            try:
                existing = runs.get(model)
                if args.phase == "ocr":
                    if (
                        existing
                        and read_json(Path(existing) / "manifest.json")["status"] == "complete"
                    ):
                        continue
                    run = run_model(
                        doc, model, python=str(root / "runners/mlx/.venv/bin/python"), timeout=1200
                    )
                    runs[model] = str(run.resolve())
                    write_json(target, index)
                    if read_json(run / "manifest.json")["status"] != "complete":
                        raise RuntimeError(f"Incomplete {run}")
                else:
                    if not existing:
                        raise ValueError("Missing OCR run")
                    flow = doc / f"flow-{Path(existing).name}.proposed.md"
                    if not flow.exists():
                        subprocess.run(
                            [
                                str(root / ".venv/bin/pdfocr"),
                                "repair",
                                existing,
                                "--model",
                                "boundary-small",
                                "--out",
                                str(flow),
                                "--timeout",
                                "600",
                            ],
                            check=True,
                        )
            except Exception as exc:
                index["errors"].append(
                    {"phase": args.phase, "book": name, "model": model, "error": str(exc)}
                )
                write_json(target, index)
                print(str(exc), flush=True)
    write_json(target, index)


if __name__ == "__main__":
    main()
