# LittleNet Moderation Research and Hardening Report

Date: 2026-09-20

## Executive conclusion

The supplied report describes the broad architecture correctly, but its grades
and implied production confidence are not supported by measured evidence. The
repository has a strong quarantine-first publication design and useful model
diversity. It does **not** yet have a representative, independently labelled
production benchmark that justifies an accuracy or "A+" claim.

The highest-impact confirmed gaps were temporal coverage of long videos,
overconfidence at the guardian age boundary, and easily canonicalized text
evasion. Those contracts have now been hardened. Remaining model-quality claims
must be resolved with a lawful, representative benchmark—not by changing a
threshold until a small synthetic test passes.

## Findings validated against source

1. Uploaded media is held in quarantine and only the ALLOW path sanitizes and
   promotes it to a published namespace. REVIEW remains private and BLOCK is not
   published.
2. Total moderation failure is BLOCK. Partial evidence failure is REVIEW. Thus
   "fail closed" is substantially true for publication, but it is inaccurate to
   describe every model error as BLOCK.
3. Image moderation combines NudeNet, FalconsAI, CLIP, and YOLO evidence with
   per-model review/block thresholds. This is an ensemble of signals, not proof
   of accuracy.
4. Video moderation uses scene-boundary plus uniform samples and stops early on
   BLOCK. Before this change, the Modal deployment used a 24-frame ceiling and a
   four-second desired interval; sufficiently long videos could exhaust the cap
   yet still be automatically allowed.
5. Video audio is intentionally stripped during sanitization. This prevents the
   original audio from reaching children, but means the product does not support
   user-audio moderation or preservation.
6. Detoxify multilingual is limited to the languages documented by that model.
   Deterministic grooming, sexual-solicitation, abuse and PII rules add useful
   fail-safe coverage, but no ruleset is immune to adversarial language.
7. (2026-09-22 note: the DeepFace/face-age path was removed entirely by product
   decision; it is no longer part of the moderation or verification stack. The
   former exact `>=18` gate was unsafe at the decision boundary.)
8. Modal is configured to scale to zero. The report's exact 25–40 second claim
   is not demonstrated by repository telemetry. Cold-start risk is real, but it
   must be measured rather than asserted.

## Implemented controls

### Temporal video coverage

- The Modal full-model budget is raised from 24 to 60 frames and the desired
  interval from four to three seconds.
- Every video now records duration, required samples, maximum accepted gap and
  whether temporal coverage was complete.
- If the frame budget cannot satisfy the four-second auto-allow coverage
  contract, the result is marked partial and policy routes it to REVIEW. A long
  under-sampled video can no longer silently reach ALLOW.
- Scene detection remains additive. It cannot substitute for the temporal
  coverage declaration because a brief insert is not guaranteed to form a
  detected scene.

### Guardian age uncertainty

- (2026-09-22 note: guardian face liveness and face-age approval were removed
  entirely by product decision. The remaining guardian assurance is email-OTP
  ownership plus an 18+ date-of-birth declaration and explicit consent.)
- Generative vision age fallback is disabled by default and requires the explicit
  `LITTLENET_ENABLE_GENERATIVE_AGE_FALLBACK=1` opt-in.
- This is still not identity or legal-age proof. Production onboarding should add
  a privacy-reviewed guardian verification provider or documented manual process.

### Text evasion resistance

- Deterministic matching now applies Unicode NFKC normalization, removes
  zero-width/combining format characters, maps common leetspeak, joins punctuation
  inserted inside words, and limits repeated-character evasion.
- Original text is still sent to the ML model; canonicalization only strengthens
  the deterministic layer.

## Test evidence

The focused moderation suite covers model thresholds, fail-closed behavior,
scene/uniform budget behavior, the opt-in
fallback, temporal coverage, and text-evasion examples. Current focused result:
38 passed.

This result proves the code contracts tested. It does not establish recall,
precision, fairness, or production accuracy of the underlying models.

## Required production validation

1. Build a versioned, consented and legally reviewed evaluation set split by
   policy class, age band, skin tone, language, device quality, compression,
   lighting and adversarial transformation.
2. Keep train/tuning data separate from a locked test set. Have at least two
   trained human raters label each item and adjudicate disagreements.
3. Report per-class recall and precision, BLOCK/REVIEW/ALLOW confusion matrices,
   high-severity false negatives, confidence intervals, and slice disparities.
4. Include flash inserts of 100–500 ms, slow fades, picture-in-picture, overlays,
   mirrored/cropped images, emoji substitutions, mixed scripts and spaced words.
5. Run guardian verification trials near the 18-year boundary and across
   demographic/device slices. Do not tune on the final evaluation set.
6. Instrument queue delay, cold start, model runtime, review wait time, appeal
   outcome and false-positive reversal. Choose Modal warm-container settings from
   measured latency and cost targets.
7. Add an explicit child/parent message that user-uploaded video audio is removed.
   If original audio is later supported, quarantine it and add ASR plus acoustic
   event/music-rights moderation before changing that promise.

## User-friendly ecosystem target

Safety states should be understandable: "Checking", "Needs parent review",
"Not allowed", and "Ready". Each non-public state needs a short reason, a safe
retry path, and—where appropriate—parent appeal/review. The client should never
promise publication while processing, and operational latency should not weaken
the server-side gate.

No production release should claim "zero leakage" or a letter grade until the
representative benchmark, live storage checks, role/authorization tests and
observability evidence are complete.
