# LittleNet — What to Show in Viva

Use this order so the demo follows the locked current project instead of older audio/Whisper claims.

| Demo screen / action | What is happening | AI / service to mention |
|---|---|---|
| Parent signup | Email ownership and adult guardian onboarding | OTP + live camera + server-side anti-spoof/adult verification |
| Parent creates child | Parent-first account and initial controls | PostgreSQL transaction + email confirmation |
| Kids Home | Safe Feed/Stories/Clips plus Learn | Parent Controls + compulsory quiz gate |
| Find friends | Non-global school/network discovery | PostgreSQL authorization rules |
| Upload safe text/image | Safety checked before visibility | Detoxify/PII + NudeNet/Falconsai/CLIP/YOLO |
| Upload 18+ test image | Explicit evidence becomes BLOCK | NSFW hard-block policy |
| Upload weapon test | Dangerous object becomes REVIEW/BLOCK by evidence threshold | OpenImages-capable YOLO + policy |
| Upload video/Clip | Sampled frames pass the visual ensemble; audio is removed before storage | PySceneDetect/OpenCV + visual ensemble + FFmpeg sanitization |
| Parent Review | Borderline media waits for explicit decision | ALLOW/REVIEW/BLOCK + audit history |
| Approved-only chat | Two-parent-approved friends only; supported text/media are moderated | social authorization + safety policy |
| Screen time + quiet hours | Server-owned limits and lockouts | usage/control services + PostgreSQL |
| Child login | Child password login plus compulsory onboarding quiz | Auth routes + quiz service |
| Live Safety | Camera frames sampled without retaining normal frames | fail-closed visual moderation |
| Admin moderation | Review signals/audit and removal actions | moderation events + audit log |
| Learning | Age-group quizzes/challenges | seeded PostgreSQL quiz data |
| Android app | WebView uses the same verified HTTPS backend | same Flask + AI safety APIs |

## One-sentence architecture answer

“LittleNet checks child-generated text, images and video through modality-specific safety models, combines evidence in a fail-closed policy, blocks hard violations before visibility, sends uncertainty to Parent Review, and applies the same parent/social controls on web and Android.”

## Five points to emphasize

1. Safety is enforced before visibility.
2. Child discovery/chat is not a global stranger network.
3. Video is visually moderated and its unmoderated audio track is stripped before persistence.
4. Parent controls are enforced server-side, not by hiding buttons.
5. AI/dependency failure does not silently turn into ALLOW.
