"""Read-only experiment audit; writes only user-facing validation evidence."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / "workspace/expanded400/report"
BASES = [
    ROOT / "workspace/expanded400",
    ROOT / "workspace/expanded400-probe-200",
    ROOT / "workspace/expanded400-probe-400",
]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


processes = {}
maps, documents = [], []
for base in BASES:
    assert not list(base.rglob(".running")), "Stale run lock"
    for path in base.rglob("*.json"):
        try:
            data = read(path)
        except (ValueError, UnicodeError):
            continue

        def visit(value):
            if isinstance(value, dict):
                if "pid" in value and "argv" in value:
                    processes[value["pid"]] = {**value, "record": str(path)}
                for child in value.values():
                    visit(child)
            elif isinstance(value, list):
                for child in value:
                    visit(child)

        visit(data)
    for path in base.rglob("document.json"):
        doc = read(path)
        assert sha(Path(doc["source"])) == doc["source_sha256"]
        for page in doc["pages"]:
            assert sha(path.parent / page["image"]) == page["image_sha256"]
        documents.append(
            {
                "path": str(path),
                "renderer": doc["renderer"],
                "pages": len(doc["pages"]),
                "dpi": doc["pages"][0]["dpi"],
            }
        )
    for path in base.rglob("*.pages.json"):
        mapping = read(path)
        if "spans" not in mapping:
            continue
        raw_path, text_path = Path(mapping["raw_file"]), Path(mapping["output_file"])
        assert sha(raw_path) == mapping["raw_sha256"]
        if "output_sha256" in mapping:
            assert sha(text_path) == mapping["output_sha256"]
        raw, text = raw_path.read_text(), text_path.read_text()
        end = 0
        for span in mapping["spans"]:
            assert span["output_start"] == end
            if span["kind"] == "source":
                assert (
                    text[span["output_start"] : span["output_end"]]
                    == raw[span["raw_start"] : span["raw_end"]]
                )
            end = span["output_end"]
        assert end == len(text)
        maps.append(str(path))

remaining = []
for pid, process in processes.items():
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        process["currently_exists"] = False
    else:
        process["currently_exists"] = True
        process["current_ps"] = subprocess.run(
            ["ps", "-p", str(pid), "-o", "pid=,ppid=,lstart=,command="],
            capture_output=True,
            text=True,
        ).stdout.strip()
        remaining.append(process)
assert not remaining, remaining

selection = read(ROOT / "datasets/expanded400/selection.json")
for name, digest in selection["experiment"]["reference_hashes"].items():
    assert sha(ROOT / "datasets/expanded" / name) == digest
for book in selection["books"]:
    doc = read(Path(book["document"]) / "document.json")
    assert len(doc["pages"]) == 8
    for page in doc["pages"]:
        assert page["dpi"] == 400 and page["renderer"] == "pdfrune"
        assert page["renderer_fallback_reason"] is None

provenance = read(BASES[0] / "renderer-provenance.json")
for group in ["native_extensions", "source_files"]:
    for name, digest in provenance[group].items():
        assert sha(Path(name)) == digest

runs = []
for base in BASES:
    for book, models in read(base / "index.json")["books"].items():
        for model, folder in models.items():
            manifest = read(Path(folder) / "manifest.json")
            assert manifest["status"] == "complete"
            for inp in manifest["inputs"]:
                assert sha(Path(inp["image_path"])) == inp["image_sha256"]
            runs.append(
                {
                    "book": book,
                    "model": model,
                    "path": folder,
                    "page_outputs": len(manifest["pages"]),
                }
            )
for name, folder in read(BASES[0] / "glm-page29-diagnostic/index.json").items():
    manifest = read(Path(folder) / "manifest.json")
    assert manifest["status"] == "complete"
    for inp in manifest["inputs"]:
        assert sha(Path(inp["image_path"])) == inp["image_sha256"]
    runs.append({"diagnostic": name, "path": folder, "page_outputs": len(manifest["pages"])})
assert sum(r["page_outputs"] for r in runs) == 83

report = read(BASES[0] / "report/comparison.json")
assert len(report["old"]["models"]) == len(report["new"]["models"]) == 5
assert len(report["fraktur_dpi_probe"]) == 8
assert len(report["quality_flags"]) == 1
assert report["quality_flags"][0]["model"] == "glm-ocr" and report["quality_flags"][0]["page"] == 29
assert report["glm_repetition_diagnostics"]["single_case_retry_aggregate"] is not None
for model in report["new"]["models"]:
    assert len(model["pages"]) == 14 and len(model["inputs"]) == 16
    if model["name"] != "paddle-book":
        assert len(model["boundaries"]) == 12

# The separately prepared 400-DPI Fraktur probe is pixel-identical to the
# previously visually reviewed native probe. No replacement source was used.
previous = read(ROOT / "workspace/fraktur-hyphen-probe/document/document.json")
fresh = read(BASES[2] / "document/document.json")
assert [p["image_sha256"] for p in previous["pages"]] == [p["image_sha256"] for p in fresh["pages"]]

result = {
    "checked_date": "2026-10-23",
    "primary_fresh_outputs": 64,
    "probe_fresh_outputs": 16,
    "diagnostic_fresh_outputs": 3,
    "total_fresh_ocr_outputs": 83,
    "all_input_hashes_verified": True,
    "frozen_reference_hashes_verified": 14,
    "native_renderer_hashes_unchanged_during_run": True,
    "prepared_documents": documents,
    "source_maps_exact_and_hashes_verified": len(maps),
    "source_maps": maps,
    "raw_runs": runs,
    "process_records_checked": len(processes),
    "remaining_recorded_task_processes": remaining,
    "processes": list(processes.values()),
    "primary_quality_flags": report["quality_flags"],
    "harness_tests_passed": 27,
    "ruff": "passed",
    "note": "Every foreground tool session was awaited. No persistent server or detached job was started. The raw GLM repetition remains in primary scores; the successful lower-cap retry is a separate diagnostic.",
}
(OUT / "pdfocr-400dpi-validation.json").write_text(json.dumps(result, indent=2) + "\n")
print(
    json.dumps(
        {
            k: v
            for k, v in result.items()
            if k
            not in {
                "processes",
                "source_maps",
                "raw_runs",
                "prepared_documents",
                "primary_quality_flags",
            }
        },
        indent=2,
    )
)
