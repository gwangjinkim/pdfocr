import json

from pdfocr.repair import DecisionBackend, export_raw_pages


def test_repair_raw_preserves_error_and_gap(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "page-0001.json").write_text(json.dumps({"page": 1, "markdown": "Ent-", "status": "ok"}))
    (run / "page-0003.json").write_text(
        json.dumps({"page": 3, "markdown": "wicklung.", "status": "error"})
    )
    (run / "manifest.json").write_text(
        json.dumps(
            {
                "pages": [
                    {"page": 1, "status": "ok", "result": "page-0001.json"},
                    {"page": 3, "status": "error", "result": "page-0003.json"},
                ]
            }
        )
    )
    raw = export_raw_pages(run, tmp_path / "raw.md")
    assert "## Page 3 (Error)" in raw.read_text()


def test_backend_never_starts_ollama_and_rejects_cloud():
    import pytest

    with pytest.raises(ValueError):
        DecisionBackend("gemma4:cloud", "http://127.0.0.1:11434")
    with pytest.raises(ValueError):
        DecisionBackend("local", "https://remote.example")
