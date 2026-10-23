from pathlib import Path

from .borrowed.archive_stitching import read_pages
from .stitch import stitch_run
from .util import atomic_text, file_hash, read_json, write_json


def import_raw(document: Path, raw: Path) -> Path:
    document = document.resolve(strict=True)
    raw = raw.resolve(strict=True)
    data = read_json(document / "document.json")
    selected = set(data["selected_pages"])
    pages = [p for p in read_pages(raw) if p.number in selected]
    if not pages:
        raise ValueError("No page numbers in raw OCR match the prepared document")
    run = document / "runs" / ("archiveorgocr-import-" + file_hash(raw)[:12])
    if run.exists():
        raise ValueError("This raw file was already imported")
    run.mkdir(parents=True)
    records = []
    for number in sorted(selected):
        page = next((p for p in pages if p.number == number), None)
        status = "ok" if page and not page.error else "error"
        name = f"page-{number:04d}.json"
        write_json(
            run / name,
            {
                "page": number,
                "status": status,
                "markdown": page.text if page else "",
                "source_raw": str(raw),
                "source_raw_start": page.raw_start if page else None,
            },
        )
        records.append({"page": number, "status": status, "result": name})
    write_json(
        run / "manifest.json",
        {
            "schema_version": 1,
            "source_sha256": data["source_sha256"],
            "import_raw_sha256": file_hash(raw),
            "import_raw": str(raw),
            "config": {
                "model_name": "archiveorgocr-import",
                "backend": "import",
                "model": {"mode": "existing-page-ocr"},
            },
            "pages": records,
            "status": "complete" if all(r["status"] == "ok" for r in records) else "incomplete",
        },
    )
    atomic_text(
        run / "pages.md",
        "\n\n".join(
            f"<!-- source-page: {r['page']} -->\n\n" + read_json(run / r["result"])["markdown"]
            for r in records
        ),
    )
    stitch_run(run)
    return run
