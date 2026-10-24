#!/bin/sh
# Explicit, finite setup: project dependencies and renderer only; no model/server.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
command -v ocicl >/dev/null 2>&1 || { echo 'Install ocicl first (macOS: brew install sbcl ocicl rust).' >&2; exit 1; }
command -v cargo >/dev/null 2>&1 || { echo 'Install Rust/Cargo first (macOS: brew install rust).' >&2; exit 1; }
OCICL_LOCAL_ONLY=1 ocicl install
cargo build --locked --release --manifest-path vendor-pdfrune/Cargo.toml -p pdfrune-ffi
sbcl --noinform --no-sysinit --no-userinit --script lisp/run-ollama-tests.lisp
