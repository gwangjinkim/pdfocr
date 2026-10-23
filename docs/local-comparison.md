# Actual local OCR and page-break comparison

Checked 2026-10-23 on Apple M3 Max, 128 GiB RAM. All three requested models
completed real local inference. No remote inference API or background server
was used. Both the setup script and the end-to-end comparison script ran.

## Measured result

Archive.org `10289757bsb`, PDF pages 9–10, printed pages 5–6. These are stained
historical German Antiqua prose scans, not a representative Fraktur test set.
Source PDF SHA-256:
`9a79e4af196f5d980552f8e5aa345bcff494fe603323105824fdfa4548a56cc1`.

| Model/runtime | Content CER ↓ | Content WER ↓ | Two-page inference* | Correct page-break word? |
|---|---:|---:|---:|---|
| GLM-OCR BF16 / MLX, control | 0.75% | 3.28% | 8.6 s | Yes |
| PaddleOCR-VL-1.6 BF16 / layout + MLX | 0.75% | 4.26% | 8.8 s | No |
| OvisOCR3 BF16 / MLX | 0.80% | 4.26% | 8.1 s | No |
| TeleOCR Q8 / Rust-Candle Metal | 1.03% | 4.92% | 32.9 s | Yes |

**My provisional choice for this book is GLM-OCR:** tied with Paddle on
character edits, fewer word edits, and successful boundary repair. Among the
three requested alternatives, Paddle narrowly leads character accuracy;
TeleOCR preserves the critical page-break evidence. The differences are small
and the sample tiny; none establishes a universal winner.

*Inference includes layout/cropping for Paddle and TeleOCR. TeleOCR's CLI also
loads its model separately for each page. Worker wall times including imports
and loads were approximately 12.1 / 12.7 / 11.6 / 33.0 seconds respectively.
These are observed timings, not controlled throughput benchmarks. First-pass
warmup, caching, processor implementations and occasional overlapping setup
work affect comparisons. Models use the same prepared source pixels with
profile resizing (GLM 2048, Ovis 2880, Paddle/Tele 4096 longest edge).

## The page break reveals a real failure

The scan ends PDF 9 with `anstecken-`; PDF 10 begins `den`. Correct continuous
text is `ansteckenden`.

- GLM and TeleOCR kept the hyphen; the same pinned Qwen3-1.7B-4bit boundary-v4
  worker chose `join_word`, producing the correct word.
- Ovis and Paddle dropped the hyphen. The same worker chose `join_space`,
  producing `anstecken den`. Its generated explanations were confused; they
  are retained in the report. A small model's fluent reason is not evidence.

Do not allow unrestricted prose rewriting to conceal this loss. Preserve raw
pages, source images, edge crops/regions and the boundary review. Missing-hyphen
cases need source-backed review or a separately evaluated visual boundary
stage. The current guarded repair does not automatically recover this case.
Only one real inter-page join was tested here; this is not a false-join-rate
estimate. The inherited 22-case regression result is a different evaluation.

## What is actually running

- **OvisOCR3:** original BF16 weights, official document-Markdown prompt,
  MLX-VLM 0.7.10. The separate cross-page table/structured modes are untested.
- **Paddle:** PP-DocLayoutV3 Torch CPU layout and reading order, original BF16
  PaddleOCR-VL-1.6 region recognition in MLX, saved crop images, raw block text
  and simple Markdown assembly. A missing batch dimension in the processor /
  MLX interface is repaired without changing pixel values or weights. This
  adapter uses rectangular crops, duplicate suppression and default furniture
  exclusions. It does not claim complete PaddleX postprocessing/benchmark
  parity on every document type.
- **TeleOCR:** teleocr-rs commit
  `957cdbabe80e86d652c5fcc938ed7fbcf1eb2bbe`, text+vision Q8 GGUF, layout pass,
  region recognition and port postprocessing, built with Rust 1.99.0. The
  upstream CLI's Metal build still selected CPU; the recorded patch explicitly
  selects Metal. Logs confirm `Metal(...)`. The supplied 65-token text and
  282-token table reference examples match exactly. Some title, figure-crop
  and LaTeX features are absent from this community port. Q8 vs BF16 and
  different pipelines are part of this practical local comparison.
- **GLM control:** BF16 full-page recognition, not its official layout pipeline.

A CPU TeleOCR run also completed both pages (roughly 270 seconds total). It
was retained for diagnosis but the table uses the working Metal implementation.
Metal and CPU output differed by a character in page 9; do not assume numerical
parity on arbitrary documents.

## Reference and repeatability limits

References are provisional assistant visual transcriptions, with documented
corrections to the reused page-9 reference, not independent human gold. Content
scores remove printed page-number-only lines, Markdown emphasis and within-page
line hyphenation, normalize NFC/whitespace and retain historical spelling,
case and punctuation. Strict raw CER/WER remain available via `pdfocr evaluate`.
Source-map checks confirm repaired output spans match the raw page text exactly.

All three requested models produced identical text across two complete local
runs. The older GLM run differed in one word from the final run (including
`ArmendiRECTORium` in the final output); its content CER changed from 0.52% to
0.75%. The table reports the final end-to-end run, not the better earlier run.
Greedy decoding and pinned dependencies do not guarantee identical GPU output.

## Reproduce and inspect

```bash
cd ~/projects/python/pdfocr
uv sync --frozen
uv sync --project runners/mlx --frozen
uv run python scripts/setup_local_comparison.py
uv run python scripts/compare_book.py --out workspace/book-comparison-final
open workspace/book-comparison-final/comparison.html
uv run pytest -q
```

22 tests pass; Ruff passes. The improved doctor checks the isolated MLX runner,
so core-environment `mlx-vlm` absence is no longer mistaken for a broken install.
Successful page outputs are cached by source/config/implementation; failures
remain explicitly incomplete. No watcher, scheduled job or server is started.

The HTML is self-contained and escapes OCR text. JSON records measured values,
full model pins, inputs, raw edge text and repair decisions. Per-run directories
retain raw OCR, crop images, logs, process status and proposed repaired Markdown.

## Source and license declarations

The three requested model families, PP-DocLayoutV3 and teleocr-rs declare
Apache-2.0; GLM weights declare MIT. No upstream TeleOCR/Paddle Python SDK or
PyMuPDF is installed. Dependency metadata inventories are saved separately;
they are not a transitive license audit. `NOTICE.md` records source provenance.

- [OvisOCR3 model card](https://huggingface.co/ATH-MaaS/OvisOCR3)
- [PaddleOCR-VL-1.6 model card](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6)
- [PP-DocLayoutV3 weights](https://huggingface.co/PaddlePaddle/PP-DocLayoutV3_safetensors)
- [TeleOCR model card](https://huggingface.co/XingChen-AGI/TeleOCR)
- [TeleOCR port and limitations](https://github.com/rzafiamy/teleocr-rs)
- [TeleOCR GGUF conversion](https://huggingface.co/rleo/TeleOCR-GGUF)
