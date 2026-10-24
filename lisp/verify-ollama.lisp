;;; Verify the bounded two-page integration records offline; no service contact.
(load (merge-pathnames "load.lisp" *load-truename*))
(let* ((args (uiop:command-line-arguments))
       (root (uiop:ensure-directory-pathname (or (first args) (error "Supply the Ollama output directory."))))
       (run (cl-pdfocr::read-json (merge-pathnames "run.json" root)))
       (pages (gethash "pages" run))
       (text (uiop:read-file-string (merge-pathnames "reading.md" root) :external-format :utf-8))
       (spans (cl-pdfocr::read-json (merge-pathnames "reading-spans.json" root))))
  (assert (= 2 (length pages) (length spans)))
  (assert (equal "needs-review" (gethash "status" run)))
  (assert (= 32 (gethash "max_new_tokens" (gethash "config" run))))
  (loop for page across pages for span across spans
        for metadata = (gethash "backend_response" page)
        do (assert (equal "partial" (gethash "status" page)))
           (assert (equal "length" (gethash "stop_reason" page)))
           (assert (= 32 (gethash "reported_generated_tokens" metadata)))
           (assert (eq yason:false (gethash "token_ids_available" metadata)))
           (assert (zerop (length (gethash "token_ids" page))))
           (assert (equal (gethash "markdown" page)
                          (subseq (gethash "raw" page) (gethash "source_start" page)
                                  (gethash "source_end" page))))
           (assert (equal (gethash "markdown" page)
                          (subseq text (gethash "output_start" span) (gethash "output_end" span)))))
  (assert (not (probe-file (merge-pathnames ".running" root))))
  (cl-pdfocr::write-json (or (second args) (merge-pathnames "validation.json" root))
    (cl-pdfocr::object "date" "2026-10-24" "runtime" (lisp-implementation-type)
      "runtime_version" (lisp-implementation-version)
      "inference" "External local Ollama; Common Lisp HTTP and orchestration"
      "model" (gethash "model" (gethash "config" run)) "pages" #(34 35)
      "dpi" 200 "reported_generated_tokens_per_page" 32 "token_ids_available" yason:false
      "page_status" "partial" "run_status" "needs-review" "body_and_reading_spans" "exact"
      "visual_budget" "service default; not independently verified"
      "quality_benchmark" yason:false))
  (format t "~&Verified two partial pages, exact body maps and explicit absence of token IDs: ~A~%" root))
