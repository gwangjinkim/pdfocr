"""Run the unchanged local Qwen3 boundary repair on matched Gemma page OCR."""

import argparse
import os
from pathlib import Path

from pdfocr.gemma_format import unwrap_presentation
from pdfocr.repair import export_raw_pages
from pdfocr.run import execute
from pdfocr.util import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "workspace/gemma"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--models", nargs="+", default=["gemma3-12b", "gemma4-12b"])
    parser.add_argument("--base", type=Path, default=BASE)
    parser.add_argument(
        "--arm",
        choices=["matched200cap2880", "matched400cap2880", "budget1120", "tiles4"],
        default="matched400cap2880",
    )
    parser.add_argument("--normalize-format", action="store_true")
    args = parser.parse_args()
    source = args.source_root
    base = args.base.resolve()
    pin = read_json(source / "models/boundary-small.json")
    for model in args.models:
        for bid in ["10289757bsb", "makrobiotikoderd00hufeuoft", "probe"]:
            run = base / args.arm / model / bid
            pages = sorted(run.glob("page-*.json"))
            expected = 2 if bid == "probe" else 8
            if len(pages) != expected or any(read_json(p)["status"] != "ok" for p in pages):
                raise ValueError(f"Incomplete Gemma inference: {run}")
            if args.normalize_format:
                original_run = run
                run = base / "format-cleaned" / args.arm / model / bid
                run.mkdir(parents=True, exist_ok=True)
                for page in pages:
                    value = read_json(page)
                    original = value["markdown"]
                    cleanup = unwrap_presentation(original)
                    assert (
                        cleanup["markdown"]
                        == original[cleanup["source_start"] : cleanup["source_end"]]
                    )
                    write_json(
                        run / page.name,
                        {
                            **value,
                            "markdown": cleanup["markdown"],
                            "format_cleanup": {k: v for k, v in cleanup.items() if k != "markdown"},
                            "original_page_result": str(original_run / page.name),
                        },
                    )
                pages = sorted(run.glob("page-*.json"))
            write_json(
                run / "manifest.json",
                {
                    "status": "complete",
                    "config": {
                        "model_name": model,
                        "backend": "local-ollama",
                        "arm": args.arm,
                    },
                    "pages": [
                        {"page": read_json(p)["pages"][0], "result": p.name, "status": "ok"}
                        for p in pages
                    ],
                },
            )
            variant = "format-cleaned" if args.normalize_format else "raw"
            output = base / "repair" / args.arm / model / variant / (bid + ".md")
            if output.exists():
                print("Cached repair", model, bid, flush=True)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            raw = output.with_suffix(".raw.md")
            export_raw_pages(run, raw)
            request = {
                "task": "repair",
                "backend": "mlx",
                "model_name": "boundary-small",
                "model_path": pin["path"],
                "pin": pin,
                "output": str(output),
                "raw": str(raw),
                "report": str(output.with_suffix(".boundaries.jsonl")),
                "running_headers": [],
            }
            path = output.with_suffix(".request.json")
            write_json(path, request)
            process = execute(
                [
                    str(source / "runners/mlx/.venv/bin/python"),
                    "-m",
                    "pdfocr.decision_worker",
                    str(path),
                ],
                output.with_suffix(".worker.log"),
                600,
                {
                    **os.environ,
                    "PYTHONPATH": str(ROOT / "src"),
                    "HF_HUB_OFFLINE": "1",
                    "TOKENIZERS_PARALLELISM": "false",
                },
            )
            write_json(output.with_suffix(".process.json"), process)
            if process.get("returncode") != 0:
                raise RuntimeError(f"Repair failed: {output}")
            print("Repaired", model, bid, flush=True)


if __name__ == "__main__":
    main()
