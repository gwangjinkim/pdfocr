from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def write_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def registry() -> dict:
    return read_json(Path(__file__).with_name("models.json"))


def parse_pages(spec: str | None, count: int) -> list[int]:
    if not spec:
        return list(range(1, count + 1))
    result: set[int] = set()
    for part in spec.split(","):
        bounds = part.strip().split("-")
        if len(bounds) == 1:
            result.add(int(bounds[0]))
        elif len(bounds) == 2:
            lo, hi = map(int, bounds)
            if lo > hi:
                raise ValueError("Page ranges must ascend")
            result.update(range(lo, hi + 1))
        else:
            raise ValueError(f"Invalid page range: {part}")
    if not result or min(result) < 1 or max(result) > count:
        raise ValueError(f"Pages must be between 1 and {count}")
    return sorted(result)
