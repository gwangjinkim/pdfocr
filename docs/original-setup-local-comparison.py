"""Explicit one-shot download/setup; never starts a server.
Run after `uv sync` and `uv sync --project runners/mlx`.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "runners/mlx/.venv/bin/python"
BINARY_SHA = "5b0aa8d11c73b762d72ad692891f40f86dae0ef64015f2ab86b975d9becbb099"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cpu-only", action="store_true", help="Keep upstream CPU device selection; slower"
    )
    args = parser.parse_args()
    for model, revision in [
        ("glm-ocr", "24f15402e83baa0a80eeeaecf5480e172abc6f2e"),
        ("boundary-small", "3b1b1768f8f8cf8351c712464f906e86c2b8269e"),
        ("ovisocr3", "5f6ce6932efee9ec10c30746db55bd780214b7fd"),
        ("paddle-vl", "c5630abae1d940eafe0697512a0325494b02ab42"),
    ]:
        subprocess.run(
            [
                str(ROOT / ".venv/bin/pdfocr"),
                "fetch",
                model,
                "--python",
                str(PYTHON),
                "--revision",
                revision,
            ],
            cwd=ROOT,
            check=True,
        )
    code = """from huggingface_hub import snapshot_download
from pathlib import Path
import json,sys
name,repo,revision,pattern=sys.argv[1:]
path=snapshot_download(repo,revision=revision,allow_patterns=json.loads(pattern))
Path('models/'+name+'.json').write_text(json.dumps(dict(repo=repo,revision=revision,path=path),indent=2))
"""
    for name, repo, revision, patterns in [
        (
            "layout",
            "PaddlePaddle/PP-DocLayoutV3_safetensors",
            "e4f489dc536556fc1be02b973ba06756e0d4a2ac",
            None,
        ),
        (
            "teleocr-gguf",
            "rleo/TeleOCR-GGUF",
            "12abf24f6015602bc8ea521f08bde8a92329ab96",
            ["teleocr-q8v.gguf", "README.md"],
        ),
    ]:
        subprocess.run(
            [str(PYTHON), "-c", code, name, repo, revision, json.dumps(patterns)],
            cwd=ROOT,
            check=True,
        )
    folder = ROOT / "runners/teleocr-bin"
    folder.mkdir(exist_ok=True)
    archive = folder / "release.tar.gz"
    if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest() != BINARY_SHA:
        urllib.request.urlretrieve(
            "https://github.com/rzafiamy/teleocr-rs/releases/download/v0.2.0/teleocr-v0.2.0-macos-aarch64-metal.tar.gz",
            archive,
        )
    if hashlib.sha256(archive.read_bytes()).hexdigest() != BINARY_SHA:
        raise ValueError("Release checksum mismatch")
    if not (folder / "teleocr").exists() or args.cpu_only:
        with tarfile.open(archive) as source:
            source.extractall(folder, filter="data")
    if not args.cpu_only:
        source = ROOT / "runners/teleocr-rs"
        revision = "957cdbabe80e86d652c5fcc938ed7fbcf1eb2bbe"
        if not source.exists():
            subprocess.run(
                ["git", "clone", "https://github.com/rzafiamy/teleocr-rs.git", str(source)],
                check=True,
            )
        actual = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=source, text=True
        ).strip()
        if actual != revision:
            raise ValueError(
                f"TeleOCR source must be pinned at {revision}; found {actual}. No checkout was reset."
            )
        patch = ROOT / "docs/teleocr-metal-device.patch"
        applied = (
            subprocess.run(
                ["git", "apply", "--reverse", "--check", str(patch)],
                cwd=source,
                capture_output=True,
            ).returncode
            == 0
        )
        if not applied:
            subprocess.run(["git", "apply", "--check", str(patch)], cwd=source, check=True)
            subprocess.run(["git", "apply", str(patch)], cwd=source, check=True)
        subprocess.run(
            [
                "cargo",
                "+1.99.0",
                "build",
                "--release",
                "--locked",
                "-p",
                "teleocr-cli",
                "--no-default-features",
                "--features",
                "metal",
            ],
            cwd=source,
            check=True,
        )
        temporary = folder / "teleocr-new"
        shutil.copy2(source / "target/release/teleocr", temporary)
        temporary.replace(folder / "teleocr")
    print("Local setup complete. No services started.")


if __name__ == "__main__":
    main()
