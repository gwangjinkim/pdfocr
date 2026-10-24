# Gemma: matched 200-DPI and 400-DPI comparison

Frozen provisional AI-assisted visual references, not independent human gold.

Same 18 pages, native repaired pdfrune at 200/400DPI, all 18 current 400-DPI renders match frozen pixels. Same pinned Q4_K_M models, Ollama 0.30.10, prompt, temperature 0 / seed 0 / context 16384 / output 8192, Gemma 4 thinking disabled, RGB/LANCZOS cap 2880 with no upscaling. Only render DPI changes; final image dimensions and visual-token usage can therefore change. Same frozen 14 CER/WER references, normalization and optional presentation-only body-slice cleanup. Same Qwen3 classifier and rules; 12 primary boundaries plus one supplementary Fraktur split. Runtime image budgets are held constant within each configuration.

Single temperature-zero run per page; no independent human gold or statistical generalization claim. The earlier specialized 200-DPI table used PDFium and is not relabeled as a new native 200 run. Concurrent timings are not a throughput benchmark. 1,120 is a ceiling, not a requirement to upscale small images.

## Presentation-only cleanup; no OCR letters corrected

| Model | Antiqua CER 200→400 | Fraktur CER 200→400 | Combined CER 200→400 | WER 200→400 |
|---|---:|---:|---:|---:|
| Gemma 3 12B | 3.52% → 2.73% | 9.24% → 20.16% | 7.09% → 13.62% | 16.22% → 22.12% |
| Gemma 4 12B, default image budget | 3.35% → 3.47% | 19.78% → 21.68% | 13.61% → 14.85% | 21.92% → 23.59% |
| Gemma 4 12B, 1120 image tokens maximum | 0.40% → 0.42% | 10.22% → 1.57% | 6.54% → 1.14% | 13.54% → 3.88% |

## Returned-output scores, with wrappers retained

| Model | Antiqua CER 200→400 | Fraktur CER 200→400 | Combined CER 200→400 | WER 200→400 |
|---|---:|---:|---:|---:|
| Gemma 3 12B | 5.00% → 4.20% | 10.40% → 21.17% | 8.37% → 14.80% | 17.27% → 23.09% |
| Gemma 4 12B, default image budget | 5.33% → 5.78% | 21.14% → 23.00% | 15.21% → 16.54% | 23.63% → 25.42% |
| Gemma 4 12B, 1120 image tokens maximum | 2.70% → 2.71% | 12.04% → 3.07% | 8.53% → 2.94% | 15.83% → 5.90% |

## Page-break repair after presentation-only cleanup

| Model | DPI | Correct split words | Wrong reconstructions on primary positives | False joins on 8 negatives | Action matches | Person probe correct | Wrong probe join |
|---|---:|---:|---:|---:|---:|---|---|
| Gemma 3 12B | 200 | 0/4 | 0 | 0/8 | 2/12 | False | False |
| Gemma 3 12B | 400 | 0/4 | 0 | 0/8 | 1/12 | False | False |
| Gemma 4 12B, default image budget | 200 | 3/4 | 0 | 0/8 | 7/12 | False | False |
| Gemma 4 12B, default image budget | 400 | 3/4 | 0 | 0/8 | 6/12 | False | False |
| Gemma 4 12B, 1120 image tokens maximum | 200 | 2/4 | 1 | 0/8 | 8/12 | False | True |
| Gemma 4 12B, 1120 image tokens maximum | 400 | 2/4 | 1 | 0/8 | 7/12 | False | True |
