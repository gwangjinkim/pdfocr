"""Run selected model workers sequentially. No background services."""

import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("document")
    parser.add_argument("--models", nargs="+", default=["glm-ocr"])
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    python = root / ".venv/bin/python"
    runner = root / "runners/mlx/.venv/bin/python"
    failures = []
    for model in args.models:
        if args.download:
            subprocess.run(
                [str(python), "-m", "pdfocr.cli", "fetch", model, "--python", str(runner)],
                cwd=root,
                check=True,
            )
        result = subprocess.run(
            [
                str(python),
                "-m",
                "pdfocr.cli",
                "run",
                args.document,
                "--model",
                model,
                "--python",
                str(runner),
            ],
            cwd=root,
            check=False,
        )
        if result.returncode:
            failures.append(model)
    subprocess.run(
        [str(python), "-m", "pdfocr.cli", "compare", args.document], cwd=root, check=True
    )
    if failures:
        print("Incomplete models: " + ", ".join(failures), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
