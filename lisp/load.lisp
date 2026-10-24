;;; Explicit local ASDF setup; no user init, downloads, model loads or GPU startup.
(require :asdf)
(let* ((here (uiop:pathname-directory-pathname *load-truename*))
       (repository (uiop:pathname-parent-directory-pathname here))
       (cl-root (uiop:ensure-directory-pathname
                 (or (uiop:getenv "PDFOCR_CL_PROJECTS")
                     (merge-pathnames "projects/cl/" (user-homedir-pathname)))))
       (engine (merge-pathnames "cl-transformer-blocks/" cl-root))
       (bundled-vlm (merge-pathnames "vendor-cl-vlm/" repository))
       (local-deps (merge-pathnames "ocicl/" repository)))
  (asdf:initialize-source-registry
   `(:source-registry (:directory ,here)
     (:directory ,(merge-pathnames "vendor-pdfrune/" repository))
     (:directory ,(if (probe-file (merge-pathnames "cl-vlm.asd" bundled-vlm))
                      bundled-vlm (merge-pathnames "cl-vlm/" cl-root)))
     (:directory ,(merge-pathnames "cl-docling/" cl-root))
     (:directory ,engine) (:tree ,(merge-pathnames ".build/deps/" engine))
     (:tree ,(if (probe-file local-deps) local-deps (merge-pathnames "ocicl/" cl-root)))
     :ignore-inherited-configuration))
  (asdf:initialize-output-translations
   `(:output-translations
     (t (,(merge-pathnames "workspace/common-lisp/fasl/" repository) :implementation))
     :ignore-inherited-configuration))
  (asdf:load-system "cl-pdfocr"))
