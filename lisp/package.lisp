(defpackage #:cl-pdfocr
  (:use #:cl)
  (:export #:prepare-pdf #:recognize-prepared #:convert-pdf
           #:clean-markdown #:checked-boundary-join #:levenshtein-distance
           #:call-with-gemma4-adapter #:convert-native-pdf
           #:make-ollama-adapter #:convert-ollama-pdf))
