# Image OCR Safety (burned-in text screening)

`safety/visual_service.py::check_image` can screen burned-in text (phone
numbers, social handles, URLs, grooming language rendered into an image)
through optical character recognition, then route the extracted text through
the **same** `check_text` + PII policy used for user-typed text. No policy
logic is duplicated in the OCR stage.

## Enabling OCR (requires installing a backend)

**No OCR dependency ships in `requirements-*.txt`.** OCR is OFF by default
(`LITTLENET_ENABLE_OCR` unset). To enable it:

1. Install **one** backend package in the image-moderation environment:
   - `rapidocr-onnxruntime` (preferred: no system binary needed), or
   - `easyocr`, or
   - `pytesseract` **plus** the `tesseract` system binary.
2. Set `LITTLENET_ENABLE_OCR=1`.
3. Restart the worker so the guarded import is re-attempted.

The stage tries backends in the order rapidocr → easyocr → pytesseract and
uses the first that imports and initializes.

## Failure posture (fail closed)

- **Flag on, no backend installed:** the stage degrades gracefully — it logs
  once, records `ocr_unavailable` in signal errors, and marks the image as a
  partial safety failure (→ REVIEW). It never silently pretends OCR ran.
- **OCR errors / timeouts:** recorded as `ocr_failed` / `ocr_timeout`,
  partial safety evidence only. An OCR failure can push an image to REVIEW at
  most; it never weakens or bypasses the visual decision, and it never
  escalates the image to a total safety failure on its own.
- **Bounded processing:** the image is downscaled (max 1024px) before OCR and
  the OCR call is capped by `LITTLENET_OCR_TIMEOUT_SECONDS` (default 30s).
- **Video frames:** per-frame OCR is off unless `LITTLENET_ENABLE_OCR_VIDEO_FRAMES=1`
  is also set, so frame sampling (up to 60 frames) stays within its time budget.

## How detections are honored

- OCR text → `text_service.check_text`: scores merge by **max** (visual
  evidence never lowered); deterministic hard-block flags (grooming,
  self-harm, severe abuse, dangerous challenge, sexual) propagate, so
  `policy.decide` hard-blocks burned-in predatory text.
- OCR text → `pii_service.scan_pii`: when PII is detected with
  `policy_action == BLOCK` (e.g. a burned-in phone number), the image signals
  get `deterministic_ocr_pii=True` and `policy.decide` returns
  `BLOCK / "burned-in contact/PII text detected in image (OCR)"`.
- Only the **redacted** OCR text (`ocr_redacted_text`, ≤500 chars) is kept in
  moderation evidence; raw PII is not persisted.

## Tier limitation

OCR runs in the **local** `check_image` path. When the Modal CPU tier or the
remote AI server handles an image, OCR is that tier's responsibility and is
not run locally. Extending OCR to the Modal worker image is future work and
must follow the same fail-closed contract above.

## Tests

`tests/test_image_ocr_safety.py` covers: PII text merged from OCR routes to a
hard BLOCK via `policy.decide`; deterministic text flags propagate; visual
scores are never weakened; OCR errors degrade to partial evidence; the stage
is a no-op when the flag is off; and graceful degradation when no backend is
installed (synthetic PIL fixtures stand in for a real OCR engine).
