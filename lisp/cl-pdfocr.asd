(asdf:defsystem "cl-pdfocr"
  :description "Explicit local PDF OCR in Common Lisp using pdfrune and cl-vlm"
  :version "0.2.0" :license "MIT" :serial t
  :depends-on ("cl-pdfrune" "cl-vlm" "yason" "ironclad")
  :components ((:file "package") (:file "pipeline"))
  :in-order-to ((asdf:test-op (asdf:test-op "cl-pdfocr/tests"))))

(asdf:defsystem "cl-pdfocr/native"
  :description "Native cl-docling Gemma 4 E2B integration; no Python or service"
  :depends-on ("cl-pdfocr" "cl-docling/mlx" "cl-docling/gemma4-vlm")
  :components ((:file "native")))

(asdf:defsystem "cl-pdfocr/ollama"
  :description "Common Lisp HTTP client for an existing local Ollama service"
  :depends-on ("cl-pdfocr" "usocket" "babel" "cl-base64")
  :components ((:file "ollama"))
  :in-order-to ((asdf:test-op (asdf:test-op "cl-pdfocr/ollama-tests"))))

(asdf:defsystem "cl-pdfocr/ollama-tests"
  :depends-on ("cl-pdfocr/ollama" "cl-pdfocr/tests")
  :components ((:file "ollama-tests"))
  :perform (asdf:test-op (operation system)
             (declare (ignore operation system))
             (uiop:symbol-call :cl-pdfocr-tests :run-ollama-tests)))

(asdf:defsystem "cl-pdfocr/tests"
  :depends-on ("cl-pdfocr") :components ((:file "tests"))
  :perform (asdf:test-op (operation system)
             (declare (ignore operation system))
             (uiop:symbol-call :cl-pdfocr-tests :run-tests)))
