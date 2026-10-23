from __future__ import annotations

import argparse
import importlib.metadata
import json
import platform
import subprocess
import sys
from pathlib import Path

from .util import read_json, registry, write_json


def fetch(args) -> None:
    spec = registry()[args.model]
    if args.model == "native":
        raise ValueError("Native pdfrune needs no model download")
    out = Path("models")
    out.mkdir(exist_ok=True)
    pin = out / f"{args.model}.json"
    if pin.exists() and not args.update:
        print(json.dumps(read_json(pin), indent=2))
        return
    # Use the isolated interpreter, whose huggingface_hub version is locked.
    code = """import json, os, sys
from pathlib import Path
from huggingface_hub import HfApi, snapshot_download
repo, revision, output = sys.argv[1:]
info = HfApi().model_info(repo, revision=revision or None)
path = snapshot_download(repo, revision=info.sha)
target = Path(output)
tmp = target.with_suffix(".tmp")
tmp.write_text(json.dumps({"repo":repo,"revision":info.sha,"path":path}, indent=2))
os.replace(tmp, target)
print(path)
"""
    import os

    from .run import execute

    process = execute(
        [args.python, "-c", code, spec["repo"], args.revision or "", str(pin.resolve())],
        out / f"{args.model}.fetch.log",
        args.timeout,
        os.environ.copy(),
    )
    if process.get("returncode") != 0:
        raise ValueError(f"Download failed or timed out; see {out / (args.model + '.fetch.log')}")
    print(json.dumps(read_json(pin), indent=2))


def doctor() -> None:
    info = {
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "python": sys.version,
        "executable": sys.executable,
        "packages": {},
    }
    for name in ("pdfrune", "pdfocr-lab", "pillow", "mlx-vlm", "httpx"):
        try:
            info["packages"][name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            info["packages"][name] = "not installed in this interpreter"
    for name in ("hw.memsize", "machdep.cpu.brand_string"):
        result = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True)
        info[name] = result.stdout.strip() if result.returncode == 0 else "unavailable"
    runner = Path(__file__).resolve().parents[2] / "runners/mlx/.venv/bin/python"
    if runner.exists():
        check = subprocess.run(
            [
                str(runner),
                "-c",
                "import json,importlib.metadata as m; print(json.dumps({p:m.version(p) for p in ['mlx','mlx-vlm','transformers']}))",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        info["mlx_runner"] = {
            "executable": str(runner),
            "healthy": check.returncode == 0,
            "packages": json.loads(check.stdout) if check.returncode == 0 else check.stderr,
        }
    info["automatic_background_services"] = False
    print(json.dumps(info, indent=2))


def licenses() -> dict:
    rows = []
    for dist in importlib.metadata.distributions():
        meta = dist.metadata
        values = [meta.get("License-Expression", ""), meta.get("License", "")]
        values.extend(c for c in meta.get_all("Classifier", []) if "License" in c)
        text = " | ".join(v for v in values if v)
        rows.append(
            {
                "name": meta.get("Name"),
                "version": dist.version,
                "license_metadata": text[:2000],
                "review": "review"
                if not text
                or any(
                    s in text.lower() for s in ("agpl", "gpl", "non-commercial", "noncommercial")
                )
                else "metadata_present",
            }
        )
    return {
        "packages": sorted(rows, key=lambda r: r["name"].lower()),
        "caveat": "Metadata inventory only. Not an audit of license texts, bundled binaries, models, datasets, or usage terms.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="pdfrune-based PDF OCR comparison lab")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("models", help="Show model specifications, modes and license notes")
    sub.add_parser("doctor")
    license_parser = sub.add_parser("licenses", help="Inventory installed distribution licenses")
    license_parser.add_argument("--out", type=Path)
    p = sub.add_parser("prepare", help="Render and extract native text with pdfrune")
    p.add_argument("pdf", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--pages", help="1-based: 1-3,7")
    p.add_argument("--dpi", type=float, default=200)
    p.add_argument("--renderer", choices=["auto", "pdfrune", "pdfium"], default="auto")
    p = sub.add_parser("fetch", help="Explicitly download and pin model weights")
    p.add_argument("model", choices=[m for m in registry() if m != "native"])
    p.add_argument("--python", required=True)
    p.add_argument("--revision")
    p.add_argument("--update", action="store_true")
    p.add_argument("--timeout", type=float, default=1800)
    p = sub.add_parser("run", help="Run a model in a bounded foreground subprocess")
    p.add_argument("document", type=Path)
    p.add_argument("--model", choices=list(registry()), required=True)
    p.add_argument("--backend", choices=["native", "mlx", "endpoint", "command", "teleocr"])
    p.add_argument("--python")
    p.add_argument("--endpoint")
    p.add_argument("--endpoint-model")
    p.add_argument("--allow-remote", action="store_true")
    p.add_argument(
        "--command-json", help="JSON argv; substitutes {request} and {run}, never invokes a shell"
    )
    p.add_argument("--prompt-file", type=Path)
    p.add_argument("--max-tokens", type=int)
    p.add_argument("--timeout", type=float, default=900)
    p = sub.add_parser("stitch", help="Build reading copy and review page-boundary decisions")
    p.add_argument("run", type=Path)
    p.add_argument("--overrides", type=Path)
    p = sub.add_parser("compare", help="Create static side-by-side review HTML; starts no server")
    p.add_argument("document", type=Path)
    p = sub.add_parser("evaluate", help="Compare raw page outputs to reference transcriptions")
    p.add_argument("run", type=Path)
    p.add_argument("--references", type=Path, required=True)
    for name in ("repair", "boundary-eval"):
        p = sub.add_parser(name, help="archiveorgocr strategy: local decisions, guarded edits")
        p.add_argument(
            "input", type=Path, help="Run directory for repair, JSONL dataset for boundary-eval"
        )
        p.add_argument("--out", type=Path, required=True)
        p.add_argument("--backend", choices=["mlx", "ollama"], default="mlx")
        p.add_argument("--model", default="boundary-small")
        p.add_argument("--python", default="runners/mlx/.venv/bin/python")
        p.add_argument("--endpoint", default="http://127.0.0.1:11434")
        p.add_argument("--running-header", action="append", default=[])
        p.add_argument("--split", choices=["train", "validation", "valid", "test"], default="test")
        p.add_argument("--timeout", type=float, default=900)
    p = sub.add_parser("archive-list", help="List PDF files from Internet Archive metadata")
    p.add_argument("item")
    p = sub.add_parser("archive-fetch", help="Download an explicitly selected public PDF")
    p.add_argument("item")
    p.add_argument("--file", required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--max-mb", type=int, default=500)
    p = sub.add_parser(
        "import-raw", help="Import archiveorgocr's ## Page N OCR without rerunning it"
    )
    p.add_argument("document", type=Path)
    p.add_argument("raw", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "models":
            print(json.dumps(registry(), ensure_ascii=False, indent=2))
        elif args.command == "doctor":
            doctor()
        elif args.command == "licenses":
            data = licenses()
            if args.out:
                write_json(args.out, data)
                print(args.out)
            else:
                print(json.dumps(data, indent=2))
        elif args.command == "prepare":
            from .pdf import prepare

            manifest = prepare(args.pdf, args.out, args.pages, args.dpi, args.renderer)
            print(f"Prepared {len(manifest['pages'])} pages in {args.out}")
            for page in manifest["pages"]:
                if page.get("renderer_fallback_reason"):
                    print(
                        f"Page {page['page']}: used {page['renderer']}: {page['renderer_fallback_reason']}"
                    )
        elif args.command == "fetch":
            fetch(args)
        elif args.command == "run":
            from .run import run_model

            command = json.loads(args.command_json) if args.command_json else None
            if command is not None and (
                not isinstance(command, list)
                or not command
                or not all(isinstance(s, str) for s in command)
            ):
                raise ValueError("command-json must be a nonempty array of strings")
            run = run_model(
                args.document,
                args.model,
                backend=args.backend,
                python=args.python,
                endpoint=args.endpoint,
                endpoint_model=args.endpoint_model,
                allow_remote=args.allow_remote,
                command=command,
                timeout=args.timeout,
                prompt=args.prompt_file.read_text() if args.prompt_file else None,
                max_tokens=args.max_tokens,
            )
            print(run)
            if read_json(run / "manifest.json")["status"] != "complete":
                parser.exit(1, "Run incomplete; inspect manifest.json and worker.log\n")
        elif args.command == "stitch":
            from .stitch import stitch_run

            stitch_run(args.run, args.overrides)
            print(args.run / "reading.md")
        elif args.command == "compare":
            from .report import compare

            print(compare(args.document))
        elif args.command == "evaluate":
            from .report import evaluate

            print(json.dumps(evaluate(args.run, args.references), indent=2))
        elif args.command in ("repair", "boundary-eval"):
            from .repair_cli import process

            process(args)
        elif args.command == "archive-list":
            from .archive import list_files

            print(json.dumps(list_files(args.item), indent=2))
        elif args.command == "archive-fetch":
            from .archive import download

            if args.max_mb < 1:
                raise ValueError("max-mb must be positive")
            print(download(args.item, args.file, args.out, args.max_mb * 1024 * 1024))
        elif args.command == "import-raw":
            from .imports import import_raw

            print(import_raw(args.document, args.raw))
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
