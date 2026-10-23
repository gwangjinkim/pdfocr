"""Conservative, auditable page-boundary handling; never rewrite page OCR."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .util import atomic_text, digest, read_json, write_json

STRUCTURAL = re.compile(r"^\s*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|[>|]|```|~~~|\$\$|<)")


def edge_line(text: str, start: bool) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return (lines[0] if start else lines[-1]) if lines else ""


def boundary(left: dict, right: dict) -> dict:
    a, b = edge_line(left["markdown"], False), edge_line(right["markdown"], True)
    action, reason = "keep", "No strong continuation evidence"
    if right["page"] != left["page"] + 1:
        reason = "Nonadjacent source pages; never join across unprocessed pages"
    elif not a or not b:
        reason = "Empty page or missing content"
    elif STRUCTURAL.match(a) or STRUCTURAL.match(b):
        reason = "Structural boundary: heading, list, table, code, math, quote or HTML"
    elif a.endswith(("-", "\u00ad")) and b[0].islower():
        action, reason = (
            "review",
            "Possible split word; removing a lexical hyphen can change meaning",
        )
    elif not re.search(r"[.!?:;][\"'’”)]*$", a) and b[0].islower():
        action, reason = (
            "suggest_join",
            "Incomplete prose followed by lowercase text; review required",
        )
    return {
        "id": f"{left['page']}-{right['page']}",
        "left_page": left["page"],
        "right_page": right["page"],
        "left_tail": a[-200:],
        "right_head": b[:200],
        "suggestion": action,
        "reason": reason,
        "boundary_sha256": digest(
            [left["page"], right["page"], left["markdown"], right["markdown"]]
        ),
    }


def assemble(pages: list[dict], overrides: dict | None = None) -> dict:
    overrides = overrides or {}
    pages = sorted(pages, key=lambda p: p["page"])
    if len({p["page"] for p in pages}) != len(pages):
        raise ValueError("Duplicate page numbers")
    if any(not isinstance(p["markdown"], str) for p in pages):
        raise ValueError("Each page needs Markdown text")
    decisions, chunks, source_map, transforms = [], [], [], []
    length = 0
    for index, page in enumerate(pages):
        text = page["markdown"].strip()
        separator = ""
        if index:
            decision = boundary(pages[index - 1], page)
            override = overrides.get(decision["id"])
            decision["applied"] = "keep"
            if override:
                if override.get("boundary_sha256") != decision["boundary_sha256"]:
                    raise ValueError(
                        f"Stale override for {decision['id']}; regenerate boundary report"
                    )
                action = override.get("action", "keep")
                if action not in ("join", "keep"):
                    raise ValueError("Override action must be join or keep")
                if action == "join":
                    if decision["right_page"] != decision["left_page"] + 1:
                        raise ValueError("Cannot join nonadjacent source pages")
                    hyphen = override.get("hyphen", "keep")
                    if hyphen not in ("keep", "remove", "space"):
                        raise ValueError("hyphen must be keep, remove or space")
                    separator = " "
                    if chunks[-1].endswith(("-", "\u00ad")):
                        if hyphen == "remove":
                            chunks[-1] = chunks[-1][:-1]
                            length -= 1
                            source_map[-1]["end"] -= 1
                            transforms.append(
                                {
                                    "page": pages[index - 1]["page"],
                                    "operation": "remove-final-hyphen",
                                }
                            )
                            separator = ""
                        elif hyphen == "keep":
                            separator = ""
                    decision["applied"] = "join"
                    decision["hyphen"] = hyphen
            if decision["applied"] == "keep":
                separator = f"\n\n<!-- source-page: {page['page']} -->\n\n"
            decisions.append(decision)
        else:
            separator = f"<!-- source-page: {page['page']} -->\n\n"
        chunks.append(separator)
        length += len(separator)
        start = length
        chunks.append(text)
        length += len(text)
        source_map.append({"page": page["page"], "start": start, "end": length})
    edges = Counter(edge_line(p["markdown"], True) for p in pages)
    furniture = [line for line, count in edges.items() if line and count >= 3]
    return {
        "markdown": "".join(chunks) + "\n",
        "boundaries": decisions,
        "source_map": source_map,
        "transforms": transforms,
        "possible_repeated_headers": furniture,
        "policy": "review-first; joins require overrides with matching boundary hashes",
    }


def stitch_run(run: Path, overrides_path: Path | None = None) -> dict:
    manifest = read_json(run / "manifest.json")
    pages = []
    for record in manifest["pages"]:
        if record["status"] == "ok":
            pages.append(read_json(run / record["result"]))
    overrides = read_json(overrides_path) if overrides_path else {}
    stitched = assemble(pages, overrides)
    atomic_text(run / "reading.md", stitched.pop("markdown"))
    write_json(run / "boundaries.json", stitched)
    template = {
        b["id"]: {"action": "keep", "hyphen": "keep", "boundary_sha256": b["boundary_sha256"]}
        for b in stitched["boundaries"]
    }
    # Never overwrite the user's edited decisions.
    if not (run / "overrides.example.json").exists():
        write_json(run / "overrides.example.json", template)
    return stitched
