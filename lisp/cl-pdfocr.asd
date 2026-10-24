(asdf:defsystem "cl-pdfocr"
  :description "Explicit local PDF OCR in Common Lisp using pdfrune and cl-vlm"
  :version "0.1.0" :license "MIT" :serial t
  :depends-on ("cl-pdfrune" "cl-vlm" "yason" "ironclad")
  :components ((:file "package") (:file "pipeline"))
  :in-order-to ((asdf:test-op (asdf:test-op "cl-pdfocr/tests"))))

(asdf:defsystem "cl-pdfocr/native"
  :description "Native cl-docling Gemma 4 E2B integration; no Python or service"
  :depends-on ("cl-pdfocr" "cl-docling/mlx" "cl-docling/gemma4-vlm")
  :components ((:file "native")))

(asdf:defsystem "cl-pdfocr/tests"
  :depends-on ("cl-pdfocr") :components ((:file "tests"))
  :perform (asdf:test-op (operation system)
             (declare (ignore operation system))
             (uiop:symbol-call :cl-pdfocr-tests :run-tests)))
