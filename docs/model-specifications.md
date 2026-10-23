# Model specifications and local hardware

Host inspected: Apple M3 Max, 128 GiB unified memory, arm64 macOS. MLX is the local inference path; vLLM/CUDA commands from model cards are not assumed to work on macOS. No background server is required by this harness.

| Profile | Nominal parameters | Purpose/output | Declared model license | Local execution status |
|---|---:|---|---|---|
| GLM-OCR | 0.9B | text, tables, formulas; official full pipeline adds layout | MIT | MLX adapter; see actual validation report |
| PaddleOCR-VL-1.6 | 0.9B | recognition; full document pipeline adds layout/crops | Apache-2.0 | BF16 MLX region OCR + Torch PP-DocLayoutV3 tested on PDF 9–10 |
| OvisOCR3 | 0.8B | Markdown/HTML tables/LaTeX; separate structured/cross-page modes | Apache-2.0 | BF16 MLX document-Markdown tested on PDF 9–10 |
| TeleOCR | 1.2B advertised | geometry-aware layout and region recognition | Apache-2.0 weights + port | Rust/Candle Q8 layout/crops on Metal tested on PDF 9–10 |
| MinerU2.5-Pro-2605 | 1.2B | coarse-to-fine layout, recognition and document assembly | Apache-2.0 weights; application additional terms | external full-pipeline adapter required |
| dots.mocr | 3B | document parsing, grounding; graphics/SVG tasks | MIT | external full-pipeline adapter required |
| LightOnOCR-3 | 0.8B / 1B / 4B nominal | Markdown, HTML tables, LaTeX, labeled bounding boxes, image/chart descriptions | Apache-2.0 | 0.8B/4B MLX profiles experimental until tested |
| boundary-tiny | 0.5B | Qwen2.5 text-only boundary decision baseline | Apache-2.0 | MLX-LM; evaluated on reused regression cases |
| boundary-small | 1.7B nominal, 4-bit conversion | Qwen3 text-only boundary decision candidate | Apache-2.0 upstream; check conversion | MLX-LM profile; download explicitly |

Parameter marketing counts and serialized checkpoint totals may differ, especially after including vision. As a rough **weights-only arithmetic estimate**, 1B BF16/FP16 parameters occupy 2 GB, 3B occupy 6 GB, and 4B occupy 8 GB. Actual runtime memory adds the vision tower (if excluded from the count), activations, KV cache, layout models, buffers and concurrency. These estimates are not minimum GPU specifications or measured peak allocations. The 128 GiB host has ample nominal weight capacity, but runtime compatibility and throughput must still be tested. Never infer a safe batch size from weights alone.

Language coverage is model-dependent. TeleOCR's card tags English and Chinese; GLM-OCR's card declares 8 languages; Paddle and dots advertise multilingual coverage. This setup does not infer equal quality across languages. The tested pages use historical German Antiqua typography, not a Fraktur benchmark. Evaluate Fraktur separately. The boundary rules also have German-specific lexical safeguards.

Context-window configuration is not a maximum PDF page count. The normal harness contract is one rasterized page per OCR request and bounded text context per boundary decision. OvisOCR3's separate cross-page task uses pairs of pages and current parses; that task is not yet integrated here. Do not concatenate a whole book into the OCR model context.

Official sources checked 2026-10-23:
- https://huggingface.co/zai-org/GLM-OCR
- https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6
- https://huggingface.co/ATH-MaaS/OvisOCR3
- https://huggingface.co/XingChen-AGI/TeleOCR
- https://huggingface.co/opendatalab/MinerU2.5-Pro-2605-1.2B
- https://huggingface.co/dots-studio/dots.mocr
- https://huggingface.co/lightonai/LightOnOCR-3-4B
- https://github.com/lightonai/LightOnOCR

Model metadata is not a transitive license audit. In particular, stock GLM and TeleOCR SDKs declare PyMuPDF; use image-only stages with reviewed dependencies. The local harness/core does not install those SDKs.
