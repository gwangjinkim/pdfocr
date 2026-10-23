"""Explicit public-book download and frozen 200-DPI baseline preparation."""

import argparse
from pathlib import Path

from pdfocr.archive import download
from pdfocr.pdf import prepare
from pdfocr.util import file_hash, read_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="Download missing public PDF files")
    parser.add_argument(
        "--prepare", action="store_true", help="Render the frozen PDFium 200-DPI baseline"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if root != Path.cwd():
        parser.error("Run from the repository root")
    books = read_json(root / "datasets/books.json")
    selected = read_json(root / "datasets/expanded/selection.json")
    for book in books:
        source = root / "data" / f"{book['id']}.pdf"
        if not source.exists():
            if not args.download:
                raise ValueError(f"Missing {source}; supply the exact PDF or use --download")
            download(book["id"], book["filename"], source.parent, 1_000_000_000)
        if file_hash(source) != book["sha256"]:
            raise ValueError(
                f"PDF differs from frozen experiment: {source}. No result or reference was replaced."
            )
        if args.prepare:
            record = next(b for b in selected["books"] if b["id"] == book["id"])
            folder = root / record["document"]
            if not (folder / "document.json").exists():
                prepare(source, folder, record["pages"], 200, "pdfium")
            print("Prepared", book["id"], folder, flush=True)
    print("Inspect rendered pages before trusting OCR; no inference or service was started.")


if __name__ == "__main__":
    main()
