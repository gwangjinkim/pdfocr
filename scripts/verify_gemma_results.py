"""Recompute published Gemma scores/source maps without models or a server."""

from pathlib import Path

import build_gemma_report as report

from pdfocr.book_compare import content_text
from pdfocr.gemma_format import unwrap_presentation
from pdfocr.util import read_json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/gemma"


def verify_map(path):
    mapping = read_json(path.with_suffix(".pages.json"))
    text = path.read_text()
    raw = path.with_suffix(".raw.md").read_text()
    cursor = 0
    for span in mapping["spans"]:
        assert cursor == span["output_start"]
        if span["kind"] == "source":
            assert (
                text[span["output_start"] : span["output_end"]]
                == raw[span["raw_start"] : span["raw_end"]]
            )
        cursor = span["output_end"]
    assert cursor == len(text)
    return text, mapping


def main():
    recorded = read_json(ROOT / "results/pdfocr-gemma-comparison.json")
    fields = [
        "character_edits",
        "reference_characters",
        "word_edits",
        "reference_words",
        "cer",
        "wer",
        "books",
    ]
    for key, prefix in [("matched", BASE), ("matched_format_cleaned", BASE / "format-cleaned")]:
        for expected in recorded[key]:
            actual = report.score_matched(prefix / expected["arm"], expected["model"])
            assert all(actual[f] == expected[f] for f in fields), (key, expected["model"])
    actual = report.score_legacy(BASE / "legacy72", "gemma3-12b")
    assert all(actual[f] == recorded["legacy"][0][f] for f in fields)
    for arm, model in [("matched400cap2880", m) for m in report.MODELS] + [
        ("budget1120", "gemma4-12b")
    ]:
        for path in (BASE / "format-cleaned" / arm / model).rglob("page-*.json"):
            value = read_json(path)
            original = read_json(BASE / arm / model / path.parent.name / path.name)["markdown"]
            cleanup = value["format_cleanup"]
            assert value["markdown"] == original[cleanup["source_start"] : cleanup["source_end"]]
            assert unwrap_presentation(original)["markdown"] == value["markdown"]
    report.BASE = BASE
    report.verify_map = verify_map
    labels = read_json(ROOT / "datasets/expanded/boundaries.json")
    labels.append(
        {
            "book": "probe",
            "left_page": 34,
            "right_page": 35,
            "expected_action": "join_word",
            "expected_join": "Person",
        }
    )
    for expected in recorded["boundary_repair"]:
        actual = report.boundaries(expected["model"], labels, expected["arm"], expected["variant"])
        assert actual == expected
    old_pages = list((ROOT / "results/raw-pages").glob("*/*/*/page-*.json"))
    assert len(old_pages) == 144
    for path in old_pages:
        text = read_json(path)["markdown"]
        assert content_text(text) == content_text(unwrap_presentation(text)["markdown"])
    assert recorded["temporary_service"]["exited"]
    assert recorded["temporary_service"]["loaded_models_after_unload"] == {"models": []}
    print("Verified: raw/cleaned Gemma CER+WER, historical batch scores, 18 exact source maps,")
    print("54 page-body slices, all boundary outcomes, unchanged 144 specialized-model answers.")


if __name__ == "__main__":
    main()
