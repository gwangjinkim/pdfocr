# Reproduce the local experiments

The published results were measured on 2026-10-23. Publication adds portable
paths and acquisition helpers; it does not rerun or rewrite the recorded OCR.
Original and exported source hashes are in `publication-provenance.json`.

## Install and acquire inputs

Follow the root README. Downloading is explicit:

```bash
uv run python scripts/bootstrap_archive.py --download --prepare
```

This selects the exact public files in `datasets/books.json`, checks their
SHA256, and renders the same 200-DPI PDFium inputs used in the baseline. A PDF
with a changed hash is rejected rather than mixed into the old experiment.
The original books are not bundled or relicensed by this repository. Inspect
the page images before inference. Merely being nonblank does not establish
rendering correctness.

## Expanded 200 DPI comparison

```bash
uv run python scripts/run_expanded.py --phase ocr
uv run python scripts/run_expanded.py --phase repair
uv run python scripts/reassemble_paddle_book.py
uv run python scripts/run_visual_repair.py
uv run python scripts/run_fraktur_hyphen_probe.py
uv run python scripts/build_expanded_report.py
```

The supplementary Fraktur probe in this first report is already native 400 DPI;
it is separate from the 16 primary 200-DPI pages and excluded from primary CER.
The earlier two-page smoke-test code is retained in `compare_book.py`.

## Fixed pdfrune at 400 DPI

```bash
uv run python scripts/prepare_400.py
uv run python scripts/run_expanded.py --base workspace/expanded400 --selection datasets/expanded400/selection.json --phase ocr
uv run python scripts/run_400_followup.py
uv run python scripts/build_400_report.py
```

The preparer explicitly permits a 100-million-pixel canvas because the first
book has unusually large page dimensions; the normal library limit stays at
40 million. Inspect the generated contact sheets and source images. Model
resize caps remain fixed, so render DPI is not equivalent to final model input
resolution. Both renderer and DPI change relative to the original baseline.

The follow-up also runs matched native-200/native-400 Fraktur probes and three
separate GLM page29 diagnostics. It retains the original repetition failure.
It never raises token limits until a repeated answer appears to finish.

## Paddle as the Fraktur visual reader

```bash
uv run python scripts/run_paddle_visual.py
uv run python scripts/build_paddle_visual_report.py
```

This replaces the crop reader only: `OCR:` for Paddle versus `Text Recognition:`
for GLM. It checks frozen crop hashes and reuses the same page OCR, adjacency
guard, lexical gate, Qwen3 classifier and separator-only edit policy.

Reports are standalone local HTML, JSON and Markdown, with escaped model text.
No server is needed. Successful inference pages are cached; output directories
are separate for each experiment. New model versions or preprocessing changes
require a new result directory and new comparisons.

## Check the published evidence without inference

```bash
uv run pytest -q
uv run python scripts/verify_published_results.py
```

All CER/WER reference transcriptions are provisional AI-assisted visual reviews,
not independently adjudicated human gold. Historical spelling, case and punctuation count. Long s, page furniture, markup
and internal line-wrap hyphens are normalized as documented in the scoring code. Frozen labels must stay outside training data if used as a
test set for future fine-tuning.

## Gemma follow-up (October 24, 2026)

The [Gemma comparison](gemma-comparison.md) adds the original 2025 script's
multi-image 72-DPI workflow, matched 400-DPI Gemma 3/Gemma 4 runs, a confirmed
1120-image-token control, and both raw and presentation-cleaned boundary
repair. These are new measurements; none replace the frozen October 23
answers above. The historical PyMuPDF dependency stays in its own environment.
