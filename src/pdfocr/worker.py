"""One foreground model worker. It exits after the requested pages finish."""

from __future__ import annotations

import base64
import importlib.metadata
import json
import os
import sys
import time
import traceback
from pathlib import Path


def save(path: Path, value: dict) -> None:
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    os.replace(temp, path)


def run(request: dict) -> None:
    backend, model = request["backend"], request["model"]
    generator = None
    load_seconds = 0.0
    versions = {}
    if backend == "mlx":
        from mlx_vlm import generate, load
        from mlx_vlm.prompt_utils import apply_chat_template

        start = time.monotonic()
        network_guard = {"local_files_only": True}
        # Models have already been downloaded and pinned by `pdfocr fetch`.
        generator, processor = load(request["model_path"], **network_guard)
        load_seconds = time.monotonic() - start
        versions = {p: importlib.metadata.version(p) for p in ("mlx", "mlx-vlm", "transformers")}
    elif backend == "teleocr":
        pass
    elif backend == "endpoint":
        import httpx

        versions = {"httpx": importlib.metadata.version("httpx")}
    else:
        raise ValueError(f"Unknown worker backend: {backend}")
    layout = None
    if model.get("pipeline") == "paddle-layout":
        from .local_pipelines import PaddleLayout

        layout_start = time.monotonic()
        layout = PaddleLayout(request["layout_pin"]["path"])
        load_seconds += time.monotonic() - layout_start
        versions["torch"] = importlib.metadata.version("torch")
    for page in request["pages"]:
        destination = Path(page["result_path"])
        start = time.monotonic()
        try:
            if backend == "teleocr":
                from .local_pipelines import teleocr_page

                text, raw, metadata = teleocr_page(request, page)
            elif layout is not None:
                text, raw, metadata = layout.recognize(generator, processor, page, model)
            elif backend == "mlx":
                formatted = apply_chat_template(
                    processor, generator.config, request["prompt"], num_images=1
                )
                response = generate(
                    generator,
                    processor,
                    formatted,
                    image=[page["image_path"]],
                    max_tokens=model["max_tokens"],
                    temperature=model.get("temperature", 0.0),
                    verbose=False,
                )
                text = response.text
                tokens = getattr(response, "generation_tokens", None)
                metadata = {
                    "generation_tokens": tokens,
                    "possibly_truncated": tokens is not None and tokens >= model["max_tokens"],
                }
                try:
                    import mlx.core as mx

                    metadata["mlx_peak_memory_bytes"] = mx.get_peak_memory()
                except (AttributeError, ImportError):
                    pass
                raw = {"text": text, **metadata}
            else:
                content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/png;base64,"
                            + base64.b64encode(Path(page["image_path"]).read_bytes()).decode()
                        },
                    }
                ]
                if request["prompt"]:
                    content.append({"type": "text", "text": request["prompt"]})
                payload = {
                    "model": request["endpoint_model"],
                    "messages": [{"role": "user", "content": content}],
                    "max_tokens": model["max_tokens"],
                    "temperature": model.get("temperature", 0.0),
                }
                payload.update(request.get("extra_body", {}))
                headers = {}
                token = os.environ.get(request.get("api_key_env", "PDFOCR_API_KEY"))
                if token:
                    headers["Authorization"] = f"Bearer {token}"
                # Never follow document/provider redirects with credentials.
                with httpx.Client(
                    timeout=request["request_timeout"], follow_redirects=False
                ) as client:
                    response = client.post(
                        request["endpoint"].rstrip("/") + "/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                    response.raise_for_status()
                    raw = response.json()
                choice = raw["choices"][0]
                text = choice["message"]["content"]
                if not isinstance(text, str):
                    raise ValueError("Endpoint content must be a string")
                metadata = {
                    "finish_reason": choice.get("finish_reason"),
                    "possibly_truncated": choice.get("finish_reason") == "length",
                    "usage": raw.get("usage"),
                    "returned_model": raw.get("model"),
                }
            save(
                destination,
                {
                    "page": page["page"],
                    "status": "ok",
                    "markdown": text,
                    "raw": raw,
                    "seconds": time.monotonic() - start,
                    "load_seconds": load_seconds,
                    "backend": backend,
                    "runtime_versions": versions,
                    **metadata,
                },
            )
        except Exception as exc:
            save(
                destination,
                {
                    "page": page["page"],
                    "status": "error",
                    "markdown": "",
                    "error": f"{type(exc).__name__}: {exc}",
                    "seconds": time.monotonic() - start,
                },
            )
            traceback.print_exc()


if __name__ == "__main__":
    run(json.loads(Path(sys.argv[1]).read_text()))
