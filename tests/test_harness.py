import json
import os
import sys

import pdfrune
import pytest

from pdfocr.archive import identifier
from pdfocr.pdf import prepare
from pdfocr.report import compare, evaluate
from pdfocr.run import execute, run_model
from pdfocr.util import parse_pages


def test_page_ranges():
    assert parse_pages("3,1-2,2", 4) == [1, 2, 3]
    for invalid in ("0", "5", "3-1"):
        with pytest.raises(ValueError):
            parse_pages(invalid, 4)


def test_archive_identifiers():
    assert identifier("https://archive.org/details/10289757bsb/mode/2up") == "10289757bsb"
    for bad in ("../secret", "https://other.example/details/book", ".."):
        with pytest.raises(ValueError):
            identifier(bad)


def test_actual_pdfrune_prepare_run_evaluation_and_safe_viewer(tmp_path):
    source = tmp_path / "test.pdf"
    with pdfrune.open() as doc:
        page = doc.new_page(width=300, height=300)
        page.insert_text(pdfrune.Point(40, 80), "A readable sentence.", fontsize=16)
        doc.save(str(source))
    folder = tmp_path / "prepared"
    data = prepare(source, folder, None, 100)
    assert data["native_extractor"] == "pdfrune"
    assert "readable" in (folder / data["pages"][0]["native_text"]).read_text()
    run = run_model(folder, "native")
    result = json.loads((run / "manifest.json").read_text())
    assert result["status"] == "complete"
    refs = tmp_path / "refs"
    refs.mkdir()
    prediction = json.loads((run / result["pages"][0]["result"]).read_text())["markdown"]
    (refs / "page-0001.md").write_text(prediction)
    assert evaluate(run, refs)["cer"] == 0
    raw = run / "page-0001.json"
    value = json.loads(raw.read_text())
    value["markdown"] = '<script>alert("untrusted")</script>'
    raw.write_text(json.dumps(value))
    report = compare(folder).read_text()
    assert "&lt;script&gt;" in report
    assert '<script>alert("untrusted")</script>' not in report


def test_timeout_terminates_our_foreground_process(tmp_path):
    info = execute(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        tmp_path / "child.log",
        0.05,
        os.environ.copy(),
    )
    assert info["timed_out"] and info["exited"]
    with pytest.raises(ProcessLookupError):
        os.kill(info["pid"], 0)


def test_remote_upload_requires_explicit_flag(tmp_path):
    folder = tmp_path / "document"
    folder.mkdir()
    (folder / "document.json").write_text(json.dumps({"pages": []}))
    with pytest.raises(ValueError, match="allow-remote"):
        run_model(folder, "glm-ocr", backend="endpoint", endpoint="https://remote.example/v1")


def test_worker_preserves_virtualenv_interpreter_path(tmp_path):
    folder = tmp_path / "document"
    folder.mkdir()
    (folder / "document.json").write_text(json.dumps({"pages": [], "source_sha256": "test"}))
    python = tmp_path / "venv-python"
    python.symlink_to(sys.executable)
    run = run_model(
        folder,
        "glm-ocr",
        backend="endpoint",
        endpoint="http://localhost:1234/v1",
        python=str(python),
    )
    manifest = json.loads((run / "manifest.json").read_text())
    assert manifest["config"]["python"] == str(python)


def test_explicit_render_budget_preserves_default_and_allows_override(tmp_path):
    source = tmp_path / "budget.pdf"
    with pdfrune.open() as doc:
        page = doc.new_page(width=100, height=100)
        page.insert_text(pdfrune.Point(10, 40), "Render budget", fontsize=12)
        doc.save(str(source))
    with pytest.raises(ValueError, match="exceed 5,000 pixels"):
        prepare(source, tmp_path / "limited", None, 72, "pdfrune", max_pixels=5000)
    data = prepare(source, tmp_path / "allowed", None, 72, "pdfrune", max_pixels=20000)
    assert data["max_render_pixels"] == 20000
    assert data["pages"][0]["width"] == 100
    for invalid in (True, 0, 160_000_001):
        with pytest.raises(ValueError, match="max_pixels"):
            prepare(source, tmp_path / "invalid", None, 72, max_pixels=invalid)
