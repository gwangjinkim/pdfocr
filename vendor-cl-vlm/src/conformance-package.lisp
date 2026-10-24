(defpackage #:cl-vlm-conformance
  (:use #:cl)
  (:nicknames #:vlm-conformance)
  (:export
   #:conformance-error #:conformance-error-message
   #:manifest-equal-p #:operation-result-equal-p
   #:check-generation-adapter #:check-adapter-operation))
