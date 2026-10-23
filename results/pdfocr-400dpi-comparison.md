# Native pdfrune 400-DPI rerun

Same 14 frozen provisional assistant visual transcriptions; not independent human gold. Prescription pages 70–71 remain qualitative.

All four local models rerun on the same 16 pages: 64 fresh page outputs and 12 adjacent boundaries. Fixed pdfrune is strict, without fallback. Both DPI and renderer change versus the prior PDFium run, so this measures the combined change. Model weights, prompts, resize caps and scoring are unchanged.

| Pipeline | 200-DPI CER | 400-DPI CER | Change, pp | 200-DPI WER | 400-DPI WER |
|---|---:|---:|---:|---:|---:|
| glm-ocr | 2.69% | 149.22% | +146.53 | 10.52% | 149.17% |
| ovisocr3 | 1.54% | 1.70% | +0.16 | 6.21% | 6.64% |
| paddle-vl | 6.90% | 7.25% | +0.35 | 14.55% | 15.13% |
| teleocr | 10.40% | 9.09% | -1.31 | 31.86% | 29.38% |
| paddle-book | 2.79% | 3.12% | +0.34 | 10.55% | 11.14% |

## Per-book CER

| Book | Pipeline | 200 DPI | 400 DPI |
|---|---|---:|---:|
| 10289757bsb | glm-ocr | 0.77% | 0.71% |
| makrobiotikoderd00hufeuoft | glm-ocr | 3.84% | 238.45% |
| 10289757bsb | ovisocr3 | 0.93% | 0.95% |
| makrobiotikoderd00hufeuoft | ovisocr3 | 1.91% | 2.16% |
| 10289757bsb | paddle-vl | 7.84% | 7.89% |
| makrobiotikoderd00hufeuoft | paddle-vl | 6.33% | 6.87% |
| 10289757bsb | teleocr | 1.61% | 1.69% |
| makrobiotikoderd00hufeuoft | teleocr | 15.69% | 13.54% |
| 10289757bsb | paddle-book | 1.27% | 1.29% |
| makrobiotikoderd00hufeuoft | paddle-book | 3.70% | 4.23% |

## Page-break continuity

| Pipeline | Text-only 200 → 400 | With visual 200 → 400 |
|---|---|---|
| glm-ocr | 3/4 → 3/4 | not tested |
| ovisocr3 | 0/4 → 0/4 | 1/4 → 1/4 |
| paddle-vl | 1/4 → 1/4 | 3/4 → 3/4 |
| teleocr | 2/4 → 2/4 | not tested |

## Matched Fraktur hyphen probe

Two supplementary pages (34–35) were rerun with fixed pdfrune at both 200 and 400 DPI for all four models: 16 extra page outputs. The visible split is Per- + son. = Person. These pages have no full-page reference and are excluded from primary CER. The HTML/JSON includes exact baseline and visual continuity results and original crop evidence.

Input DPI is distinguished from actual capped model-input sizes in the HTML/JSON. Native renderer commit: e174cbc6f80c1707ba048e46b9810cc85a8995d9. All source maps preserve exact OCR source characters; ambiguous joins remain review cases. No inference service or paid API was used.

Reproduce from the project root:

```bash
.venv/bin/python scripts/prepare_400.py
.venv/bin/python scripts/run_expanded.py --base workspace/expanded400 --selection datasets/expanded400/selection.json --phase ocr
.venv/bin/python scripts/run_400_followup.py
.venv/bin/python scripts/build_400_report.py
```


## GLM repetition diagnostics

The 400-DPI GLM page29 repetition reached its token limit and is retained in the primary CER. Insertion-heavy repetitions can yield CER above 100%.

| Case | Page29 CER | Token-limit flag |
|---|---:|---|
| native-400-default | 1737.23% | True |
| native-200 | 2.34% | False |
| native-400-cap1157 | 2.41% | False |
| pdfium-400 | 1758.29% | True |

The explicit lower-cap retry, substituted only for the token-limit failure, gives 2.63% CER over the same 14 references. That diagnostic variant is separate from the primary score and does not establish a validated production retry policy.


## Interpretation

400 DPI was not a general quality upgrade. Ovis remains strongest on this sample; TeleOCR improved on every Fraktur page but remains less accurate than Ovis and Paddle book assembly. The small Ovis/Paddle degradations are diagnostic observations, not universal rankings.

Exact split-word results did not change: Ovis text-only 0/4 and visual 1/4; Paddle text-only 1/4 and visual 3/4. Across all 12 labeled boundary operations, Paddle improved 4→6 matches and Tele 6→8; Ovis fell 4→3; GLM stayed at 8. No additional visual word join occurred on the eight non-split controls for either model.

The matched Fraktur Per- / son. probe was unresolved for every model at both DPIs. Paddle's continuation improved at 400 DPI, but GLM visual OCR misread son as jon and the gate deferred. Preserving source characters means the repair cannot silently replace those letters.

GLM repeated page29 with both pdfrune and PDFium at 400 DPI. Native 200 DPI and a lower-cap retry of the identical native-400 raster completed normally. The single-case lower-cap retry gives 2.63% aggregate CER; its separate diagnostic score does not replace the primary failure or validate a general retry policy.

Observed visual-worker wall time: 35.0s → 156.7s. Same algorithm, larger original-image crops; timings are not controlled throughput comparisons.
