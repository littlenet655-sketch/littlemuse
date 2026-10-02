# LittleNet Security Audit — Master Record

**Audit head:** `2ccee76` ("docs: refresh final deployment checklist") — freshest pushed `origin/main` at audit start.
**Fix commit (local, NOT pushed):** `35b5c1e` "fix(security): 4-team audit remediation — SHA-pin Actions, dbmate checksum, text-length caps, chat limit bound".
**Audit date:** 2026-09-22.
**Repo:** `~/workspace/littlemuse` — child-safe social platform (React Native/Expo mobile + Flask web + PostgreSQL + Modal AI tier + Cloudflare R2 media). Children use parent-created password login; parents use Android system authentication (no face auth anywhere — fully removed 2026-09-22).

> This report is the master record of a 4-team adversarial security audit. Severities below are exactly as the teams voted them; defeated findings were not upgraded; nothing is marked done without direct evidence.

---

## (a) Executive summary

A 4-team pipeline audited the LittleNet codebase:

1. **Team 1 (scan)** claimed 12 findings: 3 medium, 4 low, 5 info, **0 critical**.
2. **Team 2 (verify)** confirmed 10 of 12 as real, declared 2 false positives (T1-011 dead-helper claim — the helper is actually live; T1-012 auto-deploy claim — the job is gated on `[deploy-web]` / `workflow_dispatch`), found 0 duplicates, and added 1 new finding (T2-NEW-001, floating pip ranges).
3. **Team 3 (red team)** live-tested all 11 live findings against a local Flask + Postgres sandbox: **6 SURVIVE, 5 DEFEATED**. The red team could not break the moderation one-way ratchet, could not bypass token revocation, and demonstrated the email-XSS and URL-guard findings have no attacker→victim path.
4. **Coordinator fixes** (commit `35b5c1e`) remediated 5 findings: T1-001 (Actions SHA pinning), T1-002 (dbmate checksum), T1-003 (text-length caps), T1-005 (chat limit bound), T1-006 (stale camera strings).

**Headline counts:** 12 claimed → 10 confirmed + 2 false positives + 1 new (11 live) → 6 survived the red team → **5 fixed in 35b5c1e**.

**Overall verdict:** No critical, no high, and no remotely-exploitable unauthenticated vulnerability was found at any stage. The three medium findings (supply-chain CI tag mutability, dbmate fetch without integrity check, asymmetric DoS via unbounded text) all survived the red team and were fixed during this audit. The core child-safety invariant — fail-closed moderation that can only escalate, never downgrade — survived sustained break attempts. Two low-severity to-do items remain: per-account login throttling (T1-007) and a pinned Python lockfile for the AI/text/safety requirements (T2-NEW-001). **Post-fix, the codebase is in its strongest audited state; staging/production readiness still depends on the owner's tasks (secrets, Modal/R2 provisioning, device testing) per standing residuals.**

---

## (b) Methodology

| Team | Method | Constraints |
|---|---|---|
| Team 1 — Scan | Static scan of the full repo (source, 9 CI workflows, Dockerfiles, mobile app, templates) for security bugs; severity voted per finding (T1-001…T1-012). | Read-only. No execution. |
| Team 2 — Verify | Re-examined every Team 1 claim against the code verbatim; checked for duplicates; hunted areas Team 1 missed (dependency pins). | Read-only. No execution. |
| Team 3 — Red team | Attempted to actually exploit each live finding, including live tests against a local Flask + Postgres 16 sandbox (authenticated child user, seeded data, timed requests). Did not attempt upstream compromises (GitHub action tags, PyPI packages) — out of scope. | **Local sandbox only. Never external, never production.** |
| Team 4 — Document | This report. | No source modifications; report files only. |

Team inputs (read in full): `/tmp/security-audit/team1_findings.json`, `/tmp/security-audit/team2_verdicts.json`, `/tmp/security-audit/team3_redteam.json`.

---

## (c) What is working / ready and verified

These are defenses the teams verified, not assumptions:

- **Parameterized SQL everywhere.** Route/template/dynamic-SQL audits pass post-fix; no SQL injection surface found by scan or red team.
- **bcrypt password hashing** with generic login errors (no enumeration); password-reset OTP attempt cap enforced and carried across resends (OTP_MAX_ATTEMPTS=5).
- **Fail-closed moderation ratchet (T1-009)** — the red team's primary target, attacked on every surface and held:
  - Local deterministic BLOCK (grooming/self-harm/severe) returns *before* any AI call; the LLM can never see the message, let alone downgrade it.
  - `safety/text_service.py` merge uses `max()` on all scores; deterministic flags set unconditionally from local lexical hits; remote output cannot clear or lower a local verdict.
  - AI outage → `Decision('REVIEW')` (fail-closed), confirmed live: with text models absent, every message failed closed to BLOCK.
  - AI BLOCK → BLOCK; AI REVIEW can only escalate ALLOW → REVIEW, never downgrade.
  - Media pipeline: posts are born `PENDING`/`is_safe=FALSE` (invisible to `visible_posts`); worker exceptions → `FAILED` (invisible); caption precheck exception → 500 *before* the post row is created; REVIEW comments invisible to readers; unknown content types → BLOCK.
- **Token security (T1-010)** — live-tested: logout kills the used token (revocation-table hit) AND all sibling sessions (session_version bump); garbage tokens rejected; revocation lookup is fail-closed on DB exception; 73/82 mobile endpoints carry `@_require_mobile`, and the 10 without are legitimately public (health, login, registration, password reset, curated royalty-free music list, guarded mock-PUT). No refresh/impersonation minting path. Mobile tokens in `expo-secure-store`. 24h TTL accepted as designed.
- **CSRF scoping** — no gaps found.
- **Signed R2 URLs with per-role authorization** — no bypass found.
- **Quarantine upload pipeline** — invisible-until-allowed publication confirmed.
- **No secrets in repo** — gitleaks clean; CI post-fix pins third-party actions to SHAs.
- **Login throttling is IP-based and works as configured** (measured: 30/min enforced, correct password also 429'd inside the window) — it just doesn't stop distributed per-account attacks (→ to-do T1-007).

---

## (d) What was fixed during this audit

Commit `35b5c1e` "fix(security): 4-team audit remediation" (local, **not pushed** — awaiting owner's GitHub token, per standing procedure):

1. **T1-001 (medium) — Actions pinned to commit SHAs.** All 30 `uses:` lines across all 9 workflows now pin full commit SHAs (e.g. `actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4`). Closes the tag-retargeting supply-chain path the red team confirmed (tj-actions/changed-files precedent cited).
2. **T1-002 (medium) — dbmate binary SHA-256 verified.** Post-curl checksum verification added in both `Dockerfile` and `Dockerfile.web` (`b002d5249d53d0c6c482ed761b5a806c6fb9a364fcc5f9db3e8763c1d9e40e1d`); build fails on mismatch.
3. **T1-003 (medium) — Server-side text-length caps.** `Config.MAX_USER_TEXT_CHARS = 5000` enforced on all 7 text entry points (web + mobile chat, comments, captions). The red team measured ~1.6s server CPU per MB pre-fix; the cap bounds worst-case per-request cost to a fixed constant.
4. **T1-005 (low) — Chat history limit clamped.** `limit` bound to 1..100 (mirrors `conversations_page`); default no longer defaults to 2147483647 on the web chat path.
5. **T1-006 (low) — Stale camera permission strings corrected** in `mobile_app/app.json` (red team rated this "defeated — zero security impact", fixed as trust/wording hygiene).

**Post-fix verification:** backend pytest **563 passed / 4 skipped / 0 failed**; mobile jest **207/207**; `tsc` 0 errors; route/template/dynamic-SQL audits pass; all workflow YAML valid.

---

## (e) What is NOT ready — prioritized to-do list

| Priority | Finding | Severity | Red team | Status | What is needed | Owner |
|---|---|---|---|---|---|---|
| P1 | T1-007 — login rate limiting is IP-only, no per-account lockout | low | SURVIVES | **To-do** | Per-account failed-login tracking with progressive backoff or temporary lockout; keep responses timing-uniform. Deferred: auth-flow change, non-surgical. | Repo / future commit |
| P2 | T2-NEW-001 — floating pip ranges in requirements-ai/text/safety, no lockfile | low | SURVIVES | **To-do** | `pip-compile` lockfile or exact `==` pins (+ `--require-hashes`) for torch, ultralytics, transformers, nudenet, presidio-analyzer, spacy. Deferred: build-risky, touches Modal AI image builds. | Repo / future commit |
| — | T1-004 — approval-email HTML injection | low | DEFEATED | **Accepted residual** | Strictly self-XSS: OTP-gated recipient binding means markup only lands in the attacker's own verified inbox; all web templates autoescape. No attacker→victim path. Hygiene-only. | None |
| — | T1-008 — URL-guard IPv6/CGNAT gaps | info | DEFEATED | **Accepted** | Guard is a build-time misconfiguration tripwire, not a security boundary; no runtime-controllable URL surface exists. | None |

**Standing known residuals (unchanged by this audit):**
- `decode-uri-component` moderate npm advisory — unreachable in this app (no deep-link parsing); fix needs a react-navigation major bump.
- RapidOCR downloads onnx models on first runtime init — needs outbound network at first use (web + Modal AI image).
- npm registry audit blocked in sandbox; CI gate enforces (`npm-audit` fails on high/critical).
- **API keys, staging secrets, Modal/R2 provisioning, and deployment are the owner's task.** Release ZIP `your_files/LittleNet-deploy-ed74c95.zip` is built and verified (556,602,626 bytes, SHA-256 `bc6a9a95…4ff9834c`) but was built before this audit's fixes — **a new release ZIP must be built from final pushed HEAD after 35b5c1e is pushed.**
- No staging deploy, no live verification, no APK, no physical-device test performed (acceptance categories unchanged).

---

## (f) Risk register

| ID | Title | Severity | Team 1 | Team 2 | Team 3 | Status | Fixed in |
|---|---|---|---|---|---|---|---|
| T1-001 | Actions pinned to mutable tags, not SHAs | medium | claimed | confirmed | survives | **Fixed** | 35b5c1e |
| T1-002 | dbmate fetched via curl, no checksum | medium | claimed | confirmed | survives | **Fixed** | 35b5c1e |
| T1-003 | No server-side max text length (DoS) | medium | claimed | confirmed | survives | **Fixed** | 35b5c1e |
| T1-004 | Approval-email HTML injection (jinja2 no autoescape) | low | claimed | confirmed | defeated | Accepted residual (self-XSS only) | — |
| T1-005 | Unbounded `limit` in chat history fetch | low | claimed | confirmed | survives | **Fixed** | 35b5c1e |
| T1-006 | Stale camera permission strings claim "face checks" | low | claimed | confirmed | defeated (no vuln) | **Fixed** (wording hygiene) | 35b5c1e |
| T1-007 | Login rate limit per-IP only, no per-account lockout | low | claimed | confirmed | survives | **To-do** (P1) | — |
| T1-008 | URL guard misses IPv6/CGNAT/link-local ranges | info | claimed | confirmed | defeated (not a boundary) | Accepted | — |
| T1-009 | LLM safety output one-way ratchet | info | verified-holds | confirmed | defeated (red team could not break) | **Defense holds** | — |
| T1-010 | Mobile bearer tokens 24h TTL | info | mitigated | confirmed | defeated (revocation works live) | **Defense holds** | — |
| T1-011 | Dead math-challenge registration helper | info | claimed | **false positive** (helper is live; challenge logic inert — hygiene note) | — | Not a finding | — |
| T1-012 | Web-only workflow auto-deploys on every main push | info | claimed | **false positive** (job gated on `[deploy-web]`/workflow_dispatch) | — | Not a finding | — |
| T2-NEW-001 | Floating pip ranges, requirements-ai/text/safety | low | — | claimed+confirmed | survives | **To-do** (P2) | — |

**Severity totals:** 0 critical, 0 high, 3 medium, 6 low, 4 info (across 11 live findings). 0 criticals at every stage: scan, verify, red team, post-fix.

**Outcome categories:** fixed = 5 (T1-001, T1-002, T1-003, T1-005, T1-006) · defense holds = 2 (T1-009, T1-010) · accepted residual = 2 (T1-004, T1-008) · to-do = 2 (T1-007, T2-NEW-001) · false positive = 2 (T1-011, T1-012).

---

## (g) Appendices

### Appendix A — Per-finding evidence

Evidence locations are at the audit baseline (`2ccee76`); fixes are in `35b5c1e`.

- **T1-001** — `.github/workflows/ci.yml:34` `uses: actions/checkout@v4`; `:56` `uses: actions/setup-python@v5`; `:111` `uses: gitleaks/gitleaks-action@v2`; `release-web-validation.yml:80` `uses: zaproxy/action-baseline@v0.15.0`. Team 2: 30 `uses:` lines, 0 SHA pins, 9 workflow files (not 8). Team 3: preconditions for tag-retarget secret exfiltration (MODAL_TOKEN_SECRET in job env) all present; 2 third-party uses without tag-immutability guarantees.
- **T1-002** — `Dockerfile:5-7` and `Dockerfile.web:5-7`: `curl -fsSL -o /usr/local/bin/dbmate https://github.com/amacneil/dbmate/releases/download/v2.34.1/dbmate-linux-amd64 && chmod +x ... && dbmate --version`. No checksum/signature. Team 2: TLS is the only integrity protection.
- **T1-003** — `childMessage/routes.py:105` `text=(request.form.get('message_text') or '').strip()` (no length check); `mobile/api.py:1135` mobile chat POST; `uploadPost/routes.py:164` comment; `uploadPost/routes.py:115,261,295` captions; `mobile/api.py:1375` mobile_comment. Global bound only `config.py:27` `MAX_CONTENT_LENGTH = 100 * 1024 * 1024`. Team 3 live: 1MB→1.70s, 2MB→3.17s, 5MB→8.02s server CPU (~1.6s/MB), 60/min limit → pool saturation by one account.
- **T1-004** — `auth/service.py:319-325`: `jinja2.Template(f.read()).render(parent_name=parent_name, ...)` — plain `Template` (imported at `auth/service.py:5`) has autoescape off; `parent_name` only whitespace-stripped at `:56`; template `mailg/templates/approval_email.html` renders `{{ parent_name }}` raw. Team 2: fallback f-string path at `:311-316` unescaped too. Team 3: recipient is OTP-bound to the attacker's own inbox → self-XSS only, no victim path.
- **T1-005** — `childMessage/service.py:30`: `safe_limit = int(limit) if limit is not None else 2147483647` → raw `LIMIT %s`; `mobile/api.py:1118` passes `limit` straight through; web chat `childMessage/routes.py:99` calls `messages()` with no limit. Contrast `childMessage/service.py:89` `max(1, min(int(limit), 100))`. Team 3 live: `limit=1000000000` → 2000 seeded messages, 4.75MB JSON. (Team 3 correction to Team 2: parameterized `LIMIT -1` raises → HTTP 500, not LIMIT ALL.)
- **T1-006** — `mobile_app/app.json:37` `"cameraPermission": "LittleNet uses the camera for live face checks."`; `:44` image-picker variant. Team 2: camera plugin is live (`src/ui/nativeViews.tsx`, used by CreateScreen/VideoMedia/ReelPlayer) — permission legitimate, strings stale. Team 3: zero security impact, wording-only.
- **T1-007** — `auth/routes.py:106` `@limiter.limit('30 per minute')` web login; `mobile/api.py:693` mobile; `auth/api.py:255` `/api/login/` at 10/min; `extensions.py:9` `key_func=get_remote_address` (IP-only); repo-wide grep for per-account failure tracking: zero hits. Team 3 live: 29 wrong-password 401s → 30th 429 → correct password also 429 (IP window, zero account awareness); distributed N-IP attack unbounded per account.
- **T1-008** — `mobile_app/src/api/client.ts:10-27` `productionApiUrlProblem()` rejects non-https, localhost/127.0.0.1/::1, 10.x, 192.168.x, 172.16-31.x; missing fc00::/7, fe80::/10, 100.64.0.0/10, 169.254.0.0/16. Team 3: guard runs only on build-time `EXPO_PUBLIC_API_BASE_URL` in production builds, no runtime-controllable URL surface → no attacker path.
- **T1-009** — `childMessage/routes.py:115-118` and `mobile/api.py:1144-1147` return before AI on local BLOCK; `services/ai/client.py:62-69` fail-closed REVIEW on outage; merge `safety/text_service.py:293-309` max() + unconditional deterministic flags; route try/except → REVIEW. Team 3: attacked on all surfaces incl. media worker birth-invisible semantics — no downgrade path found.
- **T1-010** — `mobile/api.py:100` `_TOKEN_TTL` default 86400; `sver` claim `:143` checked live at `:220`; bumped on logout `:733`; `mobile_token_revocations` fail-closed read `:180-199`; storage `mobile_app/src/auth/storage.ts` expo-secure-store. Team 3 live: login→tokA+tokB→logout(tokA)→tokA 401 token_revoked, tokB 401 session_revoked. Decorator audit: 73/82 `@_require_mobile`; 10 public are legit.
- **T1-011** — `auth/api.py:20-29` `_registration_error`; Team 2: **false positive** — called at `auth/api.py:239,241` inside `parent_registration_email_gate` before_app_request. Hygiene note: the math-challenge values rendered are inert (template says no challenge; nothing validates `challenge_expected`).
- **T1-012** — `.github/workflows/deploy-web-only.yml:3-6`; Team 2: **false positive** — job gated `if: ${{ github.event_name == 'workflow_dispatch' || contains(github.event.head_commit.message, '[deploy-web]') }}`; a plain main push skips it. Residual: tag-triggered/manual deploy still lacks environment protection.
- **T2-NEW-001** — `requirements-ai.txt`: `torchvision>=0.28,<0.29`, `nudenet>=3.4,<4`, `ultralytics>=8.3,<9` (only opencv pinned `==`); `requirements-text.txt`: `torch>=2.13,<2.14`, `transformers>=5.0` (unbounded); `requirements-safety.txt`: `presidio-analyzer>=2.2,<3`, `spacy>=3.8,<4`; `Dockerfile:10`/`Dockerfile.web:10` install without lockfile/hashes; `modal_ai.py` inlines floating ranges. Team 3: precedent torchtriton PyPI compromise; classic dependency confusion not applicable (public names only).

### Appendix B — Team votes per finding

`T1 severity → T2 verdict → T3 outcome → final status`:

- T1-001 medium → confirmed → survives → **fixed (35b5c1e)**
- T1-002 medium → confirmed → survives → **fixed (35b5c1e)**
- T1-003 medium → confirmed → survives → **fixed (35b5c1e)**
- T1-004 low → confirmed → defeated → **accepted residual**
- T1-005 low → confirmed → survives → **fixed (35b5c1e)**
- T1-006 low → confirmed → defeated → **fixed (35b5c1e)** (hygiene, no vuln)
- T1-007 low → confirmed → survives → **to-do**
- T1-008 info → confirmed → defeated → **accepted**
- T1-009 info → confirmed → defeated → **defense holds**
- T1-010 info → confirmed → defeated → **defense holds**
- T1-011 info → **false positive** → — → not a finding
- T1-012 info → **false positive** → — → not a finding
- T2-NEW-001 low → confirmed → survives → **to-do**

### Appendix C — Fix verification record (35b5c1e)

- backend pytest: **563 passed / 4 skipped / 0 failed**
- mobile jest: **207/207**
- `tsc`: 0 errors
- route audit 0 errors · template audit 0 errors · dynamic-SQL audit 0 errors
- all 9 workflow YAML files parse valid
- Commit **not pushed**; no deploy, no APK, no device test performed in this audit.

---

*Written by Team 4 (documenters) from the full team inputs. This report modifies nothing; it records only what the teams found, verified, attacked, and fixed.*
