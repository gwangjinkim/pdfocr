;;; Explicit two-page native integration test using caller-selected public PDF.
(load (merge-pathnames "load.lisp" *load-truename*))
(asdf:load-system "cl-pdfocr/native")
(let* ((pdf (or (uiop:getenv "PDFOCR_TEST_PDF") (error "Set PDFOCR_TEST_PDF explicitly.")))
       (cl-root (uiop:ensure-directory-pathname
                 (or (uiop:getenv "PDFOCR_CL_PROJECTS")
                     (merge-pathnames "projects/cl/" (user-homedir-pathname)))))
       (docling-root (merge-pathnames "cl-docling/" cl-root))
       (out (uiop:ensure-directory-pathname
              (or (uiop:getenv "PDFOCR_TEST_OUT")
                  (merge-pathnames "workspace/common-lisp-native-smoke/"
                    (uiop:pathname-parent-directory-pathname
                      (uiop:pathname-directory-pathname *load-truename*)))))))
  (cl-pdfocr:convert-native-pdf pdf out
    (merge-pathnames ".build/gemma4-e2b/" docling-root)
    (merge-pathnames "references/gemma4-e2b.lock.json" docling-root)
    :pages '(34 35) :dpi 200 :max-new-tokens 128 :device :gpu :resume t)
  (let ((run (cl-pdfocr::read-json (merge-pathnames "ocr/run.json" out))))
    (loop for page across (gethash "pages" run)
          do (assert (member (gethash "status" page) '("ok" "partial") :test #'equal))
             (assert (plusp (length (gethash "token_ids" page))))))
  (format t "~&Native integration finished: ~A~%" out))
