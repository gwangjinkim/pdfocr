# PDF OCR lab

Local PDF to Markdown experiments with **pdfrune**, OvisOCR3, GLM-OCR,
PaddleOCR-VL-1.6 and TeleOCR. The tested inference machine was an Apple M3 Max
with 128 GiB unified memory. The MLX recipe below targets Apple Silicon.

[Results](results/) ·
[Reproduce the experiments](docs/reproduce.md) · [Licenses](NOTICE.md)

## What the experiments found

On 16 pages from two historical German books, Ovis had the lowest combined
character error rate. GLM was slightly better on the Antiqua subset, while
Ovis was substantially better on Fraktur. These are historical Antiqua pages,
not a benchmark of clean contemporary documents. Fourteen provisional visual
transcriptions were scored; two prescription pages were reviewed qualitatively.

400-DPI rendering did not generally improve OCR. GLM repeated a paragraph at
400 DPI with both pdfrune and PDFium; a separately recorded lower-input-cap
retry resolved that case. Raw failures remain in the primary results.

Paddle's local visual reader recovered one Fraktur split word at 400 DPI where
GLM failed. No false joins were added on 24 control decisions, representing
six physical boundaries repeated across resolutions and target OCR sources.
That small sample does not establish a production false-join rate.

## Setup

Install Python 3.12, uv and Rust. The tested toolchain was Rust 1.99.0;
the repaired pdfrune core requires Rust 1.92 or newer.

```bash
git clone https://github.com/gwangjinkim/pdfocr.git
cd pdfocr
rustup toolchain install 1.99.0
RUSTUP_TOOLCHAIN=1.99.0 uv sync --frozen
uv sync --project runners/mlx --frozen

# Explicitly downloads the pinned model weights and builds the Metal runner.
uv run python scripts/setup_local_comparison.py
uv run pdfocr doctor
uv run pytest -q
```

No model weights, Python environments, compiled binaries or book PDFs are
included. Models download only when explicitly requested. Every inference
worker is bounded and foreground; no inference server or watcher is started.

## Try your own PDF

```bash
uv run pdfocr prepare book.pdf --pages 1-3 --renderer pdfrune --dpi 200 --out workspace/book
uv run pdfocr run workspace/book --model ovisocr3 --python runners/mlx/.venv/bin/python
uv run pdfocr compare workspace/book
```

Use the run directory printed by `run` with `pdfocr repair`:

```bash
uv run pdfocr repair RUN_DIRECTORY --model boundary-small --out workspace/book-flow.proposed.md
```

The output is a proposal. Review uncertain joins against the scan. Source maps
retain exact source-character spans, and the visual repair can remove only a
mapped separator. It does not silently replace misrecognized letters.

## Included code and evidence

- `src/pdfocr/`: renderer integration, local inference adapters, Archive.org
  acquisition, scoring, guarded stitching and source maps.
- `scripts/`: every maintained experiment, repair and report runner used in the
  comparison, plus portable acquisition and verification helpers.
- `vendor-pdfrune/`: complete tracked source at repaired upstream commit
  `e174cbc6f80c1707ba048e46b9810cc85a8995d9`, including regressions and notices.
- `vendor-teleocr/`: pinned Apache-2.0 Rust/Candle port with the tested Metal
  selection modification. Its PDF feature is disabled for this experiment.
- `datasets/`: page selections, frozen provisional references and boundary labels.
- `results/`: measured summaries, original page responses and manifests. Archived
  metadata uses portable path labels; it is not a pre-populated live workspace.
- `tests/`: 28 harness tests. The vendored pdfrune core has 14 Rust tests.

Prompts, model revisions, BF16 versus Q8 precision, resize caps and limitations
are recorded. These adapters do not claim parity with official benchmark
pipelines. Legacy experimental profiles are clearly identified in the model
registry; only the four named OCR models were compared here.

The harness and author-contributed stitching code are MIT licensed. Bundled
third-party components retain their licenses. pdfrune is MIT OR Apache-2.0.
Keep the relevant licenses and notices when redistributing.
