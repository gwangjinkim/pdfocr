"""Run the four local pipelines, repair identical boundaries, and write a report."""

import argparse
import subprocess
from pathlib import Path

from pdfocr.book_compare import review
from pdfocr.run import run_model


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--document", type=Path, default=Path("workspace/demo"))
    parser.add_argument("--references", type=Path, default=Path("datasets/book-review/references"))
    parser.add_argument("--out", type=Path, default=Path("workspace/book-comparison"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if Path.cwd() != root:
        parser.error("Run this script from the pdfocr project directory")
    runs = []
    repairs = {}
    for name in ["glm-ocr", "ovisocr3", "paddle-vl", "teleocr"]:
        run = run_model(
            args.document, name, python=str(root / "runners/mlx/.venv/bin/python"), timeout=900
        )
        import json

        if json.loads((run / "manifest.json").read_text())["status"] != "complete":
            raise RuntimeError(f"Incomplete model run: {run}; inspect worker.log")
        flow = args.document / f"flow-{run.name}.proposed.md"
        if not flow.exists():
            subprocess.run(
                [
                    str(root / ".venv/bin/pdfocr"),
                    "repair",
                    str(run),
                    "--model",
                    "boundary-small",
                    "--out",
                    str(flow),
                    "--timeout",
                    "300",
                ],
                check=True,
            )
        runs.append(run)
        repairs[name] = flow
    review(args.document, runs, args.references, repairs, args.out)
    print(args.out / "comparison.html")


if __name__ == "__main__":
    main()
