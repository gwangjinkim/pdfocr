# Two-page local review corpus

Internet Archive book `10289757bsb`, PDF pages 9–10 (printed 5–6).
Prepared page pixel hashes are in `workspace/demo/document.json`.

References are provisional assistant visual transcriptions, not independently
human-verified gold. Page 9 starts from archiveorgocr's existing reference,
visually checked against the scan; corrected its spurious `r` after `fortdau-`.
Page 10 transcribed from the scan. Historical spelling is preserved; long s is
normalized to s. Line-end hyphens and printed page numbers are retained here.
Reference text was fixed before examining the three new model outputs.

Content scoring removes page-number furniture, Markdown emphasis, and joins
letter-hyphen-newline-letter within a page in BOTH reference and prediction.
Whitespace is collapsed; NFC is applied. Case, punctuation and spelling count.
Raw scoring is retained separately to expose transcription-policy differences.
The one inter-page test is `anstecken-` + `den` -> `ansteckenden`.
This tiny corpus cannot establish a global OCR ranking or false-join rate.

Final visual QA also restored the visible comma after `unheilbaren` in page 9.
The references therefore include a documented post-run correction, not a blind gold set.
