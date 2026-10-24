;;; Explicit two-page service integration. Reuse prepared scans; never start Ollama.
(load (merge-pathnames "load.lisp" *load-truename*))
(asdf:load-system "cl-pdfocr/ollama")
(let* ((prepared (or (uiop:getenv "PDFOCR_TEST_PREPARED") (error "Set PDFOCR_TEST_PREPARED.")))
       (out (uiop:ensure-directory-pathname
              (or (uiop:getenv "PDFOCR_TEST_OUT") (error "Set PDFOCR_TEST_OUT."))))
       (model (or (uiop:getenv "PDFOCR_TEST_MODEL") "gemma3:12b"))
       (adapter (cl-pdfocr:make-ollama-adapter model)))
  (cl-pdfocr:recognize-prepared prepared out adapter :max-new-tokens 32 :resume t)
  (let* ((run (cl-pdfocr::read-json (merge-pathnames "run.json" out)))
         (pages (gethash "pages" run)))
    (assert (= 2 (length pages)))
    (loop for page across pages
          for metadata = (gethash "backend_response" page)
          do (assert (member (gethash "status" page) '("ok" "partial") :test #'equal))
             (assert (plusp (length (gethash "raw" page))))
             (assert (zerop (length (gethash "token_ids" page))))
             (assert (eq yason:false (gethash "token_ids_available" metadata)))
             (assert (plusp (gethash "reported_generated_tokens" metadata)))
             (format t "~&Page ~D: ~A; ~D service-reported tokens; no token IDs.~%"
                     (gethash "page" page) (gethash "status" page)
                     (gethash "reported_generated_tokens" metadata))))
  (format t "~&Ollama integration finished: ~A~%" out))
