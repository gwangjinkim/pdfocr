from __future__ import annotations

import json
import os
from pathlib import Path

from .repair import DecisionBackend, export_raw_pages
from .run import execute
from .util import read_json, write_json


def process(args) -> None:
    args.out = args.out.resolve()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pin = None
    if args.backend == "mlx":
        if args.model not in ("boundary-tiny", "boundary-small"):
            raise ValueError("Use a text-classifier profile: boundary-tiny or boundary-small")
        pin_path = Path("models") / f"{args.model}.json"
        if not pin_path.exists():
            raise ValueError(f"First run pdfocr fetch {args.model} --python {args.python}")
        pin = read_json(pin_path)
    else:
        # Validate before any output is written; this connects only during inference.
        DecisionBackend(args.model, args.endpoint)
    if args.out.exists():
        raise ValueError("Use a new output path so an earlier reviewed result stays intact")
    request = {
        "task": "repair" if args.command == "repair" else "evaluate",
        "backend": args.backend,
        "model_name": args.model,
        "model_path": pin["path"] if pin else None,
        "pin": pin,
        "endpoint": args.endpoint,
        "output": str(args.out),
        "running_headers": args.running_header,
        "split": args.split,
    }
    if args.command == "repair":
        raw = args.out.with_suffix(".raw.md")
        export_raw_pages(args.input.resolve(), raw)
        request.update(raw=str(raw), report=str(args.out.with_suffix(".boundaries.jsonl")))
    else:
        request["dataset"] = str(args.input.resolve(strict=True))
    request_path = args.out.with_suffix(".request.json")
    write_json(request_path, request)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
    env["HF_HUB_OFFLINE"] = "1"
    env["TOKENIZERS_PARALLELISM"] = "false"
    info = execute(
        [args.python, "-m", "pdfocr.decision_worker", str(request_path)],
        args.out.with_suffix(".worker.log"),
        args.timeout,
        env,
    )
    write_json(args.out.with_suffix(".process.json"), info)
    if info.get("returncode") != 0:
        raise ValueError(f"Boundary worker failed; inspect {args.out.with_suffix('.worker.log')}")
    print(args.out)
    if args.command == "boundary-eval":
        data = read_json(args.out)
        print(json.dumps({k: v for k, v in data.items() if k != "results"}, indent=2))
