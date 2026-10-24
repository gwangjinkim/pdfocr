"""Protect the pixels and failure evidence used for the historical comparison."""

import importlib.util
from pathlib import Path

import httpx
import pytest
from PIL import Image


def runner():
    path = Path(__file__).parents[1] / "scripts/gemma_benchmark.py"
    spec = importlib.util.spec_from_file_location("gemma_benchmark_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cached_pixels_must_not_silently_change(tmp_path, monkeypatch):
    module = runner()
    monkeypatch.setattr(module, "BASE", tmp_path / "experiment")
    source = tmp_path / "page.png"
    Image.new("RGB", (100, 200), "white").save(source)
    original = source.read_bytes()
    cached = module.capped_image(source, "book", 1)
    assert source.read_bytes() == original
    Image.new("RGB", (100, 200), "black").save(cached)
    with pytest.raises(AssertionError):
        module.capped_image(source, "book", 1)


def test_original_batch_preserves_defaults_and_records_transport_failure(tmp_path, monkeypatch):
    module = runner()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    images = [tmp_path / "a.png", tmp_path / "b.png"]
    for image in images:
        Image.new("RGB", (20, 30), "white").save(image)
    calls = []

    def reject(request):
        import json

        calls.append(json.loads(request.content))
        return httpx.Response(413, json={"error": "request too large"})

    with httpx.Client(
        base_url="http://127.0.0.1:11434", transport=httpx.MockTransport(reject)
    ) as client:
        result = tmp_path / "output.json"
        module.infer(client, "gemma3:12b", images, result, "legacy72", [1, 2], "book")
    payload = calls[0]
    assert "options" not in payload and "think" not in payload
    assert payload["messages"][0]["content"] == module.PROMPT
    assert len(payload["messages"][0]["images"]) == 2
    assert payload["keep_alive"] == 0
    value = module.read(result)
    assert value["status"] == "error" and "413" in value["error"]
    assert "markdown" not in value  # Never disguise a transport failure as empty OCR.


def test_200dpi_arm_keeps_the_400dpi_generation_controls(tmp_path, monkeypatch):
    module = runner()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    image = tmp_path / "page.png"
    Image.new("RGB", (20, 30), "white").save(image)
    calls = []

    def respond(request):
        import json

        calls.append(json.loads(request.content))
        return httpx.Response(
            200, json={"message": {"content": "transcribed"}, "done_reason": "stop"}
        )

    with httpx.Client(
        base_url="http://127.0.0.1:11434", transport=httpx.MockTransport(respond)
    ) as client:
        for arm in ["matched200cap2880", "matched400cap2880"]:
            module.infer(
                client, "gemma4:12b", [image], tmp_path / (arm + ".json"), arm, [1], "book"
            )
    assert calls[0] == calls[1]
    assert calls[0]["options"] == {
        "temperature": 0,
        "seed": 0,
        "num_ctx": 16384,
        "num_predict": 8192,
    }
    assert calls[0]["think"] is False
