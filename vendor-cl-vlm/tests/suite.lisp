(defpackage #:cl-vlm-tests
  (:use #:cl)
  (:export #:run-tests))

(in-package #:cl-vlm-tests)

(defvar *checks* 0)

(defmacro check (form)
  `(progn
     (incf *checks*)
     (unless ,form
       (error "Check failed: ~S" ',form))))

(defmacro signals-contract-error (&body body)
  `(check (handler-case (progn ,@body nil)
            (cl-vlm:contract-error () t))))

(defclass mock-adapter (cl-vlm:adapter)
  ((manifest :initarg :manifest :reader mock-manifest)
   (released :initform 0 :accessor mock-released)
   (fail-p :initarg :fail-p :initform nil :reader mock-fail-p)
   (prepare-fail-p :initarg :prepare-fail-p :initform nil
                   :reader mock-prepare-fail-p)
   (generation-prepare-count :initform 0 :accessor mock-generation-prepare-count)
   (generation-prepare-fail-at :initarg :generation-prepare-fail-at :initform nil
                               :reader mock-generation-prepare-fail-at)
   (operation-result :initarg :operation-result :initform nil
                     :reader mock-operation-result)
   (operation-prepare-count :initform 0 :accessor mock-operation-prepare-count)
   (operation-execute-count :initform 0 :accessor mock-operation-execute-count)
   (operation-release-count :initform 0 :accessor mock-operation-release-count)))

(defmethod cl-vlm:adapter-manifest ((adapter mock-adapter))
  (mock-manifest adapter))

(defmethod cl-vlm:prepare-generation ((adapter mock-adapter) messages max-new-tokens)
  (incf (mock-generation-prepare-count adapter))
  (when (eql (mock-generation-prepare-count adapter)
             (mock-generation-prepare-fail-at adapter))
    (error "Injected generation preparation failure"))
  (list :messages messages :budget max-new-tokens))

(defmethod cl-vlm:generate-prepared ((adapter mock-adapter) prepared)
  (when (mock-fail-p adapter)
    (error "Injected adapter failure"))
  (check (= 7 (getf prepared :budget)))
  (cl-vlm:make-generation-result "ok" #(10 11) :eos))

(defmethod cl-vlm:generate-prepared-batch ((adapter mock-adapter) prepared)
  (when (mock-fail-p adapter)
    (error "Injected batched adapter failure"))
  (map 'vector
       (lambda (request)
         (cl-vlm:make-generation-result
          (format nil "ok-~D" (getf request :budget))
          (vector (getf request :budget)) :length))
       prepared))

(defmethod cl-vlm:release-prepared ((adapter mock-adapter) prepared)
  (declare (ignore prepared))
  (incf (mock-released adapter)))

(defmethod cl-vlm:prepare-adapter-operation
    ((adapter mock-adapter) request)
  (incf (mock-operation-prepare-count adapter))
  (when (mock-prepare-fail-p adapter)
    (error "Injected adapter-operation preparation failure"))
  (list :request request))

(defmethod cl-vlm:execute-adapter-operation
    ((adapter mock-adapter) prepared)
  (declare (ignore prepared))
  (incf (mock-operation-execute-count adapter))
  (when (mock-fail-p adapter)
    (error "Injected adapter-operation failure"))
  (mock-operation-result adapter))

(defmethod cl-vlm:release-prepared-operation
    ((adapter mock-adapter) prepared)
  (declare (ignore prepared))
  (incf (mock-operation-release-count adapter)))

(defun make-mock-manifest (&key (modalities '(:text :image)) (operations '(:generate))
                                (max-images nil max-images-p) (max-batch-size 1) lifecycle)
  (cl-vlm:make-model-manifest
   :family :mock
   :architecture "MockForConditionalGeneration"
   :checkpoint "example/mock"
   :revision "0123456789abcdef"
   :capabilities
   (cl-vlm:make-model-capabilities
    :modalities modalities :operations operations :dtypes '(:fp32)
    :context-length 128
    :max-images (if max-images-p max-images (if (member :image modalities) 1 0))
    :max-batch-size max-batch-size
    :adapter-lifecycle lifecycle)))

(defun test-content ()
  (let* ((text (cl-vlm:make-text-part "describe"))
         (image (cl-vlm:make-image-part #P"page.png" :media-type "image/png"))
         (message (cl-vlm:make-message :user (list image text)))
         (parts (cl-vlm:message-parts message)))
    (check (eq :user (cl-vlm:message-role message)))
    (check (= 2 (length parts)))
    (check (equal "describe" (cl-vlm:text-part-text (aref parts 1))))
    (setf (aref parts 0) text)
    (check (typep (aref (cl-vlm:message-parts message) 0) 'cl-vlm:image-part))
    (signals-contract-error (cl-vlm:make-message :tool (list text)))
    (signals-contract-error (cl-vlm:make-text-part ""))))

(defun test-manifest ()
  (let* ((manifest (make-mock-manifest))
         (capabilities (cl-vlm:model-manifest-capabilities manifest)))
    (check (eq :mock (cl-vlm:model-manifest-family manifest)))
    (check (cl-vlm:supports-modality-p capabilities :image))
    (check (cl-vlm:supports-operation-p capabilities :generate))
    (check (= 1 (cl-vlm:model-capabilities-max-images capabilities)))
    (check (= 1 (cl-vlm:model-capabilities-max-batch-size capabilities))))
  (signals-contract-error
    (cl-vlm:make-model-capabilities
     :modalities '(:image) :operations '(:generate) :dtypes '(:fp32)
     :context-length 128 :max-images 1))
  (signals-contract-error
    (cl-vlm:make-model-capabilities
     :modalities '(:text :image :image) :operations '(:generate) :dtypes '(:fp32)
     :context-length 128 :max-images 1)))

(defun test-generation-batch-lifecycle ()
  (let* ((adapter (make-instance 'mock-adapter
                                 :manifest (make-mock-manifest :max-batch-size 3)))
         (requests
           (vector
            (list (cl-vlm:make-message :user (list (cl-vlm:make-text-part "a"))))
            (list (cl-vlm:make-message :user (list (cl-vlm:make-text-part "b"))))))
         (results (cl-vlm:generate-batch adapter requests :max-new-tokens #(3 5))))
    (check (= 2 (length results)))
    (check (equal "ok-3" (cl-vlm:generation-result-text (aref results 0))))
    (check (equalp #(5) (cl-vlm:generation-result-token-ids (aref results 1))))
    (check (= 2 (mock-released adapter))))
  (let* ((adapter (make-instance 'mock-adapter
                                 :manifest (make-mock-manifest :max-batch-size 2)
                                 :fail-p t))
         (requests (vector
                    (list (cl-vlm:make-message :user (list (cl-vlm:make-text-part "a"))))
                    (list (cl-vlm:make-message :user (list (cl-vlm:make-text-part "b")))))))
    (handler-case (cl-vlm:generate-batch adapter requests :max-new-tokens 4)
      (error () nil))
    (check (= 2 (mock-released adapter))))
  (let ((adapter (make-instance 'mock-adapter
                                :manifest (make-mock-manifest :max-batch-size 2))))
    (signals-contract-error
      (cl-vlm:generate-batch
       adapter
       (vector
        (list (cl-vlm:make-message :user (list (cl-vlm:make-text-part "a"))))
        (list (cl-vlm:make-message :user (list (cl-vlm:make-text-part "b"))))
        (list (cl-vlm:make-message :user (list (cl-vlm:make-text-part "c")))))
       :max-new-tokens 4))
    (check (zerop (mock-released adapter))))
  (let* ((adapter (make-instance 'mock-adapter
                                 :manifest (make-mock-manifest :max-batch-size 2)
                                 :generation-prepare-fail-at 2))
         (requests (vector
                    (list (cl-vlm:make-message :user (list (cl-vlm:make-text-part "a"))))
                    (list (cl-vlm:make-message :user (list (cl-vlm:make-text-part "b")))))))
    (handler-case (cl-vlm:generate-batch adapter requests :max-new-tokens 4)
      (error () nil))
    (check (= 1 (mock-released adapter)))))

(defun test-adapter-lifecycle-capabilities ()
  (let* ((methods (list :lora))
         (optimizers (list :sgd :adamw))
         (lifecycle
           (cl-vlm:make-adapter-lifecycle-capabilities
            :adapter-methods methods
            :optimizers optimizers
            :max-images-per-example 1
            :max-context-length 96))
         (manifest
           (make-mock-manifest
            :operations '(:generate :train-adapter :save-adapter
                          :resume-adapter :merge-adapter)
            :lifecycle lifecycle))
         (capabilities (cl-vlm:model-manifest-capabilities manifest)))
    (setf (car methods) :changed
          (car optimizers) :changed)
    (check (equal '(:lora)
                  (cl-vlm:adapter-lifecycle-capabilities-adapter-methods
                   lifecycle)))
    (check (equal '(:sgd :adamw)
                  (cl-vlm:adapter-lifecycle-capabilities-optimizers lifecycle)))
    (check (= 1 (cl-vlm:adapter-lifecycle-capabilities-max-images-per-example
                 lifecycle)))
    (check (= 96 (cl-vlm:adapter-lifecycle-capabilities-max-context-length
                  lifecycle)))
    (check (eq lifecycle
               (cl-vlm:model-capabilities-adapter-lifecycle capabilities)))
    (check (cl-vlm:supports-operation-p capabilities :train-adapter))
    (check (not (cl-vlm:supports-operation-p capabilities :quantize)))
    (let ((returned
            (cl-vlm:adapter-lifecycle-capabilities-optimizers lifecycle)))
      (setf (car returned) :changed)
      (check (equal '(:sgd :adamw)
                    (cl-vlm:adapter-lifecycle-capabilities-optimizers
                     lifecycle))))
    (check
     (cl-vlm-conformance:manifest-equal-p
      manifest
      (make-mock-manifest
       :operations '(:generate :train-adapter :save-adapter
                     :resume-adapter :merge-adapter)
       :lifecycle
       (cl-vlm:make-adapter-lifecycle-capabilities
        :adapter-methods '(:lora) :optimizers '(:sgd :adamw)
        :max-images-per-example 1 :max-context-length 96))))
    (check
     (not
      (cl-vlm-conformance:manifest-equal-p
       manifest
       (make-mock-manifest
        :operations '(:generate :train-adapter :save-adapter
                      :resume-adapter :merge-adapter)
        :lifecycle
        (cl-vlm:make-adapter-lifecycle-capabilities
         :adapter-methods '(:lora) :optimizers '(:sgd :adamw)
         :max-images-per-example 1 :max-context-length 95))))))
  (check (null (cl-vlm:model-capabilities-adapter-lifecycle
                (cl-vlm:model-manifest-capabilities (make-mock-manifest)))))
  (signals-contract-error
    (make-mock-manifest :operations '(:generate :beam-search)))
  (signals-contract-error
    (make-mock-manifest :operations '(:generate :train-adapter)))
  (signals-contract-error
    (make-mock-manifest
     :operations '(:generate)
     :lifecycle
     (cl-vlm:make-adapter-lifecycle-capabilities
      :adapter-methods '(:lora) :optimizers '(:sgd)
      :max-images-per-example 1 :max-context-length 96)))
  (signals-contract-error
    (make-mock-manifest
     :operations '(:generate :resume-adapter)
     :lifecycle
     (cl-vlm:make-adapter-lifecycle-capabilities
      :adapter-methods '(:lora) :optimizers '(:sgd)
      :max-images-per-example 1 :max-context-length 96)))
  (signals-contract-error
    (make-mock-manifest
     :operations '(:generate :train-adapter)
     :lifecycle
     (cl-vlm:make-adapter-lifecycle-capabilities
      :adapter-methods '(:lora) :optimizers '(:sgd)
      :max-images-per-example 2 :max-context-length 96)))
  (signals-contract-error
    (make-mock-manifest
     :operations '(:generate :train-adapter)
     :lifecycle
     (cl-vlm:make-adapter-lifecycle-capabilities
      :adapter-methods '(:lora) :optimizers '(:sgd)
      :max-images-per-example 1 :max-context-length 129))))

(defun make-mock-lifecycle-manifest ()
  (make-mock-manifest
   :operations '(:generate :train-adapter :save-adapter
                 :resume-adapter :merge-adapter)
   :lifecycle
   (cl-vlm:make-adapter-lifecycle-capabilities
    :adapter-methods '(:lora) :optimizers '(:sgd :adamw)
    :max-images-per-example 1 :max-context-length 96)))

(defun make-training-request (&key (images 1) (context 64) (destination "run-1"))
  (cl-vlm:make-adapter-operation-request
   :train-adapter destination
   :payload '(:owned-by-adapter)
   :adapter-method :lora
   :optimizer :sgd
   :steps 2
   :image-count images
   :context-length context))

(defun make-training-result (&key (kind :training-checkpoint))
  (cl-vlm:make-adapter-operation-result
   :train-adapter
   (list (cl-vlm:make-adapter-artifact
          kind "file:///tmp/run-1" :cl-vlm-native "sha256:abc"))
   :steps-completed 2))

(defun test-adapter-operation-lifecycle ()
  (let* ((destination (copy-seq "run-1"))
         (request (make-training-request :destination destination))
         (adapter (make-instance 'mock-adapter
                                 :manifest (make-mock-lifecycle-manifest)
                                 :operation-result (make-training-result)))
         (result (cl-vlm:perform-adapter-operation adapter request))
         (artifact (aref (cl-vlm:adapter-operation-result-artifacts result) 0)))
    (check (eq :train-adapter
               (cl-vlm:adapter-operation-request-operation request)))
    (check (equal "run-1"
                  (cl-vlm:adapter-operation-request-destination request)))
    (setf (char destination 0) #\X)
    (check (equal "run-1"
                  (cl-vlm:adapter-operation-request-destination request)))
    (check (eq :training-checkpoint (cl-vlm:adapter-artifact-kind artifact)))
    (check (equal "file:///tmp/run-1" (cl-vlm:adapter-artifact-location artifact)))
    (check (= 2 (cl-vlm:adapter-operation-result-steps-completed result)))
    (check (= 1 (mock-operation-prepare-count adapter)))
    (check (= 1 (mock-operation-execute-count adapter)))
    (check (= 1 (mock-operation-release-count adapter)))
    (let ((artifacts (cl-vlm:adapter-operation-result-artifacts result)))
      (setf (aref artifacts 0) nil)
      (check (typep (aref (cl-vlm:adapter-operation-result-artifacts result) 0)
                    'cl-vlm:adapter-artifact))))
  (let* ((checkpoint
           (cl-vlm:make-adapter-artifact
            :training-checkpoint "file:///tmp/run-1" :cl-vlm-native "sha256:one"))
         (resume
           (cl-vlm:make-adapter-operation-request
            :resume-adapter "run-2" :source-artifact checkpoint
            :payload '(:batch) :adapter-method :lora :optimizer :adamw
            :steps 3 :image-count 1 :context-length 80))
         (saved
           (cl-vlm:make-adapter-operation-request :save-adapter "adapter-1"))
         (adapter-artifact
           (cl-vlm:make-adapter-artifact
            :adapter "file:///tmp/adapter-1" :peft "sha256:two"))
         (merge
           (cl-vlm:make-adapter-operation-request
            :merge-adapter "merged-1" :source-artifact adapter-artifact)))
    (check (eq checkpoint
               (cl-vlm:adapter-operation-request-source-artifact resume)))
    (check (eq :save-adapter
               (cl-vlm:adapter-operation-request-operation saved)))
    (check (eq adapter-artifact
               (cl-vlm:adapter-operation-request-source-artifact merge)))
    (check (eq :adapter
               (cl-vlm:adapter-artifact-kind
                (aref
                 (cl-vlm:adapter-operation-result-artifacts
                  (cl-vlm:make-adapter-operation-result
                   :save-adapter
                   (list (cl-vlm:make-adapter-artifact
                          :adapter "file:///tmp/adapter-2" :peft "sha256:three"))))
                 0))))
    (check (eq :merged-model
               (cl-vlm:adapter-artifact-kind
                (aref
                 (cl-vlm:adapter-operation-result-artifacts
                  (cl-vlm:make-adapter-operation-result
                   :merge-adapter
                   (list (cl-vlm:make-adapter-artifact
                          :merged-model "hf://example/merged" :transformers
                          "commit:abc"))))
                 0)))))
  (let ((adapter (make-instance 'mock-adapter
                                :manifest (make-mock-manifest)
                                :operation-result (make-training-result))))
    (signals-contract-error
      (cl-vlm:perform-adapter-operation adapter (make-training-request)))
    (check (zerop (mock-operation-prepare-count adapter))))
  (dolist (request (list (make-training-request :images 2)
                         (make-training-request :context 97)))
    (let ((adapter (make-instance 'mock-adapter
                                  :manifest (make-mock-lifecycle-manifest)
                                  :operation-result (make-training-result))))
      (signals-contract-error
        (cl-vlm:perform-adapter-operation adapter request))
      (check (zerop (mock-operation-prepare-count adapter)))))
  (dolist (request
           (list
            (cl-vlm:make-adapter-operation-request
             :train-adapter "run-method" :payload '(:batch)
             :adapter-method :prefix :optimizer :sgd :steps 1
             :image-count 1 :context-length 64)
            (cl-vlm:make-adapter-operation-request
             :train-adapter "run-optimizer" :payload '(:batch)
             :adapter-method :lora :optimizer :lion :steps 1
             :image-count 1 :context-length 64)))
    (let ((adapter (make-instance 'mock-adapter
                                  :manifest (make-mock-lifecycle-manifest)
                                  :operation-result (make-training-result))))
      (signals-contract-error
        (cl-vlm:perform-adapter-operation adapter request))
      (check (zerop (mock-operation-prepare-count adapter)))))
  (let ((adapter (make-instance 'mock-adapter
                                :manifest (make-mock-lifecycle-manifest)
                                :operation-result
                                (make-instance
                                 'cl-vlm:adapter-operation-result
                                 :operation :train-adapter
                                 :artifacts
                                 (vector
                                  (cl-vlm:make-adapter-artifact
                                   :adapter "file:///tmp/run-1"
                                   :peft "sha256:wrong"))
                                 :steps-completed 2))))
    (signals-contract-error
      (cl-vlm:perform-adapter-operation adapter (make-training-request)))
    (check (= 1 (mock-operation-release-count adapter))))
  (let ((adapter (make-instance 'mock-adapter
                                :manifest (make-mock-lifecycle-manifest)
                                :operation-result (make-training-result)
                                :fail-p t)))
    (handler-case
        (cl-vlm:perform-adapter-operation adapter (make-training-request))
      (error () nil))
    (check (= 1 (mock-operation-release-count adapter))))
  (let ((adapter (make-instance 'mock-adapter
                                :manifest (make-mock-lifecycle-manifest)
                                :operation-result (make-training-result)
                                :prepare-fail-p t)))
    (handler-case
        (cl-vlm:perform-adapter-operation adapter (make-training-request))
      (error () nil))
    (check (= 1 (mock-operation-prepare-count adapter)))
    (check (zerop (mock-operation-release-count adapter))))
  (signals-contract-error
    (cl-vlm:make-adapter-operation-request
     :resume-adapter "run-2"
     :payload '(:batch) :adapter-method :lora :optimizer :sgd
     :steps 1 :image-count 1 :context-length 64))
  (signals-contract-error
    (cl-vlm:make-adapter-operation-request
     :save-adapter "run-2" :steps 1)))

(defun test-generation-lifecycle ()
  (let* ((adapter (make-instance 'mock-adapter :manifest (make-mock-manifest)))
         (messages (list (cl-vlm:make-message
                          :user (list (cl-vlm:make-image-part #P"page.png")
                                      (cl-vlm:make-text-part "read")))))
         (result (cl-vlm:generate adapter messages :max-new-tokens 7)))
    (check (equal "ok" (cl-vlm:generation-result-text result)))
    (check (equalp #(10 11) (cl-vlm:generation-result-token-ids result)))
    (check (eq :eos (cl-vlm:generation-result-stop-reason result)))
    (check (= 1 (mock-released adapter))))
  (let* ((adapter (make-instance 'mock-adapter :manifest (make-mock-manifest)
                                 :fail-p t))
         (messages (list (cl-vlm:make-message :user
                                              (list (cl-vlm:make-text-part "fail"))))))
    (handler-case (cl-vlm:generate adapter messages :max-new-tokens 7)
      (error () nil))
    (check (= 1 (mock-released adapter))))
  (let ((adapter (make-instance 'mock-adapter
                                :manifest (make-mock-manifest :modalities '(:text)))))
    (signals-contract-error
      (cl-vlm:generate
       adapter
       (list (cl-vlm:make-message :user
                                  (list (cl-vlm:make-image-part #P"page.png"))))
       :max-new-tokens 7))
    (check (zerop (mock-released adapter))))
  (let ((adapter (make-instance 'mock-adapter
                                :manifest (make-mock-manifest :max-images 1))))
    (signals-contract-error
      (cl-vlm:generate
       adapter
       (list (cl-vlm:make-message
              :user (list (cl-vlm:make-image-part #P"one.png")
                          (cl-vlm:make-image-part #P"two.png"))))
       :max-new-tokens 7))))

(defun test-generation-conformance ()
  (let* ((manifest (make-mock-manifest))
         (adapter (make-instance 'mock-adapter :manifest manifest))
         (messages
           (list (cl-vlm:make-message
                  :user
                  (list (cl-vlm:make-image-part #P"page.png")
                        (cl-vlm:make-text-part "read")))))
         (expected (cl-vlm:make-generation-result "ok" #(10 11) :eos)))
    (let ((result
            (cl-vlm-conformance:check-generation-adapter
             adapter messages manifest expected
             :max-new-tokens 7
             :prepared-released-p
             (lambda (prepared)
               (declare (ignore prepared))
               (plusp (mock-released adapter))))))
      (check (equal "ok" (cl-vlm:generation-result-text result)))
      (check (equalp #(10 11) (cl-vlm:generation-result-token-ids result))))
    (check (= 2 (mock-released adapter)))
    (check (cl-vlm-conformance:manifest-equal-p
            manifest (make-mock-manifest)))
    (check (not (cl-vlm-conformance:manifest-equal-p
                 manifest (make-mock-manifest :max-images 2))))
    (check
     (handler-case
         (progn
           (cl-vlm-conformance:check-generation-adapter
            (make-instance 'mock-adapter :manifest manifest)
            messages manifest
            (cl-vlm:make-generation-result "wrong" #(10 11) :eos)
            :max-new-tokens 7)
           nil)
       (cl-vlm-conformance:conformance-error () t)))))

(defun test-adapter-operation-conformance ()
  (let* ((manifest (make-mock-lifecycle-manifest))
         (request (make-training-request))
         (expected (make-training-result))
         (adapter (make-instance 'mock-adapter
                                 :manifest manifest
                                 :operation-result expected))
         (result
           (cl-vlm-conformance:check-adapter-operation
            adapter request manifest expected
            :prepared-released-p
            (lambda (prepared)
              (declare (ignore prepared))
              (plusp (mock-operation-release-count adapter))))))
    (check (cl-vlm-conformance:operation-result-equal-p result expected))
    (check (= 2 (mock-operation-release-count adapter)))
    (check
     (handler-case
         (progn
           (cl-vlm-conformance:check-adapter-operation
            (make-instance 'mock-adapter
                           :manifest manifest
                           :operation-result expected)
            request manifest
            (cl-vlm:make-adapter-operation-result
             :train-adapter
             (list (cl-vlm:make-adapter-artifact
                    :training-checkpoint "file:///tmp/other"
                    :cl-vlm-native "sha256:different"))
             :steps-completed 2))
           nil)
       (cl-vlm-conformance:conformance-error () t)))))

(defun run-tests ()
  (setf *checks* 0)
  (test-content)
  (test-manifest)
  (test-adapter-lifecycle-capabilities)
  (test-adapter-operation-lifecycle)
  (test-generation-lifecycle)
  (test-generation-batch-lifecycle)
  (test-generation-conformance)
  (test-adapter-operation-conformance)
  (format t "~&cl-vlm: ~D checks passed.~%" *checks*)
  t)
