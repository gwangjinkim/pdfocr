# Gemma 3 12B with verified explicit tiling

Frozen provisional AI-assisted visual references, not independent human gold.

Explicit overview plus four overlapping full-width horizontal bands from the same frozen RGB/LANCZOS cap2880 inputs; native pdfrune at both DPIs. Complete pixel coverage, exact crop hashes and five submitted image hashes verified. >=1280 total prompt tokens on all pages; two same-prompt overview controls per DPI confirm >=1024 extra tokens. Not a native pan-and-scan implementation. Original prompt replaced by an explicit one-page/multiple-view instruction; this is a stack comparison, not a crop-only ablation across all pages. Same frozen model digest, Ollama0.30.10, temp0/seed0/context16384/output8192. 16 primary pages plus two supplementary Fraktur probe pages per DPI; 14 provisional full-page references; unchanged cleanup/scorer/Qwen3 repair/guards.

Single deterministic run; provisional AI-assisted references, not independent human gold. Four split-word primary positives are Antiqua; Fraktur has one separate positive. No throughput ranking; extra views add compute. Same-prompt overview controls cover only two pages per DPI, not a full-sample prompt ablation.

## Presentation-only cleanup

| DPI | Antiqua CER | Fraktur CER | Combined CER | WER | Output-limit pages |
|---|---:|---:|---:|---:|---|
| 200 | 1.97% | 4.15% | 3.33% | 7.64% | [] |
| 400 | 3.97% | 32.24% | 21.63% | 25.61% | [] |

## Returned output

| DPI | Antiqua CER | Fraktur CER | Combined CER | WER | Output-limit pages |
|---|---:|---:|---:|---:|---|
| 200 | 3.46% | 5.30% | 4.61% | 8.69% | [] |
| 400 | 5.38% | 33.23% | 22.78% | 26.54% | [] |

## Cleaned Gemma 3 baseline versus tiling

| DPI | Antiqua baseline → tiled | Fraktur baseline → tiled | Combined baseline → tiled |
|---|---:|---:|---:|
| 200 | 3.52% → 1.97% | 9.24% → 4.15% | 7.09% → 3.33% |
| 400 | 2.73% → 3.97% | 20.16% → 32.24% | 13.62% → 21.63% |

## Boundary repair

| DPI | Variant | Correct primary words | Wrong primary reconstructions | False joins on 8 controls | Action matches | Person correct | Wrong probe join |
|---|---|---:|---:|---:|---:|---|---|
| 200 | raw | 0/4 | 0 | 0/8 | 0/12 | False | False |
| 200 | format-cleaned | 3/4 | 0 | 0/8 | 8/12 | False | False |
| 400 | raw | 0/4 | 0 | 0/8 | 0/12 | False | False |
| 400 | format-cleaned | 2/4 | 0 | 1/8 | 6/12 | False | False |

## Same-prompt overview controls

| DPI | Book and page | Overview CER | Tiled CER | Overview tokens | Tiled tokens |
|---|---|---:|---:|---:|---:|
| 200 | 10289757bsb PDF9 | 12.90% | 3.61% | 383 | 1463 |
| 200 | makrobiotikoderd00hufeuoft PDF26 | 28.74% | 1.77% | 383 | 1463 |
| 400 | 10289757bsb PDF9 | 12.90% | 3.61% | 383 | 1463 |
| 400 | makrobiotikoderd00hufeuoft PDF26 | 29.21% | 17.05% | 383 | 1463 |

## Output quality flags

Exact repeated paragraphs of at least 120 characters are flagged without rewriting the output. A normal stop does not prove a single complete transcription.

- 400DPI, makrobiotikoderd00hufeuoft PDF201: 3 repeated long paragraph patterns; 1245 generated tokens; stop reason stop; output ceiling reached: False.
