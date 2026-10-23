"""Recompute published OCR metrics from archived responses without inference."""

from pathlib import Path

from pdfocr.book_compare import content_text, rates
from pdfocr.paddle_book import assemble_book
from pdfocr.util import file_hash, read_json


def main():
    root = Path(__file__).resolve().parents[1]
    for name, digest in read_json(root / "datasets/expanded/reference-hashes.json").items():
        assert file_hash(root / "datasets/expanded" / name) == digest
    for group, summary in [
        ("200", read_json(root / "results/pdfocr-expanded-comparison.json")["models"]),
        ("400", read_json(root / "results/pdfocr-400dpi-comparison.json")["new"]["models"]),
    ]:
        for model in summary:
            name = model["name"]
            source_model = "paddle-vl" if name == "paddle-book" else name
            # The initial report stores book assembly as a separate variant.
            scores = []
            for folder in (root / "datasets/expanded/references").iterdir():
                for ref in folder.glob("page-*.txt"):
                    value = read_json(
                        root
                        / "results/raw-pages"
                        / group
                        / folder.name
                        / source_model
                        / (ref.stem + ".json")
                    )
                    markdown = (
                        assemble_book(value["raw"]["blocks"])["markdown"]
                        if name == "paddle-book"
                        else value["markdown"]
                    )
                    scores.append(rates(content_text(ref.read_text()), content_text(markdown)))
            cer = sum(p["character_edits"] for p in scores) / sum(
                p["reference_characters"] for p in scores
            )
            wer = sum(p["word_edits"] for p in scores) / sum(p["reference_words"] for p in scores)
            assert (
                len(scores) == 14
                and abs(cer - model["cer"]) < 1e-12
                and abs(wer - model["wer"]) < 1e-12
            ), (group, name, cer, model["cer"])
            print(group, name, f"CER {100 * cer:.3f}%", f"WER {100 * wer:.3f}%")
    # The 200-DPI book variant is not part of its original four-model list.
    expected = read_json(root / "results/pdfocr-expanded-comparison.json")["paddle_book_variant"]
    scores = []
    for ref in (root / "datasets/expanded/references").glob("*/*.txt"):
        value = read_json(
            root / "results/raw-pages/200" / ref.parent.name / "paddle-vl" / (ref.stem + ".json")
        )
        scores.append(
            rates(
                content_text(ref.read_text()),
                content_text(assemble_book(value["raw"]["blocks"])["markdown"]),
            )
        )
    assert (
        abs(
            sum(p["character_edits"] for p in scores)
            / sum(p["reference_characters"] for p in scores)
            - expected["cer"]
        )
        < 1e-12
    )
    mapping = read_json(root / "results/paddle-fraktur-400dpi-repaired.pages.json")
    output = root / mapping["output_file"]
    raw = root / mapping["raw_file"]
    assert file_hash(output) == mapping["output_sha256"] and file_hash(raw) == mapping["raw_sha256"]
    text, source = output.read_text(), raw.read_text()
    cursor = 0
    for span in mapping["spans"]:
        assert span["output_start"] == cursor
        if span["kind"] == "source":
            assert (
                text[span["output_start"] : span["output_end"]]
                == source[span["raw_start"] : span["raw_end"]]
            )
        cursor = span["output_end"]
    assert cursor == len(text)
    pos = mapping["boundaries"][0]["output_offset"]
    assert text[pos - 3 : pos + 4] == "Person."
    summary = read_json(root / "results/pdfocr-paddle-visual-fraktur.json")["summary"]
    assert summary["correct_added_joins"] == 1 and summary["false_added_joins_on_controls"] == 0
    print(
        "Frozen references, primary OCR metrics, book assembly and successful Fraktur source map verified. No inference run."
    )


if __name__ == "__main__":
    main()
