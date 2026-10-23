"""Internet Archive metadata and explicit public-PDF downloads. No account bypass."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

import httpx

from .util import file_hash, write_json


def identifier(value: str) -> str:
    if "://" in value:
        url = urlparse(value)
        if url.scheme != "https" or url.hostname not in ("archive.org", "www.archive.org"):
            raise ValueError("Use an archive.org details URL or an item identifier")
        match = re.match(r"^/details/([^/]+)", url.path)
        if not match:
            raise ValueError("Expected an archive.org/details/ITEM URL")
        value = unquote(match[1])
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", value) or value in (".", ".."):
        raise ValueError("Invalid Archive identifier")
    return value


def list_files(value: str) -> dict:
    item = identifier(value)
    with httpx.Client(timeout=60, follow_redirects=False) as client:
        response = client.get(f"https://archive.org/metadata/{item}")
        response.raise_for_status()
    data = response.json()
    files = [
        {k: f.get(k) for k in ("name", "format", "size", "sha1", "private")}
        for f in data.get("files", [])
        if str(f.get("name", "")).lower().endswith(".pdf")
    ]
    return {
        "identifier": item,
        "files": files,
        "note": "Choose an exact public file. Restricted borrowing/login is not bypassed.",
    }


def download(value: str, filename: str, out: Path, max_bytes: int) -> Path:
    listing = list_files(value)
    row = next((f for f in listing["files"] if f["name"] == filename), None)
    if not row or row.get("private"):
        raise ValueError("File is absent or marked private")
    if row.get("size") and int(row["size"]) > max_bytes:
        raise ValueError("File exceeds the requested download limit")
    out.mkdir(parents=True, exist_ok=True)
    target = out / (listing["identifier"] + ".pdf")
    if target.exists():
        raise ValueError("Destination exists; choose another directory")
    temp = target.with_suffix(".partial")
    url = f"https://archive.org/download/{listing['identifier']}/{quote(filename, safe='')}"
    import hashlib

    sha1 = hashlib.sha1()
    try:
        # Archive's storage redirect is allowed; this request has no credentials.
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response:
            response.raise_for_status()
            size = 0
            with temp.open("wb") as f:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > max_bytes:
                        raise ValueError("Download exceeded limit")
                    f.write(chunk)
                    sha1.update(chunk)
        with temp.open("rb") as f:
            if not f.read(1024).lstrip().startswith(b"%PDF-"):
                raise ValueError("Archive returned non-PDF content")
        if row.get("sha1") and sha1.hexdigest() != row["sha1"]:
            raise ValueError("Archive SHA-1 integrity check failed")
        temp.replace(target)
    finally:
        temp.unlink(missing_ok=True)
    write_json(
        target.with_suffix(".source.json"),
        {"url": url, "file": row, "sha256": file_hash(target), "sha1": sha1.hexdigest()},
    )
    return target
