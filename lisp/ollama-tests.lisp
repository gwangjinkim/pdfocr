(in-package #:cl-pdfocr-tests)
(export 'run-ollama-tests)

(defun parse-http-fixture (path text)
  (with-open-file (stream path :direction :output :if-exists :supersede
                               :element-type '(unsigned-byte 8))
    (write-sequence (babel:string-to-octets text :encoding :utf-8) stream))
  (with-open-file (stream path :element-type '(unsigned-byte 8))
    (cl-pdfocr::http-body stream)))

(defun run-ollama-tests ()
  #+sbcl
  (must-error (lambda () (cl-pdfocr::call-with-ollama-deadline
                          1 (lambda () (signal 'sb-ext:timeout)))))
  (let* ((root (merge-pathnames (format nil "pdfocr-ollama-tests-~D-~D/" (get-universal-time)
                                       (random 1000000)) (uiop:temporary-directory)))
         (wire (merge-pathnames "wire.http" root))
         (prepared (merge-pathnames "prepared/" root))
         (image (merge-pathnames "page.png" prepared))
         (out (merge-pathnames "ocr/" root))
         (digest "fixture-digest") (version "fixture-version")
         (reason "stop") (count 2) (done yason:true) (calls 0) (response-model "fixture:vision")
         (vision t) (remote nil) (payloads nil))
    (unwind-protect
         (progn
           (ensure-directories-exist wire)
           (assert (equal "ſ" (parse-http-fixture wire
                              (format nil "HTTP/1.1 200 OK~C~CContent-Length: 2~C~C~C~Cſ"
                                      #\Return #\Newline #\Return #\Newline #\Return #\Newline))))
           (assert (equal "ſ" (parse-http-fixture wire
                              (format nil "HTTP/1.1 200 OK~C~CTransfer-Encoding: chunked~C~C~C~C2~C~Cſ~C~C0~C~C~C~C"
                                      #\Return #\Newline #\Return #\Newline #\Return #\Newline
                                      #\Return #\Newline #\Return #\Newline #\Return #\Newline
                                      #\Return #\Newline))))
           (dolist (text (list (format nil "HTTP/1.1 500 Fail~C~C~C~C" #\Return #\Newline #\Return #\Newline)
                              (format nil "HTTP/1.1 200 OK~C~CContent-Length: 8~C~C~C~Cx"
                                      #\Return #\Newline #\Return #\Newline #\Return #\Newline)
                              (format nil "HTTP/1.1 200 OK~C~CTransfer-Encoding: chunked~C~CContent-Length: 2~C~C~C~C"
                                      #\Return #\Newline #\Return #\Newline #\Return #\Newline #\Return #\Newline)))
             (must-error (lambda () (parse-http-fixture wire text))))
           (let ((cl-pdfocr::*ollama-response-limit* 1))
             (must-error (lambda () (parse-http-fixture wire
                                      (format nil "HTTP/1.1 200 OK~C~CContent-Length: 2~C~C~C~Cxx"
                                              #\Return #\Newline #\Return #\Newline #\Return #\Newline)))))
           (cl-pdfocr::write-text image "fixture-image")
           (cl-pdfocr::write-json (merge-pathnames "document.json" prepared)
             (cl-pdfocr::object "pages" (vector (cl-pdfocr::object "page" 34 "image" "page.png"
                                                 "image_sha256" (cl-pdfocr::sha256 image)))))
           (flet ((transport (method path payload)
                    (cond
                      ((equal path "/api/version") (cl-pdfocr::object "version" version))
                      ((equal path "/api/tags")
                       (cl-pdfocr::object "models" (vector (cl-pdfocr::object
                                                            "name" "fixture:vision" "digest" digest))))
                      ((equal path "/api/show")
                       (cl-pdfocr::object "capabilities" (if vision #("vision" "completion") #("completion"))
                                         "details" (cl-pdfocr::object "family" "fixture" "quantization_level" "test")
                                         "remote_host" remote))
                      ((equal path "/api/chat")
                       (assert (equal method "POST")) (incf calls)
                       (push (cl-pdfocr::parse-json-text
                               (with-output-to-string (s) (yason:encode payload s))) payloads)
                       (cl-pdfocr::object "model" response-model "done" done "done_reason" reason
                                         "eval_count" count "message" (cl-pdfocr::object "content" "Per-")))
                      (t (error "Unexpected fixture endpoint.")))))
             (let ((adapter (cl-pdfocr::initialize-ollama-adapter
                              "fixture:vision" #'transport 11434 180 8192 "fixture-digest")))
               (cl-pdfocr:recognize-prepared prepared out adapter :max-new-tokens 2)
               (assert (= 1 calls))
               (let* ((record (cl-pdfocr::read-json (merge-pathnames "page-0034.json" out)))
                      (metadata (gethash "backend_response" record)))
                 (assert (equal "partial" (gethash "status" record)))
                 (assert (zerop (length (gethash "token_ids" record))))
                 (assert (eq yason:false (gethash "token_ids_available" metadata)))
                 (assert (= 2 (gethash "reported_generated_tokens" metadata))))
               (let* ((payload (first payloads))
                      (message (aref (gethash "messages" payload) 0)))
                 (assert (eq yason:false (gethash "stream" payload)))
                 (assert (eq yason:false (gethash "think" payload)))
                 (assert (zerop (gethash "keep_alive" payload)))
                 (assert (equal "fixture-image" (base64:base64-string-to-string
                                                  (aref (gethash "images" message) 0)))))
               (cl-pdfocr:recognize-prepared prepared out adapter :max-new-tokens 2 :resume t)
               (assert (= 1 calls))
               (let ((messages (list (vlm:make-message :user (list (vlm:make-text-part "test"))))))
                 (setf count 1)
                 (assert (eq :stop (vlm:generation-result-stop-reason
                                    (vlm:generate adapter messages :max-new-tokens 2))))
                 (setf reason "length")
                 (assert (eq :length (vlm:generation-result-stop-reason
                                      (vlm:generate adapter messages :max-new-tokens 2))))
                 (setf reason "unknown")
                 (must-error (lambda () (vlm:generate adapter messages)))
                 (setf reason "stop" done yason:false)
                 (must-error (lambda () (vlm:generate adapter messages)))
                 (setf done yason:true response-model "different")
                 (must-error (lambda () (vlm:generate adapter messages)))
                 (setf response-model "fixture:vision" digest "retagged")
                 (must-error (lambda () (vlm:generate adapter messages)))
                 (setf digest "fixture-digest" version "changed")
                 (must-error (lambda () (vlm:generate adapter messages)))))
             (setf version "fixture-version" vision nil)
             (must-error (lambda () (cl-pdfocr::initialize-ollama-adapter
                                      "fixture:vision" #'transport 11434 180 8192 nil)))
             (setf vision t remote "remote.example")
             (must-error (lambda () (cl-pdfocr::initialize-ollama-adapter
                                      "fixture:vision" #'transport 11434 180 8192 nil)))))
      (uiop:delete-directory-tree root :validate t :if-does-not-exist :ignore)))
  (format t "~&PASS: Ollama UTF-8/length/chunk HTTP framing, response bounds, vision/local pins, payloads, raw evidence, absent IDs, partial/stop handling and cache resume.~%")
  t)
