"""Finite Gemma3 overview+4-band experiment; existing local Ollama only."""

import argparse
import os
import sys
import time
from pathlib import Path

import gemma_benchmark as bench
import httpx

from pdfocr.gemma_tiles import TILE_PROMPT, make_views

BASE = bench.ROOT / "workspace/gemma3-tiles"
MODEL = "gemma3:12b"


def run(dpis):
    baseline = bench.read(bench.ROOT / "results/gemma/model-provenance.json")
    bench.PROMPT = TILE_PROMPT
    with httpx.Client(base_url="http://127.0.0.1:11434", trust_env=False, timeout=30) as client:
        meta = bench.metadata(client, [MODEL])
        assert meta["ollama"] == baseline["ollama"], "Runtime changed"
        assert meta["models"][MODEL]["tag"]["digest"] == baseline["models"][MODEL]["tag"]["digest"]
        bench.save(BASE / "model-provenance.json", meta)
        for dpi in dpis:
            exp = bench.ROOT / "workspace" / ("gemma200" if dpi == 200 else "gemma")
            pages = [p for p in bench.read(exp / "inputs.json")["pages"] if p["dpi"] == dpi]
            assert len(pages) == 18
            controls = [("10289757bsb", 9), ("makrobiotikoderd00hufeuoft", 26)]
            pages.sort(
                key=lambda p: (0 if (p["book"], p["page"]) in controls else 1, p["book"], p["page"])
            )
            runbase = BASE / f"dpi{dpi}"
            inputs = []
            for p in pages:
                bid, number = p["book"], p["page"]
                source = Path(p["image"])
                if not source.is_absolute():
                    source = bench.ROOT / source
                assert bench.digest(source) == p["sha256"], "Frozen source pixels changed"
                overview = bench.capped_image(
                    source, bid, number, base=exp, cache_name=f"inputs{dpi}cap2880"
                )
                views = make_views(overview, runbase / "views" / bid / f"page-{number:04d}")
                group = "probe" if number in [34, 35] else bid
                target = runbase / "tiles4/gemma3-12b" / group / f"page-{number:04d}.json"
                images = [Path(v["path"]) for v in views["views"]]
                control = None
                if (bid, number) in controls:
                    control = runbase / "overview-control/gemma3-12b" / group / target.name
                    bench.infer(
                        client,
                        MODEL,
                        images[:1],
                        control,
                        f"matched{dpi}-overview-control",
                        [number],
                        bid,
                    )
                    assert bench.read(control)["status"] == "ok"
                bench.infer(client, MODEL, images, target, f"matched{dpi}-tiles4", [number], bid)
                result = bench.read(target)
                assert result["status"] == "ok", target
                assert len(result["request_without_image_bytes"]["messages"][0]["images"]) == 5
                assert [v["sha256"] for v in views["views"]] == [
                    v["sha256"]
                    for v in result["request_without_image_bytes"]["messages"][0]["images"]
                ]
                tokens = result["response"].get("prompt_eval_count", 0)
                assert tokens >= 5 * 256, "Additional visual views not confirmed"
                if control:
                    control_tokens = bench.read(control)["response"]["prompt_eval_count"]
                    assert tokens - control_tokens >= 4 * 256, (
                        "Extra views not reflected in token count"
                    )
                    views["same_prompt_overview_control"] = {
                        "path": str(control),
                        "prompt_tokens": control_tokens,
                        "tiled_prompt_tokens": tokens,
                        "extra_prompt_tokens": tokens - control_tokens,
                    }
                inputs.append(
                    {
                        **p,
                        "capped_overview_sha256": bench.digest(overview),
                        "tiling": views,
                        "prompt_eval_count": tokens,
                    }
                )
                bench.save(
                    runbase / "inputs.json",
                    {
                        "dpi": dpi,
                        "pages": inputs,
                        "method": "Same frozen capped pixels; overview plus four overlapping horizontal bands. Explicit tiling, not native pan-and-scan. Tile-specific instruction differs from historical prompt; two same-prompt overview controls per DPI.",
                        "prompt": TILE_PROMPT,
                        "complete": len(inputs) == 18,
                    },
                )
                print("Verified five visual views", dpi, bid, number, tokens, flush=True)
        # Do not manage the user's Ollama daemon. Each request has keep_alive=0.
        bench.save(
            BASE / "loaded-models-at-end.json", client.get("/api/ps").raise_for_status().json()
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dpi", nargs="+", type=int, choices=[200, 400], default=[200, 400])
    args = parser.parse_args()
    BASE.mkdir(parents=True, exist_ok=True)
    lock = BASE / ".running"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, f"pid={os.getpid()} started={time.time()}\n".encode())
    os.close(fd)
    process = {
        "pid": os.getpid(),
        "started_at_unix": time.time(),
        "argv": sys.argv,
        "exited": False,
    }
    record = BASE / f"process-{os.getpid()}.json"
    bench.save(record, process)
    try:
        run(args.dpi)
    except BaseException:
        process["returncode"] = 1
        raise
    else:
        process["returncode"] = 0
    finally:
        process.update(exited=True, seconds=time.time() - process["started_at_unix"])
        bench.save(record, process)
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
