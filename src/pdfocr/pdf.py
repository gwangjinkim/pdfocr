from __future__ import annotations

import importlib.metadata
import math
from pathlib import Path

import pdfrune
from PIL import Image, ImageStat

from .util import atomic_text, file_hash, parse_pages, write_json


def prepare(
    source: Path,
    out: Path,
    pages: str | None,
    dpi: float,
    renderer: str = "auto",
    *,
    max_pixels: int = 40_000_000,
) -> dict:
    if not math.isfinite(dpi) or not 36 <= dpi <= 600:
        raise ValueError("DPI must be between 36 and 600")
    if type(max_pixels) is not int or not 1 <= max_pixels <= 160_000_000:
        raise ValueError("max_pixels must be an integer between 1 and 160 million")
    source = source.resolve(strict=True)
    if (out / "document.json").exists():
        raise ValueError("Output already contains a document; use a new directory")
    out.mkdir(parents=True, exist_ok=True)
    records = []
    with pdfrune.open(str(source)) as doc:
        if doc.needs_pass:
            raise ValueError("Encrypted PDF: supply an authorized decrypted copy")
        selected = parse_pages(pages, len(doc))
        for number in selected:
            page = doc[number - 1]
            expected_pixels = (page.width * dpi / 72) * (page.height * dpi / 72)
            if not math.isfinite(expected_pixels) or expected_pixels > max_pixels:
                raise ValueError(f"Page {number}: raster would exceed {max_pixels:,} pixels")
            stem = f"page-{number:04d}"
            image_path = out / "pages" / f"{stem}.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            actual_renderer, fallback_reason = "pdfrune", None
            try:
                if renderer == "pdfium":
                    raise ValueError("PDFium explicitly selected")
                page.render(dpi=dpi).save(str(image_path))
                with Image.open(image_path) as probe:
                    if max(ImageStat.Stat(probe.convert("RGB")).stddev) < 0.5:
                        raise ValueError("pdfrune raster is nearly blank; verify original page")
            except Exception as exc:
                if renderer == "pdfrune":
                    raise ValueError(
                        f"Page {number}: {exc}; try --renderer auto or pdfium"
                    ) from exc
                import pypdfium2

                with pypdfium2.PdfDocument(str(source)) as independent:
                    pdfium_page = independent[number - 1]
                    bitmap = pdfium_page.render(scale=dpi / 72)
                    bitmap.to_pil().save(image_path)
                    bitmap.close()
                    pdfium_page.close()
                actual_renderer, fallback_reason = "pdfium", str(exc)
            with Image.open(image_path) as image:
                width, height = image.size
                # Smoke signal only: a nonblank raster is not proof of rendering fidelity.
                nearly_blank = max(ImageStat.Stat(image.convert("RGB")).stddev) < 0.5
            text = page.extract_text()
            atomic_text(out / "native" / f"{stem}.txt", text)
            atomic_text(out / "native" / f"{stem}.md", page.to_markdown())
            words = page.extract_words()
            blocks = page.extract_blocks()
            geometry = {
                "page": number,
                "coordinate_system": "pdfrune page coordinates, top-left origin, points",
                "page_rect": list(page.rect),
                "rotation": page.rotation,
                "words": words,
                "blocks": blocks,
            }
            write_json(out / "native" / f"{stem}.json", geometry)
            records.append(
                {
                    "page": number,
                    "image": f"pages/{stem}.png",
                    "native_text": f"native/{stem}.txt",
                    "native_markdown": f"native/{stem}.md",
                    "geometry": f"native/{stem}.json",
                    "image_sha256": file_hash(image_path),
                    "width": width,
                    "height": height,
                    "dpi": dpi,
                    "page_width_pt": page.width,
                    "page_height_pt": page.height,
                    "native_chars": len(text),
                    "nearly_blank_raster": nearly_blank,
                    "renderer": actual_renderer,
                    "renderer_fallback_reason": fallback_reason,
                }
            )
        manifest = {
            "schema_version": 1,
            "source": str(source),
            "source_sha256": file_hash(source),
            "page_count": len(doc),
            "selected_pages": selected,
            "pages": records,
            "renderer": renderer,
            "max_render_pixels": max_pixels,
            "native_extractor": "pdfrune",
            "renderer_version": importlib.metadata.version("pdfrune"),
            "render_review": "unreviewed; inspect page PNGs before trusting OCR",
        }
    write_json(out / "document.json", manifest)
    return manifest
