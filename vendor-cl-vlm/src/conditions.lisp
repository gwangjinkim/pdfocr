(in-package #:cl-vlm)

(define-condition vlm-error (error)
  ((message :initarg :message :reader vlm-error-message))
  (:report (lambda (condition stream)
             (write-string (vlm-error-message condition) stream))))

(define-condition contract-error (vlm-error) ())

(defun contract-errorf (control &rest arguments)
  (error 'contract-error :message (apply #'format nil control arguments)))
