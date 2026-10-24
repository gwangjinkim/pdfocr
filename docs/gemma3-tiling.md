# Gemma 3 with verified explicit tiling

This experiment uses the same 18 native-pdfrune pages at each of 200 and 400
DPI, including the two supplementary Fraktur boundary pages. The original
capped RGB images are unchanged. Each request sends a page overview followed
by four full-width horizontal bands, ordered top to bottom, with 2% page-height
overlap on each side of internal cuts. Crops are not externally upscaled.

This is explicit tiling, **not native Gemma pan-and-scan**. The instruction
explains that the five images depict one page and requests one transcription.
It also asks for literal page-edge fragments. Thus comparison with the frozen
baseline includes a prompt change; it is not a full-sample crop-only ablation.
Two same-prompt, overview-only controls per DPI help distinguish that issue.

The model digest, Q4_K_M weights, Ollama 0.30.10, temperature 0, seed 0,
context 16384 and output ceiling 8192 match the previous Gemma 3 experiment.
Frozen sources and capped parent hashes are checked before inference. All band
pixels must exactly match their recorded source rectangles, with complete page
coverage. All five submitted image hashes are retained. At least 1280 prompt
tokens are required for each five-view request; the four overview controls must
show at least 1024 fewer tokens with the same text prompt. An unverified view
increase aborts the run rather than being ranked as a tiling result.

First reproduce the prior [200/400 inputs](gemma-200dpi.md). With the existing
local Ollama service available and the exact model already downloaded:

```bash
uv run python scripts/run_gemma3_tiles.py
```

This starts no server and downloads no models. Each request has keep_alive=0.
The finite foreground runner records PID, start, command and exit. Successful
outputs resume from their separate cache; previous experiments stay intact.

Run the same local Qwen3 classifier, once on raw answers and once after the
unchanged presentation-only cleanup:

```bash
uv run python scripts/repair_gemma.py --base workspace/gemma3-tiles/dpi200 --arm tiles4 --models gemma3-12b
uv run python scripts/repair_gemma.py --base workspace/gemma3-tiles/dpi200 --arm tiles4 --models gemma3-12b --normalize-format
uv run python scripts/repair_gemma.py --base workspace/gemma3-tiles/dpi400 --arm tiles4 --models gemma3-12b
uv run python scripts/repair_gemma.py --base workspace/gemma3-tiles/dpi400 --arm tiles4 --models gemma3-12b --normalize-format
uv run python scripts/build_gemma3_tile_report.py --outputs workspace/gemma3-tiles/report
```

The repair script accepts `--source-root` for an existing model cache and MLX
interpreter. Fourteen frozen provisional AI-assisted references are scored;
the prescription pages remain qualitative. Four primary positive boundaries
are Antiqua, eight are non-split controls, and Fraktur has one supplementary
positive. Wrong reconstructed words are counted separately from false joins
on negative controls. All source maps and presentation slices are verified.

Published evidence can be checked without inference:

```bash
uv run python scripts/build_gemma3_tile_report.py --verify-published --outputs results
```

These are single-run local stack comparisons, not independent human gold or
a controlled throughput benchmark. Extra views increase computation. The
same-prompt overview controls cover only four requests in total.
