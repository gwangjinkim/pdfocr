# Common Lisp PDF OCR: native and Ollama backends

In the native backend, the application, model graph, tokenization calls,
generation loop, manifests, cleanup and reviewed boundary edits are Common Lisp.
Native libraries remain:
pdfrune's Rust C ABI, MLX tensor kernels, the Rust tokenizer and image codecs.
The separately loaded Ollama backend keeps orchestration and HTTP in Lisp while
Ollama performs inference. Neither backend downloads models, starts services or
watchers, or silently falls back to the other. Loading the base ASDF system does
not create a GPU backend.

| Backend | Load | Inference execution |
|---|---|---|
| Native | `cl-pdfocr/native` | Lisp model graph/generation, native MLX kernels |
| Ollama | `cl-pdfocr/ollama` | Existing loopback Ollama service; Lisp HTTP client |

## Reused packages and limits

| Package | Reused surface | Important boundary |
|---|---|---|
| `cl-pdfrune` | PDF lifecycle, native text, page dimensions, RGBA rendering and PNG encoding | Built from the repaired vendored pdfrune; 0-based native API is converted to 1-based application pages |
| `cl-vlm` | Public messages, exact model manifests, capability checks, generation and request release | Generic protocol; it does not implement model architectures |
| `cl-docling/gemma4-vlm` | Real native Gemma 4 adapter, borrowed-model lifecycle | Only the pinned E2B checkpoint; 70 image tokens; at most four images |
| `cl-docling/images` | Native PNG/JPEG readers and model-specific preprocessing | A visual encoder is not a complete recognizer; public picture crops use quantized coordinates |
| `cl-transformer-blocks` | Native MLX backend, tensor kernels, tokenizer and disposal | Existing model-family qualification does not automatically cover a new decoder |

The application currently uses a Markdown extraction prompt and the E2B factory.
Other caller-supplied `cl-vlm` adapters can be used through `recognize-prepared`,
provided their output is Markdown. SmolDocling/Granite DocTags should instead go
through cl-docling's existing parser/exporter; do not label raw DocTags Markdown.

### Exact benchmark models need more work

| Model from the article | Native support found in the inspected packages | Extension required |
|---|---|---|
| Gemma 3 12B | No native adapter | Exact SigLIP/projector/decoder, image token insertion and pan-and-scan or verified multi-view processing |
| Gemma 4 12B with 1120 image tokens | E2B only, hard-limited to 70 image tokens | Qualify higher image budgets, the 12B text/vision configuration, tokenizer/template, caching and generation |
| OvisOCR3 | No native adapter | Exact checkpoint-specific vision/projector/text model and processor |
| PaddleOCR-VL-1.6 | No native adapter | Region recognizer plus layout, reading order and footnote/duplicate assembly for the full pipeline |
| GLM-OCR | No native adapter | Exact processor/vision/text execution and the declared recognition versus layout scope |
| TeleOCR Q8 port | Rust/Candle executable, not a native Lisp adapter | FFI or subprocess integration is possible but must be labeled external execution; native inference needs a separate implementation |

The existing `cl-vlm` protocol can host these adapters without another OCR-specific
protocol. Register capability flags only after independent processor, tensor,
logit/token, CPU/Metal, cache and resource-cleanup gates. Gemma 3's earlier five-view
test is not covered by E2B's four-image limit. A model name is not an adapter.
The native packages also do not claim the benchmark's Q4_K_M/GGUF execution;
switching to BF16 is a new configuration and requires new measurements.

## Setup

The loader expects the existing local packages under `~/projects/cl/`. Set
`PDFOCR_CL_PROJECTS` to another parent directory when needed. It uses the engine's
local dependency tree plus the local OCICL packages, and compiles FASLs inside
this repository's ignored `workspace/`. It ignores user initialization and
inherited ASDF registries. Dependencies must already be installed.

Build pdfrune's C ABI explicitly, using the existing cached Rust dependencies:

```sh
cd vendor-pdfrune
RUSTUP_TOOLCHAIN=1.99.0 cargo build --offline --release -p pdfrune-ffi
cd ..
sbcl --noinform --no-sysinit --no-userinit --script lisp/run-tests.lisp
```

Build cl-docling's native image library and cl-transformer-blocks' MLX/tokenizer
libraries using those packages' instructions if they are absent. Supply the
locally acquired, locked E2B checkpoint; this code does not fetch weights.

## Use the native pipeline

```lisp
(load "lisp/load.lisp")
(asdf:load-system "cl-pdfocr/native")

(cl-pdfocr:convert-native-pdf
 #P"book.pdf" #P"workspace/my-book/"
 #P"/path/to/cl-docling/.build/gemma4-e2b/"
 #P"/path/to/cl-docling/references/gemma4-e2b.lock.json"
 :pages '(34 35) :dpi 200 :max-new-tokens 2048 :device :gpu)
```

Only the requested pages are read. The model is reused across the pages, then
disposed before its backend; tensor handles must return to baseline.
The output contains:

- `prepared/document.json`, page PNGs and separate native text;
- `ocr/page-NNNN.json`: raw response, exact cleaned body interval, token IDs,
  image hash, stop reason and complete/partial/error status;
- `ocr/reading.md` and `reading-spans.json`: reading copy and page/body provenance;
- `ocr/run.json`: model/revision, prompt, budget, prepared manifest identity and
  overall status. A length stop makes the run `needs-review`.

## Use the Ollama pipeline

This path requires SBCL, local `usocket`, `babel` and `cl-base64` dependencies,
and an already running Ollama service with a vision model installed. The client
uses Lisp sockets directly: no curl or Python subprocess. It connects only to
`127.0.0.1` and an explicit port, without proxies or redirects. It rejects remote
model metadata and cloud tags. It does not start, restart or stop the service.

```lisp
(load "lisp/load.lisp")
(asdf:load-system "cl-pdfocr/ollama")

(cl-pdfocr:convert-ollama-pdf
 #P"book.pdf" #P"workspace/ollama-gemma3/" "gemma3:12b"
 :pages '(34 35) :dpi 200 :max-new-tokens 2048
 :context-length 8192 :port 11434 :timeout 180)
```

Use `"gemma4:12b"` and a fresh directory for Gemma 4. To reuse prepared pages:

```lisp
(cl-pdfocr:recognize-prepared
 #P"workspace/my-book/prepared/" #P"workspace/ollama-gemma4/"
 (cl-pdfocr:make-ollama-adapter "gemma4:12b"
   :expected-digest "the-exact-digest-from-your-installed-model")
 :max-new-tokens 2048)
```

Model names must match `/api/tags` exactly. The adapter records the installed
digest, runtime version, precision, endpoint, context size and generation options
in its resume identity. It rechecks the model tag and runtime version before and
after generation; this detects changes, but cannot make service-side tag updates
transactional. Do not retag models during a run. A different digest, context size,
backend or budget requires a separate directory.

Requests are nonstreaming, `temperature=0`, `seed=0`, `think=false`, one image per
page, and `keep_alive=0`. The latter unloads after each request; it is slower than
keeping a model resident but leaves no model resident for this application.
The whole HTTP request has a deadline, response bodies are bounded at 16 MiB,
and length/chunked/connection-close framing is supported. A connection failure,
timeout or unknown finish reason is a failure, never an invitation to start a
service or retry through another backend.

Ollama chat responses do not provide token IDs. These records contain an empty
`token_ids` array, `backend_response.token_ids_available=false`, the reported token
count and the full response, including timing and prompt counts. No synthetic IDs
are invented. An explicit length stop or reported count reaching the budget is
conservatively marked partial. The image budget and preprocessing are controlled
by the service: this path does **not** verify pan-and-scan, tiling or 1120 image
tokens and is not a reproduction of those earlier benchmark configurations.

Run offline contract tests without a service:

```sh
sbcl --noinform --no-sysinit --no-userinit --script lisp/run-ollama-tests.lisp
```

Run an explicit two-page, 32-token integration check against an existing service:

```sh
PDFOCR_TEST_PREPARED=workspace/my-book/prepared/ \
PDFOCR_TEST_OUT=workspace/ollama-smoke/ \
PDFOCR_TEST_MODEL=gemma3:12b \
  sbcl --noinform --no-sysinit --no-userinit --script lisp/ollama-smoke.lisp
```

Use a fresh output directory for each model. The same two 200-DPI Fraktur pages
were exercised through the installed Gemma 3 12B and Gemma 4 12B models, each
bounded at 32 reported tokens per page. These are integration checks, not new
CER scores or page-break comparisons. Evidence is in
[`results/common-lisp-ollama/`](../results/common-lisp-ollama/).
`verify-ollama.lisp OUTPUT-DIRECTORY/` checks these 32-token integration records
and their exact body maps offline, without contacting the service.

The service contracts follow Ollama's official
[chat API](https://docs.ollama.com/api/chat) and
[installed-model listing](https://docs.ollama.com/api/tags).

Resume only explicitly with `:resume t`. The source, page selection, DPI, image
hashes, prepared manifest, model identity, prompt and generation limit must match.
Changed cached response records reject against the committed manifest. Existing
errors/partial outputs remain visible rather than silently receiving a retry.
Use a fresh output directory for a new model, prompt, budget or resolution.

`prepare-pdf` alone can be used for native extraction or rendering without loading
any model. Its default 40-million-pixel limit rejects unusually large pages;
an explicit `:max-pixels` up to 160 million is available on that preparation API.

## Page breaks

Both backends keep page boundaries visible. This port does not claim a native port of the
Qwen3-1.7B classifier or Paddle visual repair; those exact adapters are absent.
After reviewing the scan, apply a checked edit to exact fragments:

```lisp
(cl-pdfocr:checked-boundary-join "Per-" "son." 34 35 "Per-" "son")
;; => "Person.", plus the deleted hyphen's source position
```

Wrong continuation letters, a changed stem or nonadjacent pages reject. The caller
is responsible for the visual review. This function is not a language-based
proof that an otherwise matching join is correct.

## Integration regression

SBCL enables floating-point traps that C/Rust image codecs normally expect masked.
The first clean native render of the Fraktur page failed with
`FLOATING-POINT-INVALID-OPERATION`. `with-rasterizer-float-environment` masks only
the rasterizer call and restores the caller's modes. Both pages at 200 and 400 DPI
then matched all RGBA pixels of the frozen Python-rendered references exactly.
Other Lisp implementations must qualify their own foreign floating-point setup.

The direct Gemma ASDF system also referenced a generation observer defined by
`cl-docling/mlx`, which the broader upstream test loader had already loaded.
`cl-pdfocr/native` declares that required system explicitly. No private engine
function is called by this application's integration. A separate regression
fixes relative atomic-write destinations before rename.

An explicit rendering regression is available:

```sh
PDFOCR_TEST_PDF=/path/to/makrobiotikoderd00hufeuoft.pdf \
  sbcl --noinform --no-sysinit --no-userinit --script lisp/render-smoke.lisp
```

`native-smoke.lisp` selects those same PDF pages 34–35 and bounds native generation
to 128 tokens per page. It is an integration smoke, not a full-page OCR-quality
comparison or validation of the article's 12B recommendations.
The measured native run completed both pages on Metal with 128 generated tokens
each and `length` stops. Both are retained as partial, the run is `needs-review`,
and the native model/backend handle-balance assertion passed. It is not a
full-page recognition or page-break-repair result.

The retained [native evidence](../results/common-lisp-native/) includes both raw
responses, IDs, stop records, reading maps, checkpoint identity and pixel checks.
Verify a completed local smoke without loading a model:

```sh
sbcl --noinform --no-sysinit --no-userinit --script lisp/verify-native.lisp \
  workspace/common-lisp-native-qualified/
```

The application code inherits the repository's MIT license. pdfrune remains
MIT OR Apache-2.0; the Lisp packages, native libraries and model weights retain
their respective licenses. Ollama is a separately installed runtime; Gemma 3
weights use Gemma terms and are not relicensed by this application's MIT license.
