"""Explicit page tiling, with complete coverage and exact pixel provenance."""

import hashlib
from pathlib import Path

from PIL import Image

from .util import file_hash, write_json

TILE_PROMPT = (
    "All supplied images depict the SAME single book page. The first is the full-page "
    "overview. Any following images are magnified horizontal bands in top-to-bottom "
    "order, with small overlaps. Use the overview for layout and the bands for detail. "
    "Transcribe the page ONCE in normal reading order; do not repeat overlapping text. "
    "Preserve printed spelling, punctuation, footnotes and visible line-final hyphens. "
    "Do not complete words cut off at the page edge. "
    "Extract all readable text and format it as structured Markdown."
)


def band_boxes(width: int, height: int, count: int = 4) -> list[tuple[int, int, int, int]]:
    if width < 1 or height < count or count < 1:
        raise ValueError("Page must have positive width and at least one row per band")
    overlap = max(1, round(height * 0.02))
    edges = [height * i // count for i in range(count + 1)]
    return [
        (
            0,
            max(0, edges[i] - (overlap if i else 0)),
            width,
            min(height, edges[i + 1] + (overlap if i + 1 < count else 0)),
        )
        for i in range(count)
    ]


def make_views(source: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        image = image.convert("RGB")
        boxes = band_boxes(*image.size)
        views = [
            {
                "role": "overview",
                "path": str(source),
                "sha256": file_hash(source),
                "size": list(image.size),
            }
        ]
        covered = [False] * image.height
        for i, box in enumerate(boxes, 1):
            crop = image.crop(box)
            target = out / f"band-{i}.png"
            if target.exists():
                with Image.open(target) as saved:
                    assert (
                        saved.size == crop.size and saved.convert("RGB").tobytes() == crop.tobytes()
                    )
            else:
                crop.save(target)
            for y in range(box[1], box[3]):
                covered[y] = True
            views.append(
                {
                    "role": f"band-{i}",
                    "path": str(target),
                    "box": list(box),
                    "sha256": file_hash(target),
                    "size": list(crop.size),
                    "rgb_sha256": hashlib.sha256(crop.tobytes()).hexdigest(),
                    "exact_source_crop": True,
                }
            )
        assert all(covered)
        result = {
            "parent_sha256": file_hash(source),
            "parent_size": list(image.size),
            "all_rows_covered": True,
            "band_count": len(boxes),
            "overlap_fraction_per_side": 0.02,
            "views": views,
        }
    write_json(out / "views.json", result)
    return result
