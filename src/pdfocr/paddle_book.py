"""Book-oriented assembly of already recognized Paddle layout regions."""


def assemble_book(blocks):
    furniture = {"number", "header", "header_image", "footer", "footer_image"}
    candidates = [
        i for i, b in enumerate(blocks) if b["label"] not in furniture and b.get("text", "").strip()
    ]
    kept = []
    omitted = []
    for i in sorted(candidates, key=lambda n: (-blocks[n].get("score", 0), n)):
        a = blocks[i]["bbox"]
        area = (a[2] - a[0]) * (a[3] - a[1])
        duplicate = None
        for j in kept:
            b = blocks[j]["bbox"]
            other = (b[2] - b[0]) * (b[3] - b[1])
            inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
                0, min(a[3], b[3]) - max(a[1], b[1])
            )
            if inter / max(1, area + other - inter) > 0.9:
                duplicate = j
                break
        if duplicate is None:
            kept.append(i)
        else:
            omitted.append(
                {
                    "index": i,
                    "duplicate_of": duplicate,
                    "reason": "intersection-over-union > 0.9; keep higher-confidence layout region",
                }
            )
    kept.sort()
    return {
        "markdown": "\n\n".join(blocks[i]["text"].strip() for i in kept),
        "kept_indices": kept,
        "omitted_duplicates": omitted,
        "policy": "book-v1: retain footnotes and marginal text; exclude page furniture; suppress near-identical overlapping regions across labels",
    }
