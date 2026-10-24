(in-package #:cl-vlm)

(defparameter +model-operations+
  '(:generate :train-adapter :save-adapter :resume-adapter :merge-adapter))

(defparameter +adapter-lifecycle-operations+
  '(:train-adapter :save-adapter :resume-adapter :merge-adapter))

(defclass adapter-lifecycle-capabilities ()
  ((adapter-methods
    :initarg :adapter-methods
    :reader %adapter-lifecycle-capabilities-adapter-methods)
   (optimizers
    :initarg :optimizers
    :reader %adapter-lifecycle-capabilities-optimizers)
   (max-images-per-example
    :initarg :max-images-per-example
    :reader adapter-lifecycle-capabilities-max-images-per-example)
   (max-context-length
    :initarg :max-context-length
    :reader adapter-lifecycle-capabilities-max-context-length)))

(defclass model-capabilities ()
  ((modalities :initarg :modalities :reader %model-capabilities-modalities)
   (operations :initarg :operations :reader %model-capabilities-operations)
   (dtypes :initarg :dtypes :reader %model-capabilities-dtypes)
   (context-length :initarg :context-length :reader model-capabilities-context-length)
   (max-images :initarg :max-images :reader model-capabilities-max-images)
   (max-batch-size :initarg :max-batch-size :reader model-capabilities-max-batch-size)
   (adapter-lifecycle
    :initarg :adapter-lifecycle
    :initform nil
    :reader model-capabilities-adapter-lifecycle)))

(defclass model-manifest ()
  ((family :initarg :family :reader model-manifest-family)
   (architecture :initarg :architecture :reader %model-manifest-architecture)
   (checkpoint :initarg :checkpoint :reader %model-manifest-checkpoint)
   (revision :initarg :revision :reader %model-manifest-revision)
   (capabilities :initarg :capabilities :reader model-manifest-capabilities)))

(defun checked-keywords (values label)
  (let ((items (coerce values 'list)))
    (unless (and items (every #'keywordp items))
      (contract-errorf "~A must be a nonempty sequence of keywords" label))
    (unless (= (length items) (length (remove-duplicates items)))
      (contract-errorf "~A must not contain duplicates" label))
    (copy-list items)))

(defun make-adapter-lifecycle-capabilities
    (&key adapter-methods optimizers max-images-per-example max-context-length)
  (let ((adapter-methods (checked-keywords adapter-methods "Adapter methods"))
        (optimizers (checked-keywords optimizers "Optimizers")))
    (unless (typep max-images-per-example '(integer 0))
      (contract-errorf "Maximum training image count must be a nonnegative integer"))
    (unless (typep max-context-length '(integer 1))
      (contract-errorf "Maximum training context length must be a positive integer"))
    (make-instance 'adapter-lifecycle-capabilities
                   :adapter-methods adapter-methods
                   :optimizers optimizers
                   :max-images-per-example max-images-per-example
                   :max-context-length max-context-length)))

(defun adapter-lifecycle-capabilities-adapter-methods (capabilities)
  (copy-list (%adapter-lifecycle-capabilities-adapter-methods capabilities)))

(defun adapter-lifecycle-capabilities-optimizers (capabilities)
  (copy-list (%adapter-lifecycle-capabilities-optimizers capabilities)))

(defun make-model-capabilities
    (&key modalities operations dtypes context-length max-images (max-batch-size 1)
          adapter-lifecycle)
  (let ((modalities (checked-keywords modalities "Modalities"))
        (operations (checked-keywords operations "Operations"))
        (dtypes (checked-keywords dtypes "Dtypes")))
    (unless (member :text modalities)
      (contract-errorf "Vision-language capabilities must include :TEXT"))
    (unless (typep context-length '(integer 1))
      (contract-errorf "Context length must be a positive integer"))
    (unless (typep max-images '(integer 0))
      (contract-errorf "Maximum image count must be a nonnegative integer"))
    (unless (typep max-batch-size '(integer 1))
      (contract-errorf "Maximum generation batch size must be a positive integer"))
    (unless (eq (plusp max-images) (not (null (member :image modalities))))
      (contract-errorf "Image modality and maximum image count disagree"))
    (unless (every (lambda (operation) (member operation +model-operations+)) operations)
      (contract-errorf "Operations contain an unknown model operation"))
    (let ((lifecycle-operation-p
            (some (lambda (operation)
                    (member operation +adapter-lifecycle-operations+))
                  operations)))
      (unless (eq (not (null lifecycle-operation-p))
                  (not (null
                        (typep adapter-lifecycle
                               'adapter-lifecycle-capabilities))))
        (contract-errorf
         "Adapter lifecycle operations and lifecycle capabilities disagree")))
    (when (and (member :resume-adapter operations)
               (not (member :train-adapter operations)))
      (contract-errorf ":RESUME-ADAPTER requires :TRAIN-ADAPTER"))
    (when adapter-lifecycle
      (when (> (adapter-lifecycle-capabilities-max-images-per-example
                adapter-lifecycle)
               max-images)
        (contract-errorf "Training image limit exceeds the model image limit"))
      (when (> (adapter-lifecycle-capabilities-max-context-length
                adapter-lifecycle)
               context-length)
        (contract-errorf "Training context limit exceeds the model context limit")))
    (make-instance 'model-capabilities
                   :modalities modalities :operations operations :dtypes dtypes
                   :context-length context-length :max-images max-images
                   :max-batch-size max-batch-size
                   :adapter-lifecycle adapter-lifecycle)))

(defun model-capabilities-modalities (capabilities)
  (copy-list (%model-capabilities-modalities capabilities)))

(defun model-capabilities-operations (capabilities)
  (copy-list (%model-capabilities-operations capabilities)))

(defun model-capabilities-dtypes (capabilities)
  (copy-list (%model-capabilities-dtypes capabilities)))

(defun supports-modality-p (capabilities modality)
  (and (typep capabilities 'model-capabilities)
       (keywordp modality)
       (not (null (member modality (%model-capabilities-modalities capabilities))))))

(defun supports-operation-p (capabilities operation)
  (and (typep capabilities 'model-capabilities)
       (keywordp operation)
       (not (null (member operation (%model-capabilities-operations capabilities))))))

(defun checked-string (value label)
  (unless (and (stringp value) (plusp (length value)) (not (find #\Null value)))
    (contract-errorf "~A must be a nonempty string without NUL" label))
  (copy-seq value))

(defun make-model-manifest (&key family architecture checkpoint revision capabilities)
  (unless (keywordp family)
    (contract-errorf "Model family must be a keyword"))
  (unless (typep capabilities 'model-capabilities)
    (contract-errorf "Model manifest requires model capabilities"))
  (make-instance 'model-manifest
                 :family family
                 :architecture (checked-string architecture "Architecture")
                 :checkpoint (checked-string checkpoint "Checkpoint")
                 :revision (checked-string revision "Revision")
                 :capabilities capabilities))

(defun model-manifest-architecture (manifest)
  (copy-seq (%model-manifest-architecture manifest)))

(defun model-manifest-checkpoint (manifest)
  (copy-seq (%model-manifest-checkpoint manifest)))

(defun model-manifest-revision (manifest)
  (copy-seq (%model-manifest-revision manifest)))
