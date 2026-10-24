(load (merge-pathnames "load.lisp" *load-truename*))
(let ((root (uiop:pathname-parent-directory-pathname
              (uiop:pathname-directory-pathname *load-truename*))))
  (dolist (dpi '(200 400))
    (cl-pdfocr:prepare-pdf (or (uiop:getenv "PDFOCR_TEST_PDF") (error "Set PDFOCR_TEST_PDF."))
      (merge-pathnames (format nil "workspace/common-lisp-render-~D/" dpi) root)
      :pages '(34 35) :dpi dpi :resume t)))
