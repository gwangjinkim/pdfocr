;;; Explicit local ASDF setup; no user init, downloads, model loads or GPU startup.
(require :asdf)
(let* ((here (uiop:pathname-directory-pathname *load-truename*))
       (repository (uiop:pathname-parent-directory-pathname here))
       (cl-root (uiop:ensure-directory-pathname
                 (or (uiop:getenv "PDFOCR_CL_PROJECTS")
                     (merge-pathnames "projects/cl/" (user-homedir-pathname)))))
       (engine (merge-pathnames "cl-transformer-blocks/" cl-root)))
  (asdf:initialize-source-registry
   `(:source-registry (:directory ,here)
     (:directory ,(merge-pathnames "vendor-pdfrune/" repository))
     (:directory ,(merge-pathnames "cl-vlm/" cl-root))
     (:directory ,(merge-pathnames "cl-docling/" cl-root))
     (:directory ,engine) (:tree ,(merge-pathnames ".build/deps/" engine))
     (:tree ,(merge-pathnames "ocicl/" cl-root)) :ignore-inherited-configuration))
  (asdf:initialize-output-translations
   `(:output-translations
     (t (,(merge-pathnames "workspace/common-lisp/fasl/" repository) :implementation))
     :ignore-inherited-configuration))
  (asdf:load-system "cl-pdfocr"))
