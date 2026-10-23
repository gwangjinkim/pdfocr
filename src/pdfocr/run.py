from __future__ import annotations

import importlib.metadata
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from .stitch import stitch_run
from .util import atomic_text, digest, file_hash, read_json, registry, write_json


def stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    # Only the process group created by this call, never a name/PID search.
    os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=5)


def execute(argv: list[str], log: Path, timeout: float, env: dict) -> dict:
    start = time.monotonic()
    with log.open("a") as stream:
        proc = subprocess.Popen(
            argv, stdout=stream, stderr=subprocess.STDOUT, env=env, start_new_session=True
        )
        details = {"pid": proc.pid, "started_at_unix": time.time(), "argv": argv}
        try:
            details["returncode"] = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            details["timed_out"] = True
            stop_process(proc)
        finally:
            stop_process(proc)
        details["exited"] = proc.poll() is not None
        details["seconds"] = time.monotonic() - start
        return details


def run_model(
    document: Path,
    model_name: str,
    *,
    backend: str | None = None,
    python: str | None = None,
    endpoint: str | None = None,
    endpoint_model: str | None = None,
    allow_remote: bool = False,
    command: list[str] | None = None,
    timeout: float = 900,
    prompt: str | None = None,
    max_tokens: int | None = None,
) -> Path:
    if not 1 <= timeout <= 86400:
        raise ValueError("Timeout must be between 1 and 86400 seconds")
    document = document.resolve(strict=True)
    manifest = read_json(document / "document.json")
    model = registry()[model_name].copy()
    backend = backend or model["backend"]
    if backend not in ("native", "mlx", "endpoint", "command", "teleocr"):
        raise ValueError("Use repair or boundary-eval for text-only boundary models")
    pin_path = Path("models") / f"{model_name}.json"
    pin = read_json(pin_path) if pin_path.exists() else None
    if backend == "teleocr":
        pin = read_json(Path("models/teleocr-gguf.json"))
    model_path = pin["path"] if pin else None
    task_prompt = prompt if prompt is not None else model.get("prompt")
    if max_tokens is not None:
        if max_tokens < 1:
            raise ValueError("max_tokens must be positive")
        model["max_tokens"] = max_tokens
    if backend == "mlx":
        if not pin or not Path(model_path).is_dir():
            raise ValueError(
                f"First run: pdfocr fetch {model_name} --python runners/mlx/.venv/bin/python"
            )
        if task_prompt is None and "prompt_file" in model:
            task_prompt = (Path(model_path) / model["prompt_file"]).read_text()
        if not python:
            raise ValueError(
                "Specify --python runners/mlx/.venv/bin/python for the isolated runner"
            )
    if backend == "endpoint":
        if not endpoint:
            raise ValueError("Specify --endpoint, including /v1")
        parsed = urlparse(endpoint)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise ValueError("Endpoint must be an http(s) URL")
        local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        if not local and not allow_remote:
            raise ValueError("Remote endpoint uploads page images; add --allow-remote explicitly")
        if parsed.username or parsed.password or parsed.query:
            raise ValueError("Use an environment variable for credentials, not the endpoint URL")
        if not local and parsed.scheme != "https":
            raise ValueError("Remote endpoints must use HTTPS")
        # A full pipeline cannot be faithfully invoked as generic image chat.
        if task_prompt is None:
            raise ValueError("Supply the model's documented task prompt with --prompt-file")
    if backend == "command" and not command:
        raise ValueError(
            "This model needs an official pipeline runner: supply --command-json; see docs/adapters.md"
        )
    config = {
        "model_name": model_name,
        "model": model,
        "backend": backend,
        "model_pin": pin if backend in ("mlx", "teleocr") else None,
        "endpoint": endpoint,
        "endpoint_model": endpoint_model or model["repo"],
        "prompt": task_prompt,
        "command": command,
        "timeout": timeout,
        # Resolving a venv's interpreter symlink loses the venv's site-packages.
        "python": os.path.abspath(python) if python else sys.executable,
        "harness_version": importlib.metadata.version("pdfocr-lab"),
        "teleocr_binary_sha256": file_hash(Path("runners/teleocr-bin/teleocr"))
        if backend == "teleocr"
        else None,
        "layout_pin": read_json(Path("models/layout.json"))
        if model.get("pipeline") == "paddle-layout"
        else None,
        "implementation_sha256": digest(
            {p.name: file_hash(p) for p in Path(__file__).parent.glob("*.py")}
        ),
    }
    key = digest([config, manifest])[:16]
    run = document / "runs" / f"{model_name}-{backend}-{key}"
    run.mkdir(parents=True, exist_ok=True)
    # Prevent two invocations from racing on the same result directory.
    lock = run / ".running"
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ValueError(
            f"Run is locked: {lock}. Verify its recorded PID before removing a stale lock"
        ) from None
    os.write(fd, f"pid={os.getpid()} started={time.time()}\n".encode())
    os.close(fd)
    try:
        return _run_locked(run, document, manifest, config, model_path, command, timeout)
    finally:
        lock.unlink(missing_ok=True)


def _run_locked(run, document, manifest, config, model_path, command, timeout):
    model, backend = config["model"], config["backend"]
    work, records, all_inputs = [], [], []
    for page in manifest["pages"]:
        image = document / page["image"]
        if file_hash(image) != page["image_sha256"]:
            raise ValueError(f"Prepared page changed: {image}; prepare a fresh document")
        destination = run / f"page-{page['page']:04d}.json"
        record = {"page": page["page"], "result": destination.name, "status": "pending"}
        records.append(record)
        cached = read_json(destination) if destination.exists() else {}
        # Failed pages retry on the next invocation; successful pages resume from disk.
        longest = model.get("longest_edge", 2048)
        image_out = run / "inputs" / image.name
        image_out.parent.mkdir(exist_ok=True)
        with Image.open(image) as im:
            im = im.convert("RGB")
            im.thumbnail((longest, longest), Image.Resampling.LANCZOS)
            im.save(image_out)
            size = list(im.size)
        prepared_input = {
            "page": page["page"],
            "image_path": str(image_out.resolve()),
            "input_size": size,
            "image_sha256": file_hash(image_out),
            "result_path": str(destination.resolve()),
        }
        all_inputs.append(prepared_input)
        if cached.get("status") != "ok":
            work.append(prepared_input)
    request = {
        **config,
        "model_path": model_path,
        "pages": work,
        "request_timeout": min(timeout, 300),
        "document": str(document),
    }
    write_json(run / "request.json", request)
    result = {
        "schema_version": 1,
        "config": config,
        "source_sha256": manifest["source_sha256"],
        "document": str(document),
        "pages": records,
        "inputs": all_inputs,
        "status": "running",
    }
    write_json(run / "manifest.json", result)
    process_info = None
    if backend == "native":
        for page, record in zip(manifest["pages"], records, strict=True):
            write_json(
                run / record["result"],
                {
                    "page": page["page"],
                    "status": "ok",
                    "markdown": (document / page["native_markdown"]).read_text(),
                    "backend": "pdfrune",
                    "seconds": 0,
                    "timing_note": "Native extraction was performed during prepare; zero is not measured inference time",
                },
            )
    elif work:
        env = os.environ.copy()
        env["PYTHONPATH"] = (
            str(Path(__file__).parent.parent) + os.pathsep + env.get("PYTHONPATH", "")
        )
        env["HF_HUB_OFFLINE"] = "1"
        env["TOKENIZERS_PARALLELISM"] = "false"
        if backend == "command":
            argv = [
                s.replace("{request}", str((run / "request.json").resolve())).replace(
                    "{run}", str(run.resolve())
                )
                for s in command
            ]
        else:
            argv = [config["python"], "-m", "pdfocr.worker", str((run / "request.json").resolve())]
        process_info = execute(argv, run / "worker.log", timeout, env)
    for record in records:
        path = run / record["result"]
        if path.exists():
            value = read_json(path)
            if value.get("page") != record["page"]:
                raise ValueError("Worker returned the wrong page number")
            record["status"] = value.get("status", "error")
            if record["status"] == "ok" and not isinstance(value.get("markdown"), str):
                record["status"] = "error"
            record["seconds"] = value.get("seconds")
            record["possibly_truncated"] = value.get("possibly_truncated", False)
        else:
            record["status"] = "error"
            write_json(
                path,
                {
                    "page": record["page"],
                    "status": "error",
                    "markdown": "",
                    "error": "Worker did not return this page; inspect worker.log and process status",
                },
            )
    result["status"] = "complete" if all(r["status"] == "ok" for r in records) else "incomplete"
    result["process"] = process_info
    write_json(run / "manifest.json", result)
    paginated = []
    for record in records:
        value = read_json(run / record["result"])
        paginated.append(
            f"<!-- source-page: {record['page']} status: {record['status']} -->\n\n"
            + value.get("markdown", "")
        )
    atomic_text(run / "pages.md", "\n\n".join(paginated) + "\n")
    stitch_run(run)
    return run
