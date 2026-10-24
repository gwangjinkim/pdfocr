(asdf:defsystem "cl-vlm"
  :description "Small protocols for native Common Lisp vision-language models"
  :version "0.7.0"
  :author "Gwang-Jin Kim"
  :license "MIT"
  :serial t
  :components ((:file "src/package")
               (:file "src/conditions")
               (:file "src/content")
               (:file "src/manifest")
               (:file "src/protocol")
               (:file "src/adapter-operations"))
  :in-order-to ((asdf:test-op (asdf:test-op "cl-vlm/tests"))))

(asdf:defsystem "cl-vlm/conformance"
  :description "Dependency-free conformance checks for cl-vlm generation adapters"
  :depends-on ("cl-vlm")
  :serial t
  :components ((:file "src/conformance-package")
               (:file "src/conformance")))

(asdf:defsystem "cl-vlm/tests"
  :depends-on ("cl-vlm" "cl-vlm/conformance")
  :components ((:file "tests/suite"))
  :perform (asdf:test-op (operation system)
             (declare (ignore operation system))
             (uiop:symbol-call :cl-vlm-tests :run-tests)))
