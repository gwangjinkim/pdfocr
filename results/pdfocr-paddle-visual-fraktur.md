# Paddle local visual repair on Fraktur

PaddleOCR-VL-1.6 BF16 / local MLX, OCR: prompt. Same frozen crops, gate, Qwen3 classifier and page OCR as the GLM experiment.

**Result: one correct added join, no false joins on 24 control decisions.**

At 400 DPI, Paddle reads Per- and son. and recovers Person in the Paddle OCR reading copy. GLM read jon. and deferred. The only edit deletes the inter-page space; every raw source character is preserved.

At 200 DPI the crop read still drops the hyphen and the page OCR continuation is ion. Ovis keeps the hyphen but misreads ion. at both resolutions. Those cases defer; no letters are silently replaced.

| DPI | Target page OCR | GLM word correct | Paddle word correct |
|---:|---|---|---|
| 200 | ovisocr3 | False | False |
| 200 | paddle-vl | False | False |
| 400 | ovisocr3 | False | False |
| 400 | paddle-vl | False | True |

The 24 negative decisions repeat six physical non-split boundaries at two resolutions against two OCR sources. There is only one physical positive boundary; one of its four OCR/resolution variants has correct stems and a dropped hyphen. That repairable variant succeeds. This is useful evidence, not a validated production false-join rate.

All frozen crop/source hashes, exact source maps and separator-only edits were verified. No dependencies or model weights were downloaded, and no inference service was started.

Reproduce from the project root:

```bash
.venv/bin/python scripts/run_paddle_visual.py
.venv/bin/python scripts/build_paddle_visual_report.py
```
