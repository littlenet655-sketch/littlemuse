import { apiRequest, routes } from './client';

export type Role = 'CHILD' | 'PARENT' | 'ADMIN';
export type LoginMode = 'kids' | 'parent' | 'admin';

export interface ChildOnboardingState {
  quiz_required: boolean;
}

/** Authoritative gate state. Absent for PARENT/ADMIN. */
export type OnboardingState = ChildOnboardingState;

export interface SessionUser {
  user_id: number;
  username: string;
  full_name: string;
  email: string;
  role: Role;
  age: number | null;
  profile: Record<string, unknown> | null;
  quiz_required: boolean;
  posts_seen: number;
  quiz_interval: number;
}

export interface LoginResponse {
  ok: boolean;
  token: string;
  auth_method: string;
  user: SessionUser;
  onboarding?: OnboardingState;
}

export interface ParentRegisterInput {
  username: string;
  full_name: string;
  email: string;
  password: string;
  /** YYYY-MM-DD; backend requires 18+. */
  dob: string;
  guardian_declaration?: '1';
}

export interface CreateChildInput {
  username: string;
  full_name: string;
  age: number;
  password: string;
  date_of_birth?: string;
  school_name?: string;
  location?: string;
  current_class?: string;
  bio?: string;
  daily_limit?: number;
}

async function post<T>(path: string, body: Record<string, unknown>, token?: string, timeoutMs?: number): Promise<T> {
  return apiRequest<T>(path, { method: 'POST', body: JSON.stringify(body), timeoutMs }, token);
}

export function login(identifier: string, password: string, mode: LoginMode): Promise<LoginResponse> {
  return post<LoginResponse>(routes.login, { identifier, password, mode });
}

export function logout(token: string): Promise<{ ok: boolean }> {
  return post<{ ok: boolean }>(routes.logout, {}, token);
}

export function fetchMe(token: string): Promise<{ ok: boolean; user: SessionUser; onboarding?: OnboardingState | null }> {
  return apiRequest(routes.me, {}, token);
}

export function registerParent(input: ParentRegisterInput): Promise<{ ok: boolean; pending_token: string; email_sent: boolean; dev_code?: string }> {
  return post(routes.parentRegister, { ...input, guardian_declaration: '1' });
}

export function verifyParentEmail(pendingToken: string, otp: string): Promise<LoginResponse> {
  // Email OTP is the final server-side parent activation step. On success
  // the backend returns a signed-in session directly (parent face/liveness
  // verification was removed; device authentication gates Parent Mode).
  return post<LoginResponse>(routes.parentVerifyEmail, { pending_token: pendingToken, otp });
}

export function resendParentEmail(pendingToken: string): Promise<{ ok: boolean; error?: string | null; dev_code?: string }> {
  return post(routes.parentResendEmail, { pending_token: pendingToken });
}

export type ParentEmailDeliveryStatus =
  | 'UNKNOWN'
  | 'ACCEPTED'
  | 'SENT'
  | 'DELIVERED'
  | 'DELIVERY_DELAYED'
  | 'BOUNCED'
  | 'SUPPRESSED'
  | 'FAILED'
  | 'COMPLAINED';

export function fetchParentEmailStatus(
  pendingToken: string,
): Promise<{ ok: boolean; status: ParentEmailDeliveryStatus; delivery_failed: boolean }> {
  return post(routes.parentEmailStatus, { pending_token: pendingToken });
}

export function createChild(token: string, input: CreateChildInput): Promise<{ ok: boolean; child_id: number; next_steps: string[] }> {
  return post(routes.parentCreateChild, { ...input }, token, 60000);
}

export function requestPasswordReset(identifier: string): Promise<{ ok: boolean; user_id?: number; masked_email?: string; is_parent_proxy?: boolean; message: string }> {
  return post(routes.forgotPassword, { identifier });
}

export function resetPassword(userId: number, code: string, newPassword: string): Promise<{ ok: boolean; message: string }> {
  return post(routes.resetPassword, { user_id: userId, code, new_password: newPassword });
}

export interface QuizItem {
  quiz_id: number;
  category: string;
  question: string;
  options: string[];
}

export interface QuizResponse {
  ok: boolean;
  reason: 'onboarding' | 'feed_break' | 'practice';
  required: boolean;
  quizzes: QuizItem[];
}

export interface QuizAnswerResponse {
  ok: boolean;
  correct: boolean;
  correct_answer: string;
  xp: number;
  explanation: string;
  onboarding_complete: boolean;
  required: boolean;
}

export function fetchQuiz(token: string, limit?: number): Promise<QuizResponse> {
  const query = limit ? `?limit=${encodeURIComponent(String(limit))}` : '';
  return apiRequest<QuizResponse>(`${routes.quiz}${query}`, {}, token);
}

export function answerQuiz(token: string, quizId: number, answer: string): Promise<QuizAnswerResponse> {
  return apiRequest<QuizAnswerResponse>(routes.quizAnswer(quizId), { method: 'POST', body: JSON.stringify({ answer }) }, token);
}
