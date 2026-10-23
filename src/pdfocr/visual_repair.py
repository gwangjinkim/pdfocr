"""Source-backed recovery of missing inter-page hyphens, without rewriting OCR."""

from __future__ import annotations

import copy
import hashlib
import re
import unicodedata

WORD = r"[^\W\d_]+"


def body_text(text: str) -> str:
    text = text.strip()
    for _ in range(2):
        text = re.sub(r"^\s*(?:[-—–]\s*)?\d{1,4}(?:\s*[-—–])?\s*\n\s*", "", text, count=1)
    return text


def norm(text):
    return unicodedata.normalize("NFC", text).replace("ſ", "s").casefold()


def evidence_gate(*, left_page, right_page, left_ocr, right_ocr, visual_left, visual_right):
    def no(reason):
        return {"eligible": False, "reason": reason}

    if right_page != left_page + 1:
        return no("nonadjacent pages")
    left = body_text(left_ocr)
    right = body_text(right_ocr)
    if not left or not right:
        return no("empty OCR edge")
    if left.rstrip().endswith(("-", "¬", "\u00ad")):
        return no("hyphen already present; retain baseline repair")
    if re.match(r"^(?:#{1,6}\s|[>|]|```|<)", right):
        return no("structural right edge")
    visual_end = re.search("(" + WORD + r")[-¬\u00ad]\s*$", visual_left)
    if visual_end is None:
        return no("visual OCR does not show terminal hyphen")
    end = re.search("(" + WORD + r")\s*$", left)
    start = re.match("(" + WORD + ")", right)
    vstart = re.match("(" + WORD + ")", body_text(visual_right))
    if not end or not start or not vstart:
        return no("cannot align lexical edges")
    if norm(end[1]) != norm(visual_end[1]) or norm(start[1]) != norm(vstart[1]):
        return no("visual and page OCR edge words disagree")
    if not start[1][0].islower() or norm(start[1]) in ("und", "oder", "bzw"):
        return no("uppercase or coordination needs review")
    return {
        "eligible": True,
        "left_stem": end[1],
        "right_stem": start[1],
        "reason": "visible terminal hyphen and both edge words match page OCR",
    }


def remove_boundary_separators(text, mapping, pairs):
    """Only delete mapped separators between consecutive source-page spans."""
    spans = mapping["spans"]
    drops = []
    applied = []
    for left, right in pairs:
        ls = [i for i, s in enumerate(spans) if s.get("kind") == "source" and s.get("page") == left]
        rs = [
            i for i, s in enumerate(spans) if s.get("kind") == "source" and s.get("page") == right
        ]
        if not ls or not rs or right != left + 1:
            continue
        a, b = ls[-1], rs[0]
        between = spans[a + 1 : b]
        if b <= a + 1 or not between or any(s["kind"] != "separator" for s in between):
            continue
        start, end = spans[a]["output_end"], spans[b]["output_start"]
        if not text[start:end].isspace():
            continue
        if any(not (end <= x or start >= y) for x, y in drops):
            continue
        drops.append((start, end))
        applied.append(
            {
                "left_page": left,
                "right_page": right,
                "old_start": start,
                "old_end": end,
                "removed_separator": text[start:end],
            }
        )
    drops.sort()

    def shift(x):
        return x - sum(max(0, min(x, b) - a) for a, b in drops if x > a)

    result = copy.deepcopy(mapping)
    result["spans"] = []
    for s in spans:
        t = copy.deepcopy(s)
        t["output_start"] = shift(s["output_start"])
        t["output_end"] = shift(s["output_end"])
        if t["output_end"] > t["output_start"]:
            result["spans"].append(t)
    for a, b in reversed(drops):
        text = text[:a] + text[b:]
    for boundary in result.get("boundaries", []):
        if "output_offset" in boundary:
            boundary["output_offset"] = shift(boundary["output_offset"])
    for relocation in result.get("relocations", []):
        for key in ("output_start", "output_end"):
            if key in relocation:
                relocation[key] = shift(relocation[key])
    result["output_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    result["visual_separator_removals"] = applied
    return {"text": text, "map": result, "applied": applied}
