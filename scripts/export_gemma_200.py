"""Publish portable200-DPI evidence while preserving exact OCR/reading text."""

import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "workspace/gemma200"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--outputs", type=Path)
    args = parser.parse_args()
    prefixes = [
        (str(ROOT) + "/", ""),
        (str(Path.home() / ".cache/huggingface/hub") + "/", "model-cache/"),
    ]
    if args.source_root:
        prefixes.insert(1, (str(args.source_root.resolve()) + "/", ""))
    prefixes.append((str(Path.home()) + "/", "user-home/"))

    def portable(value):
        if isinstance(value, dict):
            return {
                k: v if k in {"markdown", "content", "thinking"} else portable(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [portable(v) for v in value]
        if isinstance(value, str):
            for old, new in prefixes:
                value = value.replace(old, new)
        return value

    dest = ROOT / "results/gemma200"
    dest.mkdir(parents=True, exist_ok=True)
    for source in BASE.rglob("*"):
        if not source.is_file() or "report" in source.relative_to(BASE).parts:
            continue
        if source.suffix not in {".json", ".jsonl", ".md"}:
            continue
        target = dest / source.relative_to(BASE)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".json":
            value = json.loads(source.read_text())
            target.write_text(json.dumps(portable(value), ensure_ascii=False, indent=2) + "\n")
            if "markdown" in value:
                assert json.loads(target.read_text())["markdown"] == value["markdown"]
        elif source.suffix == ".jsonl":
            target.write_text(
                "\n".join(
                    json.dumps(portable(json.loads(line)), ensure_ascii=False)
                    for line in source.read_text().splitlines()
                    if line.strip()
                )
                + "\n"
            )
        elif source.name.endswith(".boundaries.md"):
            target.write_text(portable(source.read_text()))
        else:
            target.write_bytes(source.read_bytes())
    for ext in ["json", "md", "html"]:
        source = BASE / "report" / ("comparison." + ext)
        name = "pdfocr-gemma-200dpi-comparison." + ext
        if ext == "json":
            payload = (
                json.dumps(portable(json.loads(source.read_text())), ensure_ascii=False, indent=2)
                + "\n"
            )
            (ROOT / "results" / name).write_text(payload)
        elif ext == "md":
            shutil.copy2(source, ROOT / "results" / name)
        if args.outputs:
            args.outputs.mkdir(parents=True, exist_ok=True)
            if ext == "json":
                (args.outputs / name).write_text(payload)
            else:
                shutil.copy2(source, args.outputs / name)
    log = (BASE / "budget1120/server.log").read_text(errors="replace")
    lines = [s for s in log.splitlines() if "image_max_pixels:" in s or "image_min_pixels:" in s]
    (dest / "budget1120/runtime-evidence.txt").write_text(
        "Finite child; LLAMA_ARG_IMAGE_MAX_TOKENS=1120\n" + "\n".join(dict.fromkeys(lines)) + "\n"
    )
    print("Exported200-DPI evidence; OCR and mapped source text preserved")


if __name__ == "__main__":
    main()
