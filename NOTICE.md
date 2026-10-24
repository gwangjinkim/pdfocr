# Sources and licensing

The harness and the author's contributed archiveorgocr stitching adaptation and regression data are published under MIT at the author's explicit request. Third-party software retains the licenses identified below.

- `vendor-pdfrune/`: snapshot of https://github.com/gwangjinkim/pdfrune at repaired commit `e174cbc6f80c1707ba048e46b9810cc85a8995d9`; MIT OR Apache-2.0. Its license files are retained. A local scanned-rendering repair is now applied; see docs/pdfrune-repair.json.
- `src/pdfocr/borrowed/archive_stitching.py`: copied from the user's archiveorgocr working tree. Standalone CLI removed, formatting may differ. Source content hashes and Git HEAD are in `docs/archiveorgocr-provenance.json`.
- `datasets/boundaries/seed.jsonl`: reused archiveorgocr regression data. Labels are provisional and not an independent benchmark; see its README.
- Models retain their own licenses. A model's license does not cover every SDK, layout model, tokenizer, binary or dataset dependency.
- PDFium is an explicit rendering fallback, not a hidden change to pdfrune. `document.json` records each page's actual renderer and reason. The pypdfium2 and PDFium notices must remain with redistributed binaries.

No model weights are vendored into this source tree. Downloaded snapshots live in the Hugging Face cache; `model-pins.json (runtime models/*.json files are generated locally)` pins their revisions.


Local OCR additions (2026-10-23):

- `vendor-teleocr/`: Apache-2.0 source at commit
  `957cdbabe80e86d652c5fcc938ed7fbcf1eb2bbe`. Its LICENSE is retained.
  The local device-selection modification is recorded as a patch. The compiled
  image-only binary does not enable the port's optional PDF feature.
- TeleOCR Q8 GGUF conversion `rleo/TeleOCR-GGUF`, OvisOCR3
  `ATH-MaaS/OvisOCR3`, PaddleOCR-VL-1.6 and PP-DocLayoutV3 weights declare
  Apache-2.0 in their published metadata. Exact revisions are pinned in models/.
- Torch/Torchvision were added for layout inference; no upstream TeleOCR or
  PaddleOCR Python SDK was installed in the specialized OCR runner.
- The project inventory is metadata inspection, not a transitive legal audit.
  Preserve upstream notices when distributing code, binaries or weights.

The repair was developed against d710b96350a454b94005fcffbc5ccdd9291d55ba with patch SHA-256 b1f482cb2ff34c108118549fe23e16dcc09c63d1cefbe5c1f94d10e6e71ff13a. The published source snapshot is upstream commit e174cbc6f80c1707ba048e46b9810cc85a8995d9, which includes that repair. New codec notices are in vendor-pdfrune/THIRD_PARTY_NOTICES.md.

Publication includes source snapshots and text-based experiment evidence. Complete book PDFs and model weights are not bundled. Two attributed boundary crops are included as experiment evidence in results/figures/. Their rights and licenses are independent of the harness license. Absolute workstation paths in archived metadata were replaced with portable labels.

Historical Gemma comparison (2026-10-24):

- `runners/legacy/` is an explicitly separate environment for reproducing the
  author's earlier PyMuPDF/Ollama workflow. PyMuPDF 1.26.7 is AGPL/commercial;
  it is not relicensed by this repository's MIT license. Its wheels and license
  text are not bundled. See https://pymupdf.readthedocs.io/en/latest/about.html.
- Gemma 3 uses Google's Gemma Terms of Use, not Apache-2.0. Gemma 4 is
  Apache-2.0. Exact local GGUF manifest digests, parameter counts and Q4_K_M
  precision are recorded with the measurements. No weights are redistributed.
- Ollama is MIT licensed. The comparison connects to an existing service. The
  optional image-budget control explicitly starts a finite, supervised child
  on a separate loopback port, unloads its model, terminates it, and waits for
  exit. It does not modify or restart the user's existing service.
