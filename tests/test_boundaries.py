import json
from unittest.mock import Mock

import pytest

from pdfocr.borrowed.archive_stitching import Page, PageStitcher
from pdfocr.stitch import assemble


@pytest.mark.parametrize(
    "left,right,action,expected",
    [
        ("Eine Ent-", "wicklung.", "join_word", "Eine Entwicklung."),
        ("Eine Kosten-", "Nutzen-Analyse.", "keep_hyphen", "Eine Kosten-Nutzen-Analyse."),
        ("Die Regel gilt", "für alle.", "join_space", "Die Regel gilt für alle."),
        ("Alle kamen\n\nzusammen", "zusammen an.", "drop_catchword", "Alle kamen zusammen an."),
    ],
)
def test_borrowed_strategy_preserves_exact_sources(tmp_path, left, right, action, expected):
    backend = Mock(model_name="test")
    backend.extract_text.return_value = json.dumps({"action": action, "reason": "test"})
    raw = tmp_path / "raw.md"
    original = f"## Page 1\n\n{left}\n\n## Page 2\n\n{right}\n"
    raw.write_text(original)
    out = tmp_path / "flow.md"
    PageStitcher(backend).process(raw, out, tmp_path / "audit.jsonl")
    assert out.read_text().strip() == expected
    assert raw.read_text() == original
    mapping = json.loads(out.with_suffix(".pages.json").read_text())
    coverage = []
    for span in mapping["spans"]:
        a, b = span["output_start"], span["output_end"]
        coverage.extend(range(a, b))
        if span["kind"] == "source":
            assert out.read_text()[a:b] == original[span["raw_start"] : span["raw_end"]]
    assert coverage == list(range(len(out.read_text())))


@pytest.mark.parametrize(
    "left,right,action",
    [
        ("Die Haus-", "und Hofordnung", "join_word"),
        ("Ende.", "Neuer Satz.", "join_space"),
        ("| table | cell |", "weiter", "join_space"),
        ("Eine Ent-", "## Anhang", "join_word"),
    ],
)
def test_unsafe_actions_do_not_apply(left, right, action):
    backend = Mock(model_name="test")
    backend.extract_text.return_value = json.dumps({"action": action})
    result = PageStitcher(backend).decide(Page(1, left), Page(2, right))
    assert result["action"] in ("keep", "uncertain")


def test_new_replacement_prose_is_rejected():
    backend = Mock(model_name="test")
    backend.extract_text.return_value = json.dumps(
        {"action": "join_word", "replacement": "invented"}
    )
    assert (
        PageStitcher(backend).decide(Page(1, "Eine Ent-"), Page(2, "wicklung"))["action"]
        == "uncertain"
    )


def test_manual_override_requires_unchanged_source():
    pages = [{"page": 1, "markdown": "Die Ent-"}, {"page": 2, "markdown": "wicklung."}]
    proposed = assemble(pages)
    assert "Entwicklung" not in proposed["markdown"]
    record = proposed["boundaries"][0]
    override = {
        "1-2": {"action": "join", "hyphen": "remove", "boundary_sha256": record["boundary_sha256"]}
    }
    assert "Entwicklung" in assemble(pages, override)["markdown"]
    pages[1]["markdown"] = "wicklungen."
    with pytest.raises(ValueError, match="Stale"):
        assemble(pages, override)


def test_gap_can_never_join():
    pages = [{"page": 1, "markdown": "geht"}, {"page": 3, "markdown": "weiter"}]
    item = assemble(pages)["boundaries"][0]
    with pytest.raises(ValueError, match="nonadjacent"):
        assemble(pages, {"1-3": {"action": "join", "boundary_sha256": item["boundary_sha256"]}})
