(in-package #:cl-vlm)

(defparameter +adapter-artifact-kinds+
  '(:adapter :training-checkpoint :merged-model))

(defclass adapter-artifact ()
  ((kind :initarg :kind :reader adapter-artifact-kind)
   (location :initarg :location :reader %adapter-artifact-location)
   (format :initarg :format :reader adapter-artifact-format)
   (revision :initarg :revision :reader %adapter-artifact-revision)))

(defclass adapter-operation-request ()
  ((operation :initarg :operation :reader adapter-operation-request-operation)
   (destination :initarg :destination :reader %adapter-operation-request-destination)
   (payload :initarg :payload :reader adapter-operation-request-payload)
   (adapter-method :initarg :adapter-method
                   :reader adapter-operation-request-adapter-method)
   (optimizer :initarg :optimizer :reader adapter-operation-request-optimizer)
   (steps :initarg :steps :reader adapter-operation-request-steps)
   (image-count :initarg :image-count :reader adapter-operation-request-image-count)
   (context-length :initarg :context-length
                   :reader adapter-operation-request-context-length)
   (source-artifact :initarg :source-artifact
                    :reader adapter-operation-request-source-artifact)))

(defclass adapter-operation-result ()
  ((operation :initarg :operation :reader adapter-operation-result-operation)
   (artifacts :initarg :artifacts :reader %adapter-operation-result-artifacts)
   (steps-completed :initarg :steps-completed
                    :reader adapter-operation-result-steps-completed)))

(defgeneric prepare-adapter-operation (adapter request)
  (:documentation
   "Prepare owned model-specific state for one validated adapter operation."))

(defgeneric execute-adapter-operation (adapter prepared)
  (:documentation
   "Execute a prepared adapter operation and return an ADAPTER-OPERATION-RESULT."))

(defgeneric release-prepared-operation (adapter prepared)
  (:documentation
   "Release PREPARED exactly once after successful adapter-operation preparation."))

(defmethod prepare-adapter-operation ((adapter adapter) request)
  (declare (ignore adapter request))
  (contract-errorf "Adapter does not implement PREPARE-ADAPTER-OPERATION"))

(defmethod execute-adapter-operation ((adapter adapter) prepared)
  (declare (ignore adapter prepared))
  (contract-errorf "Adapter does not implement EXECUTE-ADAPTER-OPERATION"))

(defmethod release-prepared-operation ((adapter adapter) prepared)
  (declare (ignore adapter prepared))
  (contract-errorf "Adapter does not implement RELEASE-PREPARED-OPERATION"))

(defun make-adapter-artifact (kind location format revision)
  (unless (member kind +adapter-artifact-kinds+)
    (contract-errorf "Unknown adapter artifact kind"))
  (unless (keywordp format)
    (contract-errorf "Adapter artifact format must be a keyword"))
  (make-instance 'adapter-artifact
                 :kind kind
                 :location (checked-string location "Adapter artifact location")
                 :format format
                 :revision (checked-string revision "Adapter artifact revision")))

(defun adapter-artifact-location (artifact)
  (copy-seq (%adapter-artifact-location artifact)))

(defun adapter-artifact-revision (artifact)
  (copy-seq (%adapter-artifact-revision artifact)))

(defun check-zero-operation-fields
    (adapter-method optimizer steps image-count context-length payload label)
  (unless (and (null adapter-method) (null optimizer) (zerop steps)
               (zerop image-count) (zerop context-length) (null payload))
    (contract-errorf "~A does not accept training fields" label)))

(defun make-adapter-operation-request
    (operation destination
     &key payload adapter-method optimizer (steps 0) (image-count 0)
       (context-length 0) source-artifact)
  (unless (member operation +adapter-lifecycle-operations+)
    (contract-errorf "Unknown adapter lifecycle operation"))
  (unless (typep steps '(integer 0))
    (contract-errorf "Adapter operation steps must be a nonnegative integer"))
  (unless (typep image-count '(integer 0))
    (contract-errorf "Adapter operation image count must be nonnegative"))
  (unless (typep context-length '(integer 0))
    (contract-errorf "Adapter operation context length must be nonnegative"))
  (case operation
    ((:train-adapter :resume-adapter)
     (unless (and payload (keywordp adapter-method) (keywordp optimizer)
                  (plusp steps) (plusp context-length))
       (contract-errorf
        "Training operations require payload, method, optimizer, steps and context"))
     (if (eq operation :resume-adapter)
         (unless (and (typep source-artifact 'adapter-artifact)
                      (eq :training-checkpoint
                          (adapter-artifact-kind source-artifact)))
           (contract-errorf
            ":RESUME-ADAPTER requires a training-checkpoint source artifact"))
         (when source-artifact
           (contract-errorf ":TRAIN-ADAPTER does not accept a source artifact"))))
    (:save-adapter
     (check-zero-operation-fields adapter-method optimizer steps image-count
                                  context-length payload ":SAVE-ADAPTER")
     (when source-artifact
       (contract-errorf ":SAVE-ADAPTER does not accept a source artifact")))
    (:merge-adapter
     (check-zero-operation-fields adapter-method optimizer steps image-count
                                  context-length payload ":MERGE-ADAPTER")
     (unless (and (typep source-artifact 'adapter-artifact)
                  (eq :adapter (adapter-artifact-kind source-artifact)))
       (contract-errorf ":MERGE-ADAPTER requires an adapter source artifact"))))
  (make-instance 'adapter-operation-request
                 :operation operation
                 :destination (checked-string destination "Adapter operation destination")
                 :payload payload
                 :adapter-method adapter-method
                 :optimizer optimizer
                 :steps steps
                 :image-count image-count
                 :context-length context-length
                 :source-artifact source-artifact))

(defun adapter-operation-request-destination (request)
  (copy-seq (%adapter-operation-request-destination request)))

(defun expected-artifact-kind (operation)
  (ecase operation
    ((:train-adapter :resume-adapter) :training-checkpoint)
    (:save-adapter :adapter)
    (:merge-adapter :merged-model)))

(defun make-adapter-operation-result (operation artifacts &key (steps-completed 0))
  (unless (member operation +adapter-lifecycle-operations+)
    (contract-errorf "Unknown adapter lifecycle operation"))
  (unless (typep steps-completed '(integer 0))
    (contract-errorf "Completed step count must be nonnegative"))
  (let ((artifacts (coerce artifacts 'vector)))
    (unless (and (= 1 (length artifacts))
                 (typep (aref artifacts 0) 'adapter-artifact)
                 (eq (expected-artifact-kind operation)
                     (adapter-artifact-kind (aref artifacts 0))))
      (contract-errorf "Adapter operation returned the wrong artifact contract"))
    (when (and (member operation '(:save-adapter :merge-adapter))
               (plusp steps-completed))
      (contract-errorf "Non-training operations cannot report training steps"))
    (make-instance 'adapter-operation-result
                   :operation operation
                   :artifacts (copy-seq artifacts)
                   :steps-completed steps-completed)))

(defun adapter-operation-result-artifacts (result)
  (copy-seq (%adapter-operation-result-artifacts result)))

(defun validate-adapter-operation (capabilities request)
  (let* ((operation (adapter-operation-request-operation request))
         (lifecycle (model-capabilities-adapter-lifecycle capabilities)))
    (unless (supports-operation-p capabilities operation)
      (contract-errorf "Adapter does not declare ~S support" operation))
    (unless (typep lifecycle 'adapter-lifecycle-capabilities)
      (contract-errorf "Adapter does not declare lifecycle capabilities"))
    (when (member operation '(:train-adapter :resume-adapter))
      (unless (member (adapter-operation-request-adapter-method request)
                      (%adapter-lifecycle-capabilities-adapter-methods lifecycle))
        (contract-errorf "Adapter method is not declared"))
      (unless (member (adapter-operation-request-optimizer request)
                      (%adapter-lifecycle-capabilities-optimizers lifecycle))
        (contract-errorf "Optimizer is not declared"))
      (when (> (adapter-operation-request-image-count request)
               (adapter-lifecycle-capabilities-max-images-per-example lifecycle))
        (contract-errorf "Training request exceeds the image limit"))
      (when (> (adapter-operation-request-context-length request)
               (adapter-lifecycle-capabilities-max-context-length lifecycle))
        (contract-errorf "Training request exceeds the context limit")))))

(defun validate-adapter-operation-result (request result)
  (unless (eq (adapter-operation-request-operation request)
              (adapter-operation-result-operation result))
    (contract-errorf "Adapter operation result names another operation"))
  (let ((artifacts (%adapter-operation-result-artifacts result)))
    (unless (and (vectorp artifacts)
                 (= 1 (length artifacts))
                 (typep (aref artifacts 0) 'adapter-artifact)
                 (eq (expected-artifact-kind
                      (adapter-operation-request-operation request))
                     (adapter-artifact-kind (aref artifacts 0))))
      (contract-errorf "Adapter operation result violates its artifact contract")))
  (unless (and (typep (adapter-operation-result-steps-completed result)
                      '(integer 0))
               (<= (adapter-operation-result-steps-completed result)
                   (adapter-operation-request-steps request)))
    (contract-errorf "Adapter operation exceeded its requested steps")))

(defun perform-adapter-operation (adapter request)
  "Validate, prepare, execute and release one bounded adapter lifecycle operation.

DESTINATION is an abstract identity. The implementing adapter must create it
without replacing an existing artifact; cl-vlm performs no filesystem work."
  (unless (typep adapter 'adapter)
    (contract-errorf "Expected a VLM adapter"))
  (unless (typep request 'adapter-operation-request)
    (contract-errorf "Expected an adapter operation request"))
  (let ((manifest (adapter-manifest adapter)))
    (unless (typep manifest 'model-manifest)
      (contract-errorf "ADAPTER-MANIFEST must return a model manifest"))
    (validate-adapter-operation (model-manifest-capabilities manifest) request)
    (let ((prepared nil)
          (prepared-p nil))
      (unwind-protect
           (progn
             (setf prepared (prepare-adapter-operation adapter request)
                   prepared-p t)
             (let ((result (execute-adapter-operation adapter prepared)))
               (unless (typep result 'adapter-operation-result)
                 (contract-errorf
                  "EXECUTE-ADAPTER-OPERATION must return an adapter operation result"))
               (validate-adapter-operation-result request result)
               result))
        (when prepared-p
          (release-prepared-operation adapter prepared))))))
