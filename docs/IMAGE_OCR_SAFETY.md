# Image OCR Safety — current LittleMuse contract (8 October 2026)

This document describes the **current source**, not the retired 2026-09-22 optional-only OCR design.

## Default and deployment dependencies
- OCR for ordinary uploaded **images is enabled by default** in `safety/visual_service.py::check_image`. Set `LITTLENET_ENABLE_OCR=0` only for an explicitly documented opt-out.
- `rapidocr-onnxruntime==1.4.4` is pinned in `requirements-core.txt` and the Modal AI CPU image in `modal_ai.py`. The preferred backend is RapidOCR; the code supports EasyOCR and pytesseract as fallbacks if provisioned.
- The direct-to-R2 v2 pipeline runs inside the Modal web worker; ordinary image inference can call `modal_ai.py::moderate_image_upload_cpu`, which invokes `check_image` and OCR without requiring a T4 GPU.
- Alternative runtimes (such as the optional Docker AI image) inherit the core OCR dependency through `requirements-text.txt`. Each deployment must independently verify package availability; source wiring alone is not proof of OCR accuracy.

## Bounded, fail-closed processing
1. The image is downscaled to at most 1024 pixels for OCR. OCR extraction has a 30-second default timeout (`LITTLENET_OCR_TIMEOUT_SECONDS`).
2. The extracted text is examined using the same text and contact/PII policy as typed text. Deterministic contact-sharing flags, dangerous language and relevant adult-text categories must survive text+image evidence merging.
3. Missing OCR backend, an OCR exception, or timeout adds explicit failure evidence and can prevent an automatic ALLOW by requiring REVIEW. It must never silently be interpreted as a safe, empty OCR result.
4. Only redacted OCR text is retained in moderation evidence; never store raw extracted phone numbers or other PII.

## Video coverage
- Video sampling is bounded: the default maximum is eight sampled frames with an adaptive fast pass and coverage checks.
- Per-frame OCR is **not enabled by default**. It runs when `LITTLENET_ENABLE_OCR_VIDEO_FRAMES=1`, to avoid multiplying image OCR cost across frames.
- A video's first-frame/fast-pass safety check is not a claim that every frame is inspected. Insufficient temporal coverage remains private for REVIEW.

## Historical defect closure
The legacy browser post uploader previously combined only numeric risk fields and dropped OCR PII/deterministic text flags. The October 8 historical audit replaces that duplicate merge with the canonical `services.media_processor._merge_signals`, so both mobile and browser policy paths honor OCR hard-block evidence.

## Evidence limits
`tests/test_image_ocr_safety.py` and `tests/test_legacy_upload_policy_parity.py` cover policy wiring using controlled/mock OCR evidence. They do **not** establish real-world OCR recall, speed, or full real-image deployment behavior. A real OCR sample and live BLOCK/REVIEW test are still required before making those claims.
