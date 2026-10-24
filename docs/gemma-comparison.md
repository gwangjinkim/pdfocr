# Gemma: reproduce the old workflow and the matched comparison

The original article was published on April 6, 2025. These new runs were made
on October 24, 2026, using the same two books, selection and frozen provisional
references as the specialized OCR comparison. They are not archived 2025
measurements. The original article did not pin an Ollama binary, model manifest,
renderer version or random seed; a bit-for-bit reconstruction of its historical
outputs is not possible from that article alone.

## Deliberately distinct arms

- `legacy72`: the author's exact plural-image prompt, PyMuPDF `get_pixmap()`
  without a matrix/DPI argument, RGB PNG images, multiple pages in one user
  message and no generation options. Only JSON transport (`stream=false`) and
  model cleanup (`keep_alive=0`) differ from the original call. The continuous
  excerpts are A9–14, A70–71, B25–30 and B200–201. We do not concatenate disjoint
  page ranges and pretend they are adjacent. The full 93-page/longer books were
  not sent in a single request. Gemma 3:12b is the primary historical baseline.
- `matched400cap2880`: one page/request, exact same repaired-pdfrune 400-DPI
  source image hashes as the specialized comparison, explicit Pillow
  RGB/LANCZOS thumbnail cap of 2880 pixels (the existing Ovis cap), original
  plural-image prompt unchanged, temperature 0, seed 0, context 16384,
  output 8192. Gemma 4 thinking is disabled; Gemma 3 has no thinking mode.
- `budget1120`: same Gemma 4 weights and matched settings; a temporary child
  of the benchmark supervisor runs on loopback 11539 with
  `LLAMA_ARG_IMAGE_MAX_TOKENS=1120`. Logs and prompt token counts must confirm
  the override before the full sample proceeds. It is a diagnostic for the
  installed Ollama 0.30.10, not a benchmark of the newest Ollama release.
- `matched400`: the initial unresized transport diagnostic is retained.
  Six unusually large Antiqua pages exceeded Ollama's request-size limit.
  Those errors are not silently treated as valid empty OCR or ranked scores.

A supplementary B34–35 probe examines the visible `Per-`/`son.` split. It
does not have complete gold pages and stays out of the primary CER/WER.

The optional Gemma 4 default-thinking batch branch was stopped after one
completed A9–14 excerpt. Its incomplete remainder is explicitly excluded from
full-sample scores; it is not a measured model timeout or a full Gemma 4 batch
benchmark.

## Execute explicitly, while the task is active

Install an already-compatible Ollama and start it yourself if it is not already
running. The baseline script never starts/restarts/stops that service. Local
model downloads are explicit and can be several gigabytes:

```bash
uv sync --project runners/legacy --frozen
# Historical renderer is isolated because PyMuPDF is AGPL/commercial.
runners/legacy/.venv/bin/python scripts/gemma_benchmark.py prepare

uv run python scripts/gemma_benchmark.py pull --models gemma3:12b gemma4:12b
uv run python scripts/gemma_benchmark.py run --models gemma3:12b --arms legacy72 matched400cap2880
uv run python scripts/gemma_benchmark.py run --models gemma4:12b --arms matched400cap2880

# Explicitly launches a finite supervised child; not a persistent service.
uv run python scripts/gemma_budget_control.py

uv run python scripts/repair_gemma.py
uv run python scripts/repair_gemma.py --arm budget1120 --models gemma4-12b
uv run python scripts/repair_gemma.py --normalize-format
uv run python scripts/repair_gemma.py --arm budget1120 --models gemma4-12b --normalize-format
uv run python scripts/build_gemma_report.py

# Check the published evidence without inference or Ollama.
uv run python scripts/verify_gemma_results.py
```

Prepare400 and the supplementary probes first, as described in `reproduce.md`.
For an existing lab in another directory, `prepare` and `repair_gemma.py` accept
`--source-root`. The measurements reused the author's original cached inputs,
model pins and MLX interpreter; they did not rerender the matched pages.

Ollama tags are mutable. Preserve the manifest digests in the published
provenance. Do not silently mix different weights or a newer runtime with
cached answers. A changed tag requires a fresh experiment directory. A future
download may resolve to different weights; record it as a new experiment,
rather than claiming exact replication. Keep all inference on loopback and
avoid cloud model tags. Root dependencies do not include PyMuPDF.

## Interpretation

Matched metrics sum edits independently across the same 14 reference pages,
using the unchanged existing normalization. Batch metrics compare a whole
contiguous excerpt with concatenated references; they cannot provide an
independently measured per-page score or a source-page map. These two score
types are reported separately. Latin prescription pages remain qualitative.
Returned-output scores keep model commentary and outer code fences. A separate
assembly variant removes only a single outer Markdown fence and leading
page-number metadata, retaining one exact contiguous body-text interval per
page. No letters are corrected. Raw and cleaned CER/WER and repair results
are both reported. The same pass was checked against all 144 archived
specialized-model page answers and changed none of their content-normalized
texts; their published metrics stay unchanged. Finishing with `done_reason=stop` does not prove all text was read.

Repair uses the unchanged Qwen3-1.7B classifier and exact character-source
guards. It never receives reference labels. The primary set contains four
split words (all Antiqua) and eight non-split controls; the Fraktur positive
is supplementary. All source spans are verified against the raw OCR.

The checkpoints differ in architecture, quantization and visual preprocessing;
specialized OCR results use BF16 or the documented TeleOCR Q8 port. Treat this
as measured local stack behavior, not intrinsic model superiority or a
controlled throughput benchmark. Runs overlapped on this workstation, so
observed wall times are not a valid speed ranking.

Relevant upstream evidence:

- [Ollama image-token-budget issue and maintainer discussion](https://github.com/ollama/ollama/issues/15626)
- [Google's visual-token-budget documentation](https://ai.google.dev/gemma/docs/capabilities/vision/image)
- [Gemma 4 model card and Apache-2.0 license](https://ai.google.dev/gemma/docs/core/model_card_4)
- [Gemma 4 12B architecture and release](https://developers.googleblog.com/gemma-4-12b-the-developer-guide/)

Zero false joins on non-split controls is not the same as zero incorrect word
reconstructions. A correctly detected split can still produce a wrong word
if OCR supplied the wrong letters or already completed the left stem. The
report separately counts wrong reconstructions on positive cases and the
Fraktur probe; do not conceal these behind the negative-control rate.
