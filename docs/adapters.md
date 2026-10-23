# Adapter contract

There are four execution paths besides the pdfrune native baseline:

1. **MLX**: isolated foreground worker for supported page models. It loads pinned local snapshots, takes one raster per page, and writes raw output. Only actually tested combinations should be considered supported; the other profiles remain experimental.
2. **Existing endpoint**: `pdfocr run DOC --model glm-ocr --backend endpoint --endpoint http://127.0.0.1:PORT/v1 --endpoint-model EXACT_MODEL_ID`. No server is launched. A non-loopback URL requires `--allow-remote` and HTTPS. Models with no built-in task prompt require `--prompt-file` pointing to their documented prompt. This is an image-chat adapter, not an automatic implementation of a vendor's document pipeline.
3. **Official pipeline command**: `pdfocr run DOC --model teleocr --backend command --command-json '["/absolute/path/runner-python", "/absolute/path/adapter.py", "{request}"]'`.

The command adapter receives a JSON request path. It must read `pages`, each containing `page`, `image_path`, and `result_path`, and run the **complete** intended pipeline on the images (layout, crop recognition, assembly, postprocessing). It must write one JSON object per page to `result_path`:

```json
{"page": 9, "status": "ok", "markdown": "source transcription", "seconds": 1.23, "raw": {"original_pipeline_response": "..."}, "possibly_truncated": false}
```

On failure write `status: error` with a diagnostic, not a fabricated transcription. Return nonzero for document-level failure. Include layout/model revisions, runtime package versions, preprocessing and any license conditions in `raw`. Do not download models implicitly, start persistent services or leave child processes alive. The parent places the command in a separate process group and terminates that group on timeout/interruption. Do not detach from it.

Use pdfrune for PDF reading/rendering outside the model's image-only adapter. The optional PDFium fallback is already handled during preparation. Avoid importing entire vendor SDKs that unconditionally install PyMuPDF when only their image/model stages are needed. Replacing PDF IO must preserve the vendor's intended layout/crop recognition behavior and be evaluated; it does not automatically preserve benchmark performance.

4. **Built-in TeleOCR**: `pdfocr run DOC --model teleocr` invokes the pinned local
Rust/Candle binary directly, with no server. It implements the hybrid decoder,
layout and per-region OCR; the local device-selection patch enables Metal.

Paddle's MLX profile now invokes PP-DocLayoutV3 plus crop recognition and simple
reading-order assembly. OvisOCR3 document-Markdown runs directly on MLX. See
`docs/local-comparison.md` for measured readiness and remaining limitations.

 MinerU-Pro needs its coarse-to-fine pipeline and postprocessing. dots.mocr needs its task prompts/output parser. MinerU and dots integrations remain adapter-only.
