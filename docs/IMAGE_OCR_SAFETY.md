# Image OCR Safety (burned-in text screening)

`safety/visual_service.py::check_image` screens burned-in text such as phone
numbers, social handles, URLs, and unsafe language through OCR, then routes the
extracted text through the same text-moderation and PII policy used for typed
content. OCR never replaces the trained image/YOLO evidence; it can only add
safety evidence.

## Production configuration

Production image moderation ships `rapidocr-onnxruntime` in the LittleNet AI
image and enables `LITTLENET_ENABLE_OCR=1`. Ordinary image uploads are
moderated by the scale-to-zero Modal CPU function
`littlenet-ai.moderate_image_upload_cpu`, which calls the shared
`check_image()` implementation.

The trained-image deployment preflight imports and initializes RapidOCR.
Deployment is blocked if that backend cannot load.

Alternative local development backends remain supported in this order:
`rapidocr-onnxruntime`, `easyocr`, then `pytesseract` plus the Tesseract
system binary.

## Bounded processing

- Images are downscaled to at most 1024 px before OCR.
- OCR is bounded by `LITTLENET_OCR_TIMEOUT_SECONDS` (30 seconds by default).
- `LITTLENET_ENABLE_OCR_VIDEO_FRAMES=0` remains the production default so
  sampled video frames do not multiply OCR cost.
- OCR output is capped and only redacted text is retained in moderation
  evidence.

## Failure posture

- Missing/unavailable OCR while the stage is enabled records
  `ocr_unavailable` and marks partial safety failure.
- OCR errors/timeouts record `ocr_failed` / `ocr_timeout`.
- OCR failure never weakens another detector's decision and never creates an
  unsafe ALLOW.
- Extracted contact/PII that maps to BLOCK sets
  `deterministic_ocr_pii=True`, so the shared policy blocks the image.
- Deterministic grooming, self-harm, severe-abuse, dangerous-challenge and
  sexual text flags are propagated into the image safety decision.

## Privacy

Only the redacted OCR representation (`ocr_redacted_text`, maximum 500
characters) is stored with moderation evidence. Raw extracted PII is not
persisted.

## Tests

`tests/test_image_ocr_safety.py` covers PII hard-blocking, deterministic text
flags, max-score merging, fail-closed OCR errors, the disabled-stage behavior,
and graceful backend failure. `tests/test_react_native_contract.py` also
locks the production Modal dependency/feature-flag/preflight contract.
