(defpackage #:cl-vlm
  (:use #:cl)
  (:nicknames #:vlm)
  (:export
   #:vlm-error #:vlm-error-message #:contract-error
   #:content-part #:text-part #:image-part
   #:make-text-part #:text-part-text
   #:make-image-part #:image-part-source #:image-part-media-type
   #:message #:make-message #:message-role #:message-parts
   #:model-capabilities #:make-model-capabilities
   #:model-capabilities-modalities #:model-capabilities-operations
   #:model-capabilities-dtypes #:model-capabilities-context-length
   #:model-capabilities-max-images #:model-capabilities-max-batch-size
   #:model-capabilities-adapter-lifecycle
   #:supports-modality-p #:supports-operation-p
   #:adapter-lifecycle-capabilities #:make-adapter-lifecycle-capabilities
   #:adapter-lifecycle-capabilities-adapter-methods
   #:adapter-lifecycle-capabilities-optimizers
   #:adapter-lifecycle-capabilities-max-images-per-example
   #:adapter-lifecycle-capabilities-max-context-length
   #:model-manifest #:make-model-manifest
   #:model-manifest-family #:model-manifest-architecture
   #:model-manifest-checkpoint #:model-manifest-revision
   #:model-manifest-capabilities
   #:adapter-artifact #:make-adapter-artifact
   #:adapter-artifact-kind #:adapter-artifact-location
   #:adapter-artifact-format #:adapter-artifact-revision
   #:adapter-operation-request #:make-adapter-operation-request
   #:adapter-operation-request-operation
   #:adapter-operation-request-destination
   #:adapter-operation-request-payload
   #:adapter-operation-request-adapter-method
   #:adapter-operation-request-optimizer
   #:adapter-operation-request-steps
   #:adapter-operation-request-image-count
   #:adapter-operation-request-context-length
   #:adapter-operation-request-source-artifact
   #:adapter-operation-result #:make-adapter-operation-result
   #:adapter-operation-result-operation
   #:adapter-operation-result-artifacts
   #:adapter-operation-result-steps-completed
   #:prepare-adapter-operation #:execute-adapter-operation
   #:release-prepared-operation #:perform-adapter-operation
   #:adapter #:adapter-manifest #:prepare-generation
   #:generate-prepared #:generate-prepared-batch #:release-prepared
   #:generate #:generate-batch
   #:generation-result #:make-generation-result
   #:generation-result-text #:generation-result-token-ids
   #:generation-result-stop-reason))
