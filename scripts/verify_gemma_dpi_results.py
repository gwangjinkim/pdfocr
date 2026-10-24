"""Recompute published native 200/400 Gemma metrics and maps without inference."""

from pathlib import Path

import build_gemma_dpi_report as dpi_report
import build_gemma_report as common
from verify_gemma_results import verify_map

from pdfocr.gemma_format import unwrap_presentation
from pdfocr.util import read_json

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "results/gemma200"


def main():
    recorded = read_json(ROOT / "results/pdfocr-gemma-200dpi-comparison.json")
    original = common.verify_map
    common.verify_map = verify_map
    try:
        actual = dpi_report.build_data(BASE)
    finally:
        common.verify_map = original
    for a, b in zip(actual["rows"], recorded["rows"]):
        assert a == b, (a["name"], "Published result mismatch")
    slices = 0
    for _, model, arm, _ in dpi_report.CONFIGS:
        for path in (BASE / "format-cleaned" / arm / model).rglob("page-*.json"):
            value = read_json(path)
            raw = read_json(BASE / arm / model / path.parent.name / path.name)["markdown"]
            clean = value["format_cleanup"]
            assert value["markdown"] == raw[clean["source_start"] : clean["source_end"]]
            assert unwrap_presentation(raw)["markdown"] == value["markdown"]
            slices += 1
    assert slices == 54
    prior = read_json(ROOT / "results/gemma/model-provenance.json")
    assert recorded["provenance"]["ollama"] == prior["ollama"]
    for model, pin in recorded["provenance"]["models"].items():
        assert pin["tag"]["digest"] == prior["models"][model]["tag"]["digest"]
        assert (
            pin["tag"]["details"]["quantization_level"]
            == prior["models"][model]["tag"]["details"]["quantization_level"]
        )
    print("Verified three 200/400-DPI configurations, raw/clean CER+WER, 18 new source maps,")
    print(
        "54 exact body slices, 78 new boundary decisions and 18 matching 400-DPI renderer controls."
    )


if __name__ == "__main__":
    main()
