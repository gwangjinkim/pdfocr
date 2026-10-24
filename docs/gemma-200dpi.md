# Gemma at 200 versus 400 DPI

This follow-up holds the repaired pdfrune renderer, source PDFs, page selection,
model digests, Ollama 0.30.10, prompt and generation controls fixed. It renders
the same 16 primary pages and two supplementary Fraktur pages at 200 DPI.
All 18 newly rendered 400-DPI controls must reproduce the frozen source pixels
before the new comparison proceeds. No PDFium fallback is permitted.

The external RGB/LANCZOS input cap remains 2880 pixels with no upscaling.
Gemma 3 and default-budget Gemma 4 use the existing loopback Ollama. A finite
supervised child holds Gemma 4's image-token maximum at 1120, as in the prior
400-DPI test. Every request unloads its model. The child server always stops
and is checked for exit; the pre-existing service is left unchanged.

The 1120 setting is a ceiling: a smaller 200-DPI image can use fewer image
tokens. The report retains prompt token counts and source/input dimensions,
because nominal render DPI is different from the final model representation.

```bash
uv run python scripts/run_gemma_200.py prepare
uv run python scripts/run_gemma_200.py run
uv run python scripts/gemma_budget_control.py --dpi 200

uv run python scripts/repair_gemma.py --base workspace/gemma200 --arm matched200cap2880
uv run python scripts/repair_gemma.py --base workspace/gemma200 --arm matched200cap2880 --normalize-format
uv run python scripts/repair_gemma.py --base workspace/gemma200 --arm budget1120 --models gemma4-12b
uv run python scripts/repair_gemma.py --base workspace/gemma200 --arm budget1120 --models gemma4-12b --normalize-format
uv run python scripts/build_gemma_dpi_report.py
uv run python scripts/verify_gemma_dpi_results.py
```

`prepare` and the repair runner accept `--source-root` when reusing an existing
local lab. The published run used the author's cached PDFs and 400-DPI inputs;
it did not download replacement books or weights. Reproduce the original
400-DPI experiment first as described in `gemma-comparison.md`.

The report shows returned-output and presentation-only-cleaned CER/WER.
Cleanup is the same exact contiguous-body slice used at 400 DPI, with no letter
corrections. Scores use the same 14 frozen provisional AI-assisted references.
They are not independent human gold. The two prescription pages remain
qualitative. The supplementary Fraktur split remains outside primary CER.

The same Qwen3-1.7B classifier and rules evaluate 12 primary page boundaries
and the one supplementary Fraktur split, on both raw and cleaned OCR. Wrong
reconstructions on true split words are reported separately from false joins
on the eight non-split controls. Source maps are checked character by character.

The older specialized-model200-DPI comparison used PDFium. Those earlier
numbers are not silently relabeled as matched native-pdfrune200-DPI results.
Timing is observational; overlapping inference prevents a throughput ranking.
