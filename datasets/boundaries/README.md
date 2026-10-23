# Dataset provenance

`boundaries/seed.jsonl`: 56 labelled records. 26 synthetic authored training records, 8 synthetic authored validation records, 12 separately authored regression test records, and 10 scan-checked boundaries from real Gemma 4 12B OCR. Groups and duplicate content are checked against leakage. The two source books are entirely excluded from train/validation. These tests were consulted during rule development and must not be represented as a blind benchmark.

Historical sources: Internet Archive identifiers `10289757bsb` (PDF pages 9–14) and `makrobiotikoderd00hufeuoft` (PDF pages 25–30), using the user's local PDFs. OCR wording was intentionally not corrected when building boundary examples. Labels and OCR references were visually checked by the assistant and await independent human validation.

`ocr/pilot.jsonl`: two full-page images, rendered to 2000 pixels wide with pypdfium2, plus provisional source transcriptions. Long s is transcribed as s. This is OCR evaluation data, not OCR training data. References retain page numbers and historical spelling. Do not infer corpus accuracy from two pages.

`boundaries/sft`: derived chat-format train/valid JSONL; test records are deliberately excluded. `manifest.json` lists included/excluded IDs and the prompt version. See `training/README.md` before attempting a fine-tune.
