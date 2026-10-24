"""Finite local Gemma4 image-budget control; temporary child service, always reaped.

Does not modify/restart the user's existing Ollama service. Reuses its local
weights, uses a private loopback port, and records child ownership/lifetime.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

import gemma_benchmark as bench
import httpx


def main():
    base = bench.BASE / "budget1120"
    base.mkdir(parents=True, exist_ok=True)
    port = 11539
    endpoint = f"http://127.0.0.1:{port}"
    with httpx.Client(trust_env=False, timeout=1) as client:
        try:
            client.get(endpoint + "/api/version")
        except httpx.ConnectError:
            pass
        else:
            raise RuntimeError("Private experiment port already occupied; refusing duplicate")
    executable = shutil.which("ollama")
    if executable is None:
        raise RuntimeError("Install Ollama before this explicit local control")
    command = [executable, "serve"]
    env = {
        **os.environ,
        "OLLAMA_HOST": f"127.0.0.1:{port}",
        "LLAMA_ARG_IMAGE_MAX_TOKENS": "1120",
        "OLLAMA_NO_CLOUD": "1",
        "OLLAMA_KEEP_ALIVE": "0",
        "OLLAMA_MAX_LOADED_MODELS": "1",
    }
    details = {
        "purpose": "Gemma4 OCR image-token-budget control",
        "owner_pid": os.getpid(),
        "started_at_unix": time.time(),
        "command": command,
        "endpoint": endpoint,
        "image_max_tokens_environment": 1120,
        "lifetime": "Only this finite benchmark; finally unload, terminate and wait",
        "log": str(base / "server.log"),
        "exited": False,
    }
    proc = None
    with (base / "server.log").open("a") as log:
        try:
            proc = subprocess.Popen(
                command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
            )
            details["pid"] = proc.pid
            bench.save(base / "service-process.json", details)
            with httpx.Client(base_url=endpoint, trust_env=False, timeout=30) as client:
                for _ in range(100):
                    if proc.poll() is not None:
                        raise RuntimeError("Temporary Ollama exited during startup")
                    try:
                        client.get("/api/version", timeout=1).raise_for_status()
                        break
                    except (httpx.ConnectError, httpx.ReadTimeout):
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Temporary Ollama startup timed out")
                bench.save(base / "model-provenance.json", bench.metadata(client, ["gemma4:12b"]))
                inputs = bench.read(bench.BASE / "inputs.json")["pages"]
                # One Antiqua and one dense Fraktur control first. The following full
                # sample is conditional on evidence the larger budget actually applied.
                cases = [("10289757bsb", 9), ("makrobiotikoderd00hufeuoft", 26)]
                cases += [
                    (bid, n)
                    for bid, numbers in bench.BOOKS.items()
                    for n in numbers
                    if (bid, n) not in cases
                ]
                cases += [("makrobiotikoderd00hufeuoft", n) for n in [34, 35]]
                for i, (bid, number) in enumerate(cases):
                    p = next(
                        p
                        for p in inputs
                        if p["book"] == bid and p["page"] == number and p["dpi"] == 400
                    )
                    image = bench.capped_image(Path(p["image"]), bid, number)
                    group = "probe" if number in [34, 35] else bid
                    target = base / "gemma4-12b" / group / f"page-{number:04d}.json"
                    bench.infer(
                        client, "gemma4:12b", [image], target, "matched400budget1120", [number], bid
                    )
                    result = bench.read(target)
                    if result["status"] != "ok":
                        raise RuntimeError(f"Image budget control failed: {target}")
                    if i == 0:
                        log_text = (base / "server.log").read_text(errors="replace")
                        tokens = result["response"].get("prompt_eval_count", 0)
                        evidence = {
                            "prompt_eval_count": tokens,
                            "expected_image_max_pixels": 2_580_480,
                            "server_log_mentions_2580480": "2580480" in log_text,
                        }
                        bench.save(base / "budget-evidence.json", evidence)
                        if tokens < 900 or "2580480" not in log_text:
                            raise RuntimeError(
                                "1120-token override not confirmed; no quality ranking"
                            )
                # Explicit unload, even if the final request hit an error.
                client.post(
                    "/api/generate", json={"model": "gemma4:12b", "keep_alive": 0}
                ).raise_for_status()
                details["loaded_models_after_unload"] = (
                    client.get("/api/ps").raise_for_status().json()
                )
        except BaseException:
            details["returncode"] = 1
            raise
        else:
            details["returncode"] = 0
        finally:
            if proc is not None:
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=5)
                # The group was created by this supervisor. Reap any surviving
                # runner as well, without a process-name search or touching 11434.
                try:
                    os.killpg(proc.pid, 0)
                except ProcessLookupError:
                    details["process_group_gone"] = True
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
                    for _ in range(50):
                        try:
                            os.killpg(proc.pid, 0)
                        except ProcessLookupError:
                            details["process_group_gone"] = True
                            break
                        time.sleep(0.1)
                details.update(
                    exited=proc.poll() is not None,
                    server_returncode=proc.returncode,
                    seconds=time.time() - details["started_at_unix"],
                )
                bench.save(base / "service-process.json", details)
                print("Temporary OCR service exited", proc.pid, proc.returncode, flush=True)


if __name__ == "__main__":
    main()
