(in-package #:cl-vlm-conformance)

(define-condition conformance-error (error)
  ((message :initarg :message :reader conformance-error-message))
  (:report (lambda (condition stream)
             (write-string (conformance-error-message condition) stream))))

(define-condition injected-generation-failure (error) ())

(defun conformance-errorf (control &rest arguments)
  (error 'conformance-error :message (apply #'format nil control arguments)))

(defun same-sequence-p (left right)
  (equal (coerce left 'list) (coerce right 'list)))

(defun lifecycle-capabilities-equal-p (left right)
  (or (and (null left) (null right))
      (and (typep left 'cl-vlm:adapter-lifecycle-capabilities)
           (typep right 'cl-vlm:adapter-lifecycle-capabilities)
           (same-sequence-p
            (cl-vlm:adapter-lifecycle-capabilities-adapter-methods left)
            (cl-vlm:adapter-lifecycle-capabilities-adapter-methods right))
           (same-sequence-p
            (cl-vlm:adapter-lifecycle-capabilities-optimizers left)
            (cl-vlm:adapter-lifecycle-capabilities-optimizers right))
           (= (cl-vlm:adapter-lifecycle-capabilities-max-images-per-example left)
              (cl-vlm:adapter-lifecycle-capabilities-max-images-per-example right))
           (= (cl-vlm:adapter-lifecycle-capabilities-max-context-length left)
              (cl-vlm:adapter-lifecycle-capabilities-max-context-length right)))))

(defun capabilities-equal-p (left right)
  (and (typep left 'cl-vlm:model-capabilities)
       (typep right 'cl-vlm:model-capabilities)
       (same-sequence-p (cl-vlm:model-capabilities-modalities left)
                        (cl-vlm:model-capabilities-modalities right))
       (same-sequence-p (cl-vlm:model-capabilities-operations left)
                        (cl-vlm:model-capabilities-operations right))
       (same-sequence-p (cl-vlm:model-capabilities-dtypes left)
                        (cl-vlm:model-capabilities-dtypes right))
       (= (cl-vlm:model-capabilities-context-length left)
          (cl-vlm:model-capabilities-context-length right))
       (= (cl-vlm:model-capabilities-max-images left)
          (cl-vlm:model-capabilities-max-images right))
       (= (cl-vlm:model-capabilities-max-batch-size left)
          (cl-vlm:model-capabilities-max-batch-size right))
       (lifecycle-capabilities-equal-p
        (cl-vlm:model-capabilities-adapter-lifecycle left)
        (cl-vlm:model-capabilities-adapter-lifecycle right))))

(defun manifest-equal-p (left right)
  "Return true when two manifests describe the same exact qualified contract."
  (and (typep left 'cl-vlm:model-manifest)
       (typep right 'cl-vlm:model-manifest)
       (eq (cl-vlm:model-manifest-family left)
           (cl-vlm:model-manifest-family right))
       (equal (cl-vlm:model-manifest-architecture left)
              (cl-vlm:model-manifest-architecture right))
       (equal (cl-vlm:model-manifest-checkpoint left)
              (cl-vlm:model-manifest-checkpoint right))
       (equal (cl-vlm:model-manifest-revision left)
              (cl-vlm:model-manifest-revision right))
       (capabilities-equal-p
        (cl-vlm:model-manifest-capabilities left)
        (cl-vlm:model-manifest-capabilities right))))

(defun result-equal-p (left right)
  (and (typep left 'cl-vlm:generation-result)
       (typep right 'cl-vlm:generation-result)
       (equal (cl-vlm:generation-result-text left)
              (cl-vlm:generation-result-text right))
       (equalp (cl-vlm:generation-result-token-ids left)
               (cl-vlm:generation-result-token-ids right))
       (eq (cl-vlm:generation-result-stop-reason left)
           (cl-vlm:generation-result-stop-reason right))))

(defun artifact-equal-p (left right)
  (and (typep left 'cl-vlm:adapter-artifact)
       (typep right 'cl-vlm:adapter-artifact)
       (eq (cl-vlm:adapter-artifact-kind left)
           (cl-vlm:adapter-artifact-kind right))
       (equal (cl-vlm:adapter-artifact-location left)
              (cl-vlm:adapter-artifact-location right))
       (eq (cl-vlm:adapter-artifact-format left)
           (cl-vlm:adapter-artifact-format right))
       (equal (cl-vlm:adapter-artifact-revision left)
              (cl-vlm:adapter-artifact-revision right))))

(defun operation-result-equal-p (left right)
  "Return true when two adapter-operation results have exact artifact identities."
  (and (typep left 'cl-vlm:adapter-operation-result)
       (typep right 'cl-vlm:adapter-operation-result)
       (eq (cl-vlm:adapter-operation-result-operation left)
           (cl-vlm:adapter-operation-result-operation right))
       (= (cl-vlm:adapter-operation-result-steps-completed left)
          (cl-vlm:adapter-operation-result-steps-completed right))
       (let ((left-artifacts
               (cl-vlm:adapter-operation-result-artifacts left))
             (right-artifacts
               (cl-vlm:adapter-operation-result-artifacts right)))
         (and (= (length left-artifacts) (length right-artifacts))
              (loop for left-artifact across left-artifacts
                    for right-artifact across right-artifacts
                    always (artifact-equal-p left-artifact right-artifact))))))

(defclass conformance-probe (cl-vlm:adapter)
  ((delegate :initarg :delegate :reader probe-delegate)
   (inject-failure-p :initarg :inject-failure-p :reader probe-inject-failure-p)
   (manifest-count :initform 0 :accessor probe-manifest-count)
   (prepare-count :initform 0 :accessor probe-prepare-count)
   (generate-count :initform 0 :accessor probe-generate-count)
   (release-count :initform 0 :accessor probe-release-count)
   (prepared :initform nil :accessor probe-prepared)
   (operation-prepare-count :initform 0 :accessor probe-operation-prepare-count)
   (operation-execute-count :initform 0 :accessor probe-operation-execute-count)
   (operation-release-count :initform 0 :accessor probe-operation-release-count)
   (operation-prepared :initform nil :accessor probe-operation-prepared)))

(defmethod cl-vlm:adapter-manifest ((probe conformance-probe))
  (incf (probe-manifest-count probe))
  (cl-vlm:adapter-manifest (probe-delegate probe)))

(defmethod cl-vlm:prepare-generation
    ((probe conformance-probe) messages max-new-tokens)
  (incf (probe-prepare-count probe))
  (let ((prepared
          (cl-vlm:prepare-generation
           (probe-delegate probe) messages max-new-tokens)))
    (setf (probe-prepared probe) prepared)
    prepared))

(defmethod cl-vlm:generate-prepared ((probe conformance-probe) prepared)
  (incf (probe-generate-count probe))
  (when (probe-inject-failure-p probe)
    (error 'injected-generation-failure))
  (cl-vlm:generate-prepared (probe-delegate probe) prepared))

(defmethod cl-vlm:release-prepared ((probe conformance-probe) prepared)
  (incf (probe-release-count probe))
  (cl-vlm:release-prepared (probe-delegate probe) prepared))

(defmethod cl-vlm:prepare-adapter-operation
    ((probe conformance-probe) request)
  (incf (probe-operation-prepare-count probe))
  (let ((prepared
          (cl-vlm:prepare-adapter-operation (probe-delegate probe) request)))
    (setf (probe-operation-prepared probe) prepared)
    prepared))

(defmethod cl-vlm:execute-adapter-operation
    ((probe conformance-probe) prepared)
  (incf (probe-operation-execute-count probe))
  (when (probe-inject-failure-p probe)
    (error 'injected-generation-failure))
  (cl-vlm:execute-adapter-operation (probe-delegate probe) prepared))

(defmethod cl-vlm:release-prepared-operation
    ((probe conformance-probe) prepared)
  (incf (probe-operation-release-count probe))
  (cl-vlm:release-prepared-operation (probe-delegate probe) prepared))

(defun check-probe-counts (probe label)
  (unless (and (= 1 (probe-manifest-count probe))
               (= 1 (probe-prepare-count probe))
               (= 1 (probe-generate-count probe))
               (= 1 (probe-release-count probe)))
    (conformance-errorf
     "~A lifecycle was manifest=~D prepare=~D generate=~D release=~D, expected 1 each"
     label (probe-manifest-count probe) (probe-prepare-count probe)
     (probe-generate-count probe) (probe-release-count probe))))

(defun check-release-state (probe released-p label)
  (when (and released-p
             (not (funcall released-p (probe-prepared probe))))
    (conformance-errorf "~A prepared request was not released" label)))

(defun check-operation-probe-counts (probe label)
  (unless (and (= 1 (probe-manifest-count probe))
               (= 1 (probe-operation-prepare-count probe))
               (= 1 (probe-operation-execute-count probe))
               (= 1 (probe-operation-release-count probe)))
    (conformance-errorf
     "~A lifecycle was manifest=~D prepare=~D execute=~D release=~D, expected 1 each"
     label (probe-manifest-count probe) (probe-operation-prepare-count probe)
     (probe-operation-execute-count probe) (probe-operation-release-count probe))))

(defun check-operation-release-state (probe released-p label)
  (when (and released-p
             (not (funcall released-p (probe-operation-prepared probe))))
    (conformance-errorf "~A prepared operation was not released" label)))

(defun check-generation-adapter
    (adapter messages expected-manifest expected-result
     &key (max-new-tokens 128) prepared-released-p)
  "Check exact identity/result transport and success/failure cleanup for ADAPTER.

EXPECTED-MANIFEST and EXPECTED-RESULT must be independently fixed expectations.
PREPARED-RELEASED-P, when supplied, receives each released model-specific prepared
object. The adapter runs once normally and once with failure injected immediately
before model generation. The successful generation result is returned."
  (unless (typep adapter 'cl-vlm:adapter)
    (conformance-errorf "Expected a cl-vlm adapter"))
  (unless (typep expected-manifest 'cl-vlm:model-manifest)
    (conformance-errorf "Expected a cl-vlm model manifest"))
  (unless (typep expected-result 'cl-vlm:generation-result)
    (conformance-errorf "Expected a cl-vlm generation result"))
  (when (and prepared-released-p (not (functionp prepared-released-p)))
    (conformance-errorf "PREPARED-RELEASED-P must be a function"))
  (unless (manifest-equal-p (cl-vlm:adapter-manifest adapter) expected-manifest)
    (conformance-errorf "Adapter manifest differs from the expected exact contract"))
  (let* ((success (make-instance 'conformance-probe
                                 :delegate adapter :inject-failure-p nil))
         (result (cl-vlm:generate success messages :max-new-tokens max-new-tokens)))
    (check-probe-counts success "Successful generation")
    (check-release-state success prepared-released-p "Successful generation")
    (unless (result-equal-p result expected-result)
      (conformance-errorf "Generation result differs from the exact expectation"))
    (let ((failure (make-instance 'conformance-probe
                                  :delegate adapter :inject-failure-p t))
          (observed-p nil))
      (handler-case
          (cl-vlm:generate failure messages :max-new-tokens max-new-tokens)
        (injected-generation-failure () (setf observed-p t)))
      (unless observed-p
        (conformance-errorf "Injected generation failure was not observed"))
      (check-probe-counts failure "Injected-failure generation")
      (check-release-state failure prepared-released-p "Injected-failure generation"))
    result))

(defun check-adapter-operation
    (adapter request expected-manifest expected-result &key prepared-released-p)
  "Check exact manifest/artifact transport and operation success/failure cleanup."
  (unless (typep adapter 'cl-vlm:adapter)
    (conformance-errorf "Expected a cl-vlm adapter"))
  (unless (typep request 'cl-vlm:adapter-operation-request)
    (conformance-errorf "Expected an adapter operation request"))
  (unless (typep expected-manifest 'cl-vlm:model-manifest)
    (conformance-errorf "Expected a cl-vlm model manifest"))
  (unless (typep expected-result 'cl-vlm:adapter-operation-result)
    (conformance-errorf "Expected an adapter operation result"))
  (when (and prepared-released-p (not (functionp prepared-released-p)))
    (conformance-errorf "PREPARED-RELEASED-P must be a function"))
  (unless (manifest-equal-p (cl-vlm:adapter-manifest adapter) expected-manifest)
    (conformance-errorf "Adapter manifest differs from the expected exact contract"))
  ;; Failure runs first so an adapter can enforce create-only destinations. The
  ;; injected failure occurs before delegate execution and therefore publishes
  ;; nothing; the following success run may use the same exact request.
  (let ((failure (make-instance 'conformance-probe
                                :delegate adapter :inject-failure-p t))
        (observed-p nil))
    (handler-case
        (cl-vlm:perform-adapter-operation failure request)
      (injected-generation-failure () (setf observed-p t)))
    (unless observed-p
      (conformance-errorf "Injected adapter-operation failure was not observed"))
    (check-operation-probe-counts failure "Injected-failure adapter operation")
    (check-operation-release-state
     failure prepared-released-p "Injected-failure adapter operation"))
  (let* ((success (make-instance 'conformance-probe
                                 :delegate adapter :inject-failure-p nil))
         (result (cl-vlm:perform-adapter-operation success request)))
    (check-operation-probe-counts success "Successful adapter operation")
    (check-operation-release-state
     success prepared-released-p "Successful adapter operation")
    (unless (operation-result-equal-p result expected-result)
      (conformance-errorf
       "Adapter operation result differs from the exact expectation"))
    result))
