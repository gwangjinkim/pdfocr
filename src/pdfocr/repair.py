from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

import httpx

from .util import atomic_text, read_json


def validate_decision(text: str, schema: dict) -> str:
    import re

    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text.strip(), re.S)
    data = json.loads(fenced[1] if fenced else text)
    properties = schema["properties"]
    if not isinstance(data, dict) or set(data) - set(properties):
        raise ValueError("Model returned unsupported keys or replacement text")
    if any(k not in data for k in schema.get("required", [])):
        raise ValueError("Model omitted required decision fields")
    for key, value in data.items():
        rule = properties[key]
        if rule["type"] == "boolean" and type(value) is not bool:
            raise ValueError(f"{key} must be a boolean")
        if rule["type"] == "string" and not isinstance(value, str):
            raise ValueError(f"{key} must be text")
        if "enum" in rule and value not in rule["enum"]:
            raise ValueError(f"{key} is not an allowed operation")
    return json.dumps(data, ensure_ascii=False)


class DecisionBackend:
    """Connect only to an already running, loopback Ollama; never start one."""

    def __init__(self, model: str, endpoint: str = "http://127.0.0.1:11434"):
        parsed = urlparse(endpoint)
        if parsed.scheme != "http" or parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Boundary Ollama endpoint must be loopback HTTP")
        if "cloud" in model.lower():
            raise ValueError("Cloud model tags are disabled; use a genuinely local model")
        self.model_name = model
        self.endpoint = endpoint.rstrip("/")

    def extract_json(self, prompt: str, schema: dict) -> str:
        with httpx.Client(timeout=120, trust_env=False, follow_redirects=False) as client:
            response = client.post(
                self.endpoint + "/api/chat",
                json={
                    "model": self.model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "format": schema,
                    "stream": False,
                    "keep_alive": 0,
                    "options": {"temperature": 0, "num_predict": 512, "num_ctx": 4096},
                },
            )
            response.raise_for_status()
        return validate_decision(response.json()["message"]["content"], schema)


class MLXDecisionBackend:
    """Small local text model; schema validation and lexical guards constrain edits."""

    def __init__(self, path: str):
        from mlx_lm import load

        self.model, self.tokenizer = load(path)
        self.model_name = path

    def extract_json(self, prompt: str, schema: dict) -> str:
        from mlx_lm import generate
        from mlx_lm.sample_utils import make_sampler

        messages = [
            {"role": "user", "content": prompt + "\nRequired JSON schema:\n" + json.dumps(schema)}
        ]
        text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
        )
        result = generate(
            self.model,
            self.tokenizer,
            prompt=text,
            max_tokens=512,
            sampler=make_sampler(temp=0.0),
            verbose=False,
        )
        return validate_decision(result, schema)


def export_raw_pages(run: Path, path: Path) -> Path:
    pages = []
    for record in read_json(run / "manifest.json")["pages"]:
        value = read_json(run / record["result"])
        suffix = " (Error)" if record["status"] != "ok" else ""
        text = value.get("markdown", "")
        # The borrowed format reserves these headers for page delimiters.
        import re

        if re.search(r"^## Page \d+(?: \(Error\))?\s*$", text, re.M):
            raise ValueError(
                "OCR text collides with reserved page delimiters; review it before repair"
            )
        pages.append(f"## Page {record['page']}{suffix}\n\n{text}\n")
    atomic_text(path, "\n".join(pages))
    return path
