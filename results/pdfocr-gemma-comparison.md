# Gemma: the original workflow and the matched local OCR test

16 primary pages, 14 CER/WER references, 12 primary boundaries; supplementary Fraktur 34–35 excluded from primary CER.

Frozen provisional AI-assisted visual references, not independent human gold.

## Matched 400-DPI per-page OCR (cap2880)

| Model | Antiqua CER | Fraktur CER | Combined CER | Combined WER |
|---|---:|---:|---:|---:|
| gemma3-12b | 4.20% | 21.17% | 14.80% | 23.09% |
| gemma4-12b | 5.78% | 23.00% | 16.54% | 25.42% |
| gemma4-12b (1120 image tokens) | 2.71% | 3.07% | 2.94% | 5.90% |

## Same OCR after presentation-only cleanup (no letter corrections)

| Model | Antiqua CER | Fraktur CER | Combined CER | Combined WER |
|---|---:|---:|---:|---:|
| gemma3-12b | 2.73% | 20.16% | 13.62% | 22.12% |
| gemma4-12b | 3.47% | 21.68% | 14.85% | 23.59% |
| gemma4-12b (1120 image tokens) | 0.42% | 1.57% | 1.14% | 3.88% |

## Original-style 72-DPI batch workflow

| Model | Antiqua CER | Fraktur CER | Combined CER | Combined WER |
|---|---:|---:|---:|---:|
| gemma3-12b | 4.32% | 28.53% | 19.45% | 32.67% |

## Guarded page-break repair

- gemma3-12b (matched400cap2880, raw): 0/4 correct split words; 0 wrong primary word reconstructions; 0/8 false joins on non-split controls; 0/12 action matches; Person probe: False, wrong reconstruction: False.
- gemma4-12b (matched400cap2880, raw): 0/4 correct split words; 0 wrong primary word reconstructions; 0/8 false joins on non-split controls; 0/12 action matches; Person probe: False, wrong reconstruction: False.
- gemma4-12b (budget1120, raw): 0/4 correct split words; 0 wrong primary word reconstructions; 0/8 false joins on non-split controls; 0/12 action matches; Person probe: False, wrong reconstruction: False.
- gemma3-12b (matched400cap2880, format-cleaned): 0/4 correct split words; 0 wrong primary word reconstructions; 0/8 false joins on non-split controls; 1/12 action matches; Person probe: False, wrong reconstruction: False.
- gemma4-12b (matched400cap2880, format-cleaned): 3/4 correct split words; 0 wrong primary word reconstructions; 0/8 false joins on non-split controls; 6/12 action matches; Person probe: False, wrong reconstruction: False.
- gemma4-12b (budget1120, format-cleaned): 2/4 correct split words; 1 wrong primary word reconstructions; 0/8 false joins on non-split controls; 7/12 action matches; Person probe: False, wrong reconstruction: True.

## Methods and limits

**legacy:** Original plural-image prompt, multiple contiguous pages per request, PyMuPDF default 72 DPI, no generation options. Only stream=false and keep_alive=0 added for transport and cleanup. Current pinned models/runtime; not an archived 2025 measurement.

**matched:** Same fixed pdfrune 400-DPI source pages, Pillow RGB/LANCZOS cap2880, original prompt, one page/request; temp0 seed0 context16384 output8192, Gemma4 thinking disabled.

**batch_scoring:** Whole-excerpt CER/WER against concatenated frozen references. No inferred page segmentation; not identical to summed per-page CER. Only the three fully referenced batches count; symbols remain qualitative.

**normalization:** Unchanged content_text: NFC, long s to s, page-number-only furniture and Markdown heading/emphasis removed, line-end hyphens joined, whitespace collapsed; case/spelling/punctuation count. Returned-output scores keep code fences and commentary. Separate format-cleaned scores remove only a single outer fence and leading page-number metadata; body characters stay exact.

**boundary:** Unchanged local Qwen3-1.7B classifier and source-preserving rules. No extra visual repair. Raw answers and a separate presentation-only cleanup variant use the same classifier and source guards. Printed page numbers/code fences can prevent joins in the raw arm.

**historical:** Original article April6 2025; all new comparisons measured October24 2026, about18.6 months later. No assertion that original Gemma3 tag or defaults are frozen to2025.

**budget_control:** Same Gemma4 weights, prompt, cap2880, temperature0, seed0, context16384, output8192 and thinking=false; only the temporary Ollama child uses LLAMA_ARG_IMAGE_MAX_TOKENS=1120. Server log and prompt token counts confirm override. This is an installed-runtime control, not a run on the newest Ollama release.

**optional_batch:** One optional Gemma4 default-thinking batch excerpt (A9–14) completed; the following unscored A70–71 request was interrupted to prioritize the main tests. Remaining Gemma4 batch requests were not run. This partial branch is displayed as a diagnostic only, without full-sample metrics.
