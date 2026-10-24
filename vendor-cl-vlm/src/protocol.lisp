(in-package #:cl-vlm)

(defclass adapter () ())

(defclass generation-result ()
  ((text :initarg :text :reader %generation-result-text)
   (token-ids :initarg :token-ids :reader %generation-result-token-ids)
   (stop-reason :initarg :stop-reason :reader generation-result-stop-reason)))

(defgeneric adapter-manifest (adapter)
  (:documentation "Return the immutable, exact manifest implemented by ADAPTER."))

(defgeneric prepare-generation (adapter messages max-new-tokens)
  (:documentation "Prepare an owned model-specific request from normalized messages."))

(defgeneric generate-prepared (adapter prepared)
  (:documentation "Run bounded generation and return a GENERATION-RESULT."))

(defgeneric generate-prepared-batch (adapter prepared)
  (:documentation "Run one native batch of prepared independent requests and return a result vector."))

(defgeneric release-prepared (adapter prepared)
  (:documentation "Release PREPARED. Called exactly once after successful preparation."))

(defmethod adapter-manifest ((adapter adapter))
  (declare (ignore adapter))
  (contract-errorf "Adapter does not implement ADAPTER-MANIFEST"))

(defmethod prepare-generation ((adapter adapter) messages max-new-tokens)
  (declare (ignore adapter messages max-new-tokens))
  (contract-errorf "Adapter does not implement PREPARE-GENERATION"))

(defmethod generate-prepared ((adapter adapter) prepared)
  (declare (ignore adapter prepared))
  (contract-errorf "Adapter does not implement GENERATE-PREPARED"))

(defmethod generate-prepared-batch ((adapter adapter) prepared)
  (declare (ignore adapter prepared))
  (contract-errorf "Adapter does not implement GENERATE-PREPARED-BATCH"))

(defmethod release-prepared ((adapter adapter) prepared)
  (declare (ignore adapter prepared))
  (contract-errorf "Adapter does not implement RELEASE-PREPARED"))

(defun make-generation-result (text token-ids stop-reason)
  (unless (and (stringp text) (not (find #\Null text)))
    (contract-errorf "Generated text must be a string without NUL"))
  (unless (member stop-reason '(:eos :length :stop))
    (contract-errorf "Stop reason must be :EOS, :LENGTH or :STOP"))
  (let* ((values (coerce token-ids 'vector))
         (copy (make-array (length values) :element-type '(unsigned-byte 32))))
    (dotimes (index (length values))
      (let ((value (aref values index)))
        (unless (typep value '(unsigned-byte 32))
          (contract-errorf "Token IDs must be unsigned 32-bit integers"))
        (setf (aref copy index) value)))
    (make-instance 'generation-result :text (copy-seq text)
                                      :token-ids copy :stop-reason stop-reason)))

(defun generation-result-text (result)
  (copy-seq (%generation-result-text result)))

(defun generation-result-token-ids (result)
  (copy-seq (%generation-result-token-ids result)))

(defun request-image-count (messages)
  (loop for message across messages
        sum (count-if (lambda (part) (typep part 'image-part))
                      (%message-parts message))))

(defun validate-request-capabilities (capabilities messages)
  (unless (supports-operation-p capabilities :generate)
    (contract-errorf "Adapter does not declare :GENERATE support"))
  (let ((image-count (request-image-count messages)))
    (when (and (plusp image-count)
               (not (supports-modality-p capabilities :image)))
      (contract-errorf "Request contains images but adapter does not support :IMAGE"))
    (when (> image-count (model-capabilities-max-images capabilities))
      (contract-errorf "Request contains ~D images; adapter permits at most ~D"
                       image-count (model-capabilities-max-images capabilities)))))

(defun generate (adapter messages &key (max-new-tokens 128))
  "Validate, prepare, generate and always release a successfully prepared request."
  (unless (typep adapter 'adapter)
    (contract-errorf "Expected a VLM adapter"))
  (unless (typep max-new-tokens '(integer 1))
    (contract-errorf "MAX-NEW-TOKENS must be a positive integer"))
  (let* ((messages (normalize-messages messages))
         (manifest (adapter-manifest adapter)))
    (unless (typep manifest 'model-manifest)
      (contract-errorf "ADAPTER-MANIFEST must return a model manifest"))
    (validate-request-capabilities (model-manifest-capabilities manifest) messages)
    (let ((prepared nil)
          (prepared-p nil))
      (unwind-protect
           (progn
             (setf prepared (prepare-generation adapter messages max-new-tokens)
                   prepared-p t)
             (let ((result (generate-prepared adapter prepared)))
               (unless (typep result 'generation-result)
                 (contract-errorf "GENERATE-PREPARED must return a generation result"))
               result))
        (when prepared-p
          (release-prepared adapter prepared))))))

(defun generation-budgets (value count)
  (let ((budgets (if (typep value '(integer 1))
                     (make-array count :initial-element value)
                     (coerce value 'vector))))
    (unless (and (= (length budgets) count)
                 (every (lambda (budget) (typep budget '(integer 1))) budgets))
      (contract-errorf
       "MAX-NEW-TOKENS must be a positive integer or one positive integer per request"))
    budgets))

(defun generate-batch (adapter requests &key (max-new-tokens 128))
  "Validate and run one native batch of independent generation requests.
REQUESTS is a nonempty sequence of ordinary message sequences. MAX-NEW-TOKENS is
one positive integer or a same-length sequence. Every prepared request is released
exactly once after successful preparation, including exceptional batch execution."
  (unless (typep adapter 'adapter)
    (contract-errorf "Expected a VLM adapter"))
  (let* ((requests (coerce requests 'vector))
         (count (length requests))
         (manifest (adapter-manifest adapter)))
    (unless (plusp count)
      (contract-errorf "Generation batch must contain at least one request"))
    (unless (typep manifest 'model-manifest)
      (contract-errorf "ADAPTER-MANIFEST must return a model manifest"))
    (let ((capabilities (model-manifest-capabilities manifest)))
      (when (> count (model-capabilities-max-batch-size capabilities))
        (contract-errorf "Generation batch contains ~D requests; adapter permits at most ~D"
                         count (model-capabilities-max-batch-size capabilities)))
      (let ((normalized (make-array count))
            (budgets (generation-budgets max-new-tokens count))
            (prepared (make-array count :initial-element nil))
            (prepared-count 0))
        (dotimes (index count)
          (setf (aref normalized index) (normalize-messages (aref requests index)))
          (validate-request-capabilities capabilities (aref normalized index)))
        (unwind-protect
             (progn
               (dotimes (index count)
                 (setf (aref prepared index)
                       (prepare-generation adapter (aref normalized index)
                                           (aref budgets index)))
                 (incf prepared-count))
               (let ((results (generate-prepared-batch adapter prepared)))
                 (unless (and (vectorp results) (= (length results) count)
                              (every (lambda (result) (typep result 'generation-result))
                                     results))
                   (contract-errorf
                    "GENERATE-PREPARED-BATCH must return one generation result per request"))
                 results))
          (dotimes (index prepared-count)
            (release-prepared adapter (aref prepared index))))))))
