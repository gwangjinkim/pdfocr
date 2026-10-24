(in-package #:cl-pdfocr)

(defun call-with-gemma4-adapter (checkpoint lock function &key (device :gpu))
  "Borrow the pinned native E2B adapter within a bounded model/backend lifetime.
This is not Gemma4 12B and retains cl-docling's qualified 70-token image processor."
  (tb:with-resource (backend (tb:make-backend :device device))
    (let ((baseline (getf (tb:backend-memory backend) :handles)) (result nil))
      (tb:with-resource (model (docling:load-gemma4-vision-model checkpoint :lock-file lock :backend backend))
        (setf result (funcall function (docling:make-gemma4-vlm-adapter model))))
      (unless (= baseline (getf (tb:backend-memory backend) :handles))
        (error "Native tensor handles did not return to baseline."))
      result)))

(defun convert-native-pdf (source out checkpoint lock &key pages (dpi 200)
                                                         (max-new-tokens 2048) (device :gpu) resume)
  (call-with-gemma4-adapter checkpoint lock
    (lambda (adapter)
      (convert-pdf source out adapter :pages pages :dpi dpi
                   :max-new-tokens max-new-tokens :resume resume))
    :device device))
