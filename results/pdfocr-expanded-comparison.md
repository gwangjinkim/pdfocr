# Expanded local comparison and pdfrune repair

Checked 2026-10-23 on Apple M3 Max / 128 GiB. All four OCR pipelines completed
16 pages across both Archive.org books (64 page outputs). Twelve adjacent page
boundaries include four split words and eight non-split controls. The pages
cover stained Antiqua, a footnote, dense Fraktur, centered Latin, faded printing,
a chapter opening and prescription lists with apothecary symbols.

A separate native-resolution Fraktur probe adds PDF pages 34–35 for Paddle and
Ovis. It is excluded from the primary OCR scores and kept separate below.

## OCR results

Primary edit rates cover 14 full-page provisional visual transcriptions.
Prescription pages 70–71 are inspected as symbol/structure cases without
inventing a gold transcription for uncertain apothecary glyphs.

| Pipeline | Overall CER | Overall WER | Antiqua CER, 6 pages | Fraktur CER, 8 pages |
|---|---:|---:|---:|---:|
| OvisOCR3 BF16 / MLX | 1.54% | 6.21% | 0.93% | 1.91% |
| GLM-OCR BF16 / MLX | 2.69% | 10.52% | 0.77% | 3.84% |
| PaddleOCR-VL BF16, book assembly | 2.79% | 10.55% | 1.27% | 3.70% |
| PaddleOCR-VL, original assembly | 6.90% | 14.55% | 7.84% | 6.33% |
| TeleOCR Q8 / Rust-Candle Metal | 10.40% | 31.86% | 1.61% | 15.69% |

**Ovis is the strongest OCR candidate on this expanded sample**, especially for
Fraktur. GLM is slightly stronger on the first book's Antiqua prose. This
changes the recommendation from the earlier two-page test. TeleOCR's local Q8
port performs poorly on these Fraktur pages; this is not a claim about every
TeleOCR runtime or its original-precision model.

The Paddle book variant uses exactly the saved real region recognition: it
retains the PDF-12 footnote and suppresses a nearly identical region detected
twice under different labels on the chapter-opening page. No OCR text is
rewritten and no extra inference is needed for that variant. Its improvement
shows why the default Markdown assembly must not be mistaken for intrinsic
recognizer quality. The raw region outputs are retained for review.

## Local visual hyphen recovery

The visual worker uses shared Paddle layout geometry to find the last and first
body regions, then GLM-OCR reads image crops locally. A gate requires adjacency,
a literal hyphen in visual OCR, matching edge words in the page OCR, and Qwen3
approval of a split-word join. It can delete only a source-mapped separator;
it cannot rewrite OCR words or remove arbitrary text. All source spans and
updated output coordinates/hashes are checked.

| Main-sample split-word continuity | Text-only repair | With visual step |
|---|---:|---:|
| Ovis | 0/4 correct | 1/4 correct |
| Paddle | 1/4 correct | 3/4 correct |
| GLM control | 3/4 correct | not needed for this experiment |
| TeleOCR control | 2/4 correct | not tested with visual step |

Three additional joins were applied, all matching the scan: `ansteckenden` for
both Ovis and Paddle, plus `Aufmerksamkeit` for Paddle. No word join was added
on the eight non-split controls tested for each model (16 negative model cases).
These counts are much too small to estimate a production false-join rate.

The footnote boundary remains unresolved. The OCR sometimes completes or
changes the word before reaching the boundary; a separator-only repair cannot
safely fix that. This experiment preserves those failures instead of replacing
prose to make the result look correct.

In the additional Fraktur test, the scan shows `Per-` + `son.` = `Person`.
Paddle dropped the hyphen, but the GLM crop reader misread `son` as `jon`, so the
matching gate correctly deferred rather than forcing a join. Ovis kept the
hyphen but misread the continuation. Therefore visual recovery is demonstrated
for the Antiqua cases, and is **not yet reliable on Fraktur**.

## pdfrune itself is repaired

The actual Rust renderer now handles DCT/JPEG, JPX/JPEG2000, JBIG2 masks,
soft-mask source-over compositing and affine image placement. Invisible OCR
text (`3 Tr`) stays extractable and is no longer painted as black rectangles;
clip-only text is also not painted. Unsupported image streams raise errors
instead of silently disappearing.

The patched source is installed in `vendor-pdfrune` and rebuilt in `.venv`.
All 16 selected pages rendered natively without fallback in separate checks.
14 Rust tests, 33 pdfrune Python tests and 26 harness tests pass. All workspace
bindings compile. Clippy passes with two pre-existing unrelated lints suppressed
for the newer compiler. New codec dependencies are MIT OR Apache-2.0, pure Rust,
and their license texts are included in the wheel. Rust 1.92+ is now required.

The primary OCR comparison retains its frozen, visually verified 200-DPI
PDFium inputs; changing the renderer halfway through the comparison would
change model inputs. The additional 400-DPI Fraktur probe and a GLM smoke run
use the repaired pdfrune renderer strictly, with no fallback. A separate
before/after preview and patch are delivered with this report.

## Interpretation and reproduction

The references are assistant visual transcriptions, not independently adjudicated
human gold. Historical spelling, case, punctuation and readable footnotes count.
Only page furniture, emphasis and internal line-wrap hyphens are normalized.
Formatting differences may still count as edits. The hardest faded text and
proper names deserve human review. This is a useful local diagnostic set, not a
blind benchmark or a universal model ranking.

Both books use the same prepared pixels for every primary model. Their small
physical page size makes 200 DPI a genuine low-resolution challenge for the
Fraktur book. Model-specific resizing, layouts, precision (BF16 vs Q8), port
postprocessing and timing conditions differ; do not read this as a controlled
architecture or throughput comparison. No paid API or inference server was used.

```bash
cd ~/projects/python/pdfocr
uv sync --frozen
uv sync --project runners/mlx --frozen
uv run python scripts/run_expanded.py --phase ocr
uv run python scripts/run_expanded.py --phase repair
uv run python scripts/run_visual_repair.py
uv run python scripts/reassemble_paddle_book.py
uv run python scripts/run_fraktur_hyphen_probe.py
uv run python scripts/build_expanded_report.py
open workspace/expanded/report/comparison.html
```

The frozen sample is in `datasets/expanded/selection.json`, references and
hashes are alongside it, and visually checked boundary labels are in
`datasets/expanded/boundaries.json`. The visual model is not prompted with those
expected labels. The successful run index, raw page JSON, layout crops,
repair decisions, source maps and process records remain under
`workspace/expanded/`. The native Fraktur probe is under
`workspace/fraktur-hyphen-probe/`.
