/**
 * Normalized mobile API errors.
 *
 * The backend communicates gates with HTTP status + `error` code strings
 * (and sometimes a `gate` field). This module keeps every parsing rule in one
 * pure, test-covered place so screens can render explicit UX for each gate:
 * 401 logged-out/invalid, 403 forbidden/disabled, 423 locked (quiet hours or
 * screen-time), 428 action-required (quiz/parent verification), 503
 * temporarily unavailable.
 */

export type GateKind =
  | 'quiz'
  | 'parent_verification'
  | 'email_verification'
  | 'quiet_hours'
  | 'screen_time'
  | null;

export class ApiError extends Error {
  readonly status: number;
  /** Backend `error` code, e.g. "quiz_required", "disabled_by_parent". */
  readonly code: string;
  readonly gate: GateKind;
  /** Extra payload passthrough (pending_token, feature, quiet, ...). */
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, gate: GateKind = null, details: Record<string, unknown> = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.gate = gate;
    this.details = details;
  }
}

const GATE_BY_CODE: Record<string, GateKind> = {
  onboarding_quiz_required: 'quiz',
  quiz_required: 'quiz',
  parent_verification_required: 'parent_verification',
  email_verification_required: 'email_verification',
  quiet_hours: 'quiet_hours',
  screen_time_limit: 'screen_time',
};

export function gateFor(status: number, code: string, payloadGate?: unknown): GateKind {
  if (typeof payloadGate === 'string') {
    if (payloadGate === 'quiz') return 'quiz';
    if (payloadGate === 'quiet_hours') return 'quiet_hours';
    if (payloadGate === 'screen_time') return 'screen_time';
  }
  const mapped = GATE_BY_CODE[code];
  if (mapped) return mapped;
  if (status === 423) return 'screen_time';
  if (status === 428) return 'quiz';
  return null;
}

export function parseErrorResponse(status: number, payload: unknown): ApiError {
  const body = (payload ?? {}) as Record<string, unknown>;
  const code = typeof body.error === 'string' && body.error ? body.error : httpFallbackCode(status);
  const gate = gateFor(status, code, body.gate);
  const message = userMessageFor(status, code, body);
  const { error: _e, ...details } = body;
  void _e;
  return new ApiError(status, code, message, gate, details as Record<string, unknown>);
}

function httpFallbackCode(status: number): string {
  if (status === 0) return 'network_unreachable';
  if (status === 401) return 'mobile_auth_required';
  if (status === 403) return 'forbidden';
  if (status === 404) return 'not_found';
  if (status === 423) return 'locked';
  if (status === 428) return 'action_required';
  if (status >= 500) return 'server_unavailable';
  return 'request_failed';
}

/**
 * Human-readable message per backend code. Backend validation errors for
 * registration/child-creation are already user-safe sentences, so when the
 * code is unknown we surface the backend `message`/`error_description` when
 * present instead of inventing wording.
 */
export function userMessageFor(status: number, code: string, body?: Record<string, unknown>): string {
  switch (code) {
    case 'network_unreachable':
      return 'LittleNet server is unreachable. Check your internet or local connection.';
    case 'insecure_api_configuration':
      return 'This LittleNet build is not connected to the secure production service. Please update the app.';
    case 'verification_offline':
      return 'Internet is required to complete verification.';
    case 'request_timeout':
      return 'LittleNet took too long to respond. Check your internet and try again.';
    case 'request_cancelled':
      return 'Request cancelled.';
    case 'invalid_credentials':
      return 'That username/email and password did not match. Try again.';
    case 'wrong_mode':
    case 'invalid_credentials_for_mode':
      return 'Invalid credentials for this login mode. Check you are using the right login (Kids, Parent, or Admin).';
    case 'account_inactive':
      return 'This account is not active. Finish verification or ask your parent for help.';
    case 'account_not_found':
    case 'user_not_found':
      return 'We could not find that account. Check the spelling and try again.';
    case 'pending_verification_expired':
      return 'That verification session expired. Register or log in again to get a fresh code.';
    case 'invalid_otp':
    case 'Incorrect verification code.':
      return 'That code is not correct. Check the email and try again.';
    case 'live_camera_photo_required':
      return 'A live camera photo is required. Please allow camera access and retake the photo.';
    case 'onboarding_quiz_required':
    case 'quiz_required':
      return 'A short safety quiz is required before continuing.';
    case 'quiz_bank_unavailable':
      return 'Quizzes are temporarily unavailable. Pull to retry in a moment.';
    case 'parent_verification_required':
      return 'Parent verification is not finished. Continue with email code and adult check.';
    case 'email_verification_required':
      return 'Verify the email code first, then continue with the adult check.';
    case 'age_estimate_ambiguous':
      return 'We could not confidently confirm adult age from this photo. Retake it in clear, even lighting.';
    case 'age_verification_unavailable':
      return 'Adult age verification is temporarily unavailable. Please try again in a moment.';
    case 'adult_verification_failed': {
      const reason = typeof body?.reason === 'string' ? body.reason : '';
      if (reason === 'age_estimate_ambiguous')
        return 'We could not confidently confirm adult age from this photo. Retake it in clear, even lighting.';
      if (reason === 'age_verification_unavailable')
        return 'Adult age verification is temporarily unavailable. Please try again in a moment.';
      return 'Adult verification failed. An adult guardian must complete this step.';
    }
    case 'adult_verification_unavailable':
      return 'Adult verification is temporarily busy. Please try again in a moment.';
    case 'disabled_by_parent':
      return 'This feature is turned off by parent controls.';
    case 'quiet_hours':
      return 'Quiet hours are on. LittleNet will be back after the quiet window.';
    case 'screen_time_limit':
      return 'Today\u2019s screen-time limit is reached. Come back tomorrow.';
    case 'role_forbidden':
      return 'Your account cannot open this section.';
    case 'parent_approval_required':
      return 'This needs your parent\u2019s approval. Ask your parent to do it from Parent Mode.';
    case 'parent_verification_incomplete':
      return 'This parent has not finished identity verification (email code plus live adult check). Activation is blocked until verification completes.';
    case 'mobile_auth_required':
    case 'token_role_mismatch':
      return 'Your session expired. Please log in again.';
    case 'session_revoked':
    case 'token_revoked':
      return 'Your session was ended for security (for example after a password or account change). Please log in again.';
    case 'child_not_found':
      return 'That child account was not found under your parent account.';
    case 'media_storage_unavailable':
      return 'Media is temporarily unavailable. Try again shortly.';
    default: {
      const backendMessage =
        (typeof body?.message === 'string' && body.message) ||
        (typeof body?.error_description === 'string' && body.error_description) ||
        '';
      if (backendMessage && backendMessage !== code) return backendMessage;
      // Registration/child-creation validation arrives as a human sentence in
      // the `error` field itself (e.g. duplicate username). Surface it verbatim.
      if (code.includes(' ')) return code;
      if (status === 0) return 'No connection to LittleNet. Check your internet and try again.';
      if (status >= 500) return 'LittleNet is temporarily busy. Please try again in a moment.';
      return 'Something went wrong. Please try again.';
    }
  }
}

/** Retry/backoff is only ever applied to safe (idempotent GET) requests. */
export function shouldRetryRequest(method: string, attempt: number, status: number): boolean {
  if (method.toUpperCase() !== 'GET') return false;
  if (attempt >= 2) return false;
  return status === 0 || status === 408 || status === 429 || status >= 500;
}

export function retryDelayMs(attempt: number): number {
  return Math.min(1000 * 2 ** attempt, 4000);
}
