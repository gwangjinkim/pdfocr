(in-package #:cl-vlm)

(defclass content-part () ())

(defclass text-part (content-part)
  ((text :initarg :text :reader %text-part-text)))

(defclass image-part (content-part)
  ((source :initarg :source :reader %image-part-source)
   (media-type :initarg :media-type :reader %image-part-media-type)))

(defclass message ()
  ((role :initarg :role :reader %message-role)
   (parts :initarg :parts :reader %message-parts)))

(defun make-text-part (text)
  (unless (and (stringp text) (plusp (length text)) (not (find #\Null text)))
    (contract-errorf "Text content must be a nonempty string without NUL"))
  (make-instance 'text-part :text (copy-seq text)))

(defun text-part-text (part)
  (unless (typep part 'text-part)
    (contract-errorf "Expected a text part"))
  (copy-seq (%text-part-text part)))

(defun make-image-part (source &key media-type)
  (when (null source)
    (contract-errorf "Image content requires a source"))
  (unless (or (null media-type)
              (and (stringp media-type) (plusp (length media-type))
                   (not (find #\Null media-type))))
    (contract-errorf "Image media type must be NIL or a nonempty string without NUL"))
  (make-instance 'image-part :source source
                             :media-type (and media-type (copy-seq media-type))))

(defun image-part-source (part)
  (unless (typep part 'image-part)
    (contract-errorf "Expected an image part"))
  (%image-part-source part))

(defun image-part-media-type (part)
  (unless (typep part 'image-part)
    (contract-errorf "Expected an image part"))
  (let ((value (%image-part-media-type part)))
    (and value (copy-seq value))))

(defun make-message (role parts)
  (unless (member role '(:system :user :assistant))
    (contract-errorf "Message role must be :SYSTEM, :USER or :ASSISTANT"))
  (let ((vector (coerce parts 'vector)))
    (unless (plusp (length vector))
      (contract-errorf "A message requires at least one content part"))
    (unless (every (lambda (part) (typep part 'content-part)) vector)
      (contract-errorf "Every message item must be a content part"))
    (make-instance 'message :role role :parts (copy-seq vector))))

(defun message-role (message)
  (unless (typep message 'message)
    (contract-errorf "Expected a message"))
  (%message-role message))

(defun message-parts (message)
  (unless (typep message 'message)
    (contract-errorf "Expected a message"))
  (copy-seq (%message-parts message)))

(defun normalize-messages (messages)
  (let ((vector (coerce messages 'vector)))
    (unless (plusp (length vector))
      (contract-errorf "Generation requires at least one message"))
    (unless (every (lambda (message) (typep message 'message)) vector)
      (contract-errorf "Every request item must be a message"))
    (copy-seq vector)))
