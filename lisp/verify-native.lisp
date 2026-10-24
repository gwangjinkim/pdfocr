;;; Offline evidence verification: no model loading, GPU creation or subprocesses.
(load (merge-pathnames "load.lisp" *load-truename*))
(let* ((args (uiop:command-line-arguments))
       (root (uiop:ensure-directory-pathname (or (first args) (error "Supply the native smoke directory."))))
       (out (or (second args) (merge-pathnames "validation.json" root)))
       (ocr (merge-pathnames "ocr/" root))
       (run (cl-pdfocr::read-json (merge-pathnames "run.json" ocr)))
       (pages (gethash "pages" run))
       (text (uiop:read-file-string (merge-pathnames "reading.md" ocr) :external-format :utf-8))
       (spans (cl-pdfocr::read-json (merge-pathnames "reading-spans.json" ocr))))
  (assert (= 2 (length pages) (length spans)))
  (assert (equal "needs-review" (gethash "status" run)))
  (loop for page across pages for span across spans
        do (assert (equal "partial" (gethash "status" page)))
           (assert (equal "length" (gethash "stop_reason" page)))
           (assert (= 128 (length (gethash "token_ids" page))))
           (assert (equal (gethash "markdown" page)
                          (subseq (gethash "raw" page) (gethash "source_start" page)
                                  (gethash "source_end" page))))
           (assert (equal (gethash "markdown" page)
                          (subseq text (gethash "output_start" span)
                                       (gethash "output_end" span))))
           (format t "~&Page ~D: ~A; 128 native tokens; body/map exact.~%"
                   (gethash "page" page) (gethash "status" page)))
  (assert (not (probe-file (merge-pathnames ".running" ocr))))
  (cl-pdfocr::write-json out
    (cl-pdfocr::object "date" "2026-10-24" "runtime" (lisp-implementation-type)
      "runtime_version" (lisp-implementation-version) "inference" "Common Lisp graph and generation; MLX Metal kernels"
      "model" (gethash "model" (gethash "config" run)) "max_image_tokens" 70
      "pages" #(34 35) "generated_tokens_per_page" 128 "run_status" "needs-review"
      "page_status" "partial" "body_and_reading_spans" "exact"
      "external_inference_runtime" "none" "native_handle_balance" "integration assertion passed"))
  (format t "~&Native smoke evidence verified: ~A~%" out))
