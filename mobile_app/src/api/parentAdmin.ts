import { apiRequest, routes } from './client';

export interface ParentControls {
  child_id?: number;
  allow_reels: boolean;
  allow_stories: boolean;
  allow_messaging: boolean;
  allow_posting: boolean;
  allow_discover: boolean;
  quiet_hours_enabled: boolean;
  quiet_start: string;
  quiet_end: string;
  educational_only_feed: boolean;
  allowed_categories: string[];
  quiz_pacing_policy?: 'FREQUENT' | 'BALANCED' | 'LIGHT';
}

export interface TimeLimit {
  child_id: number;
  daily_limit_minutes: number;
  strict_mode: boolean;
  updated_at?: string;
}

export interface ParentChild {
  user_id: number;
  username: string;
  full_name: string;
  age: number | null;
  account_status: string;
  avatar_url?: string | null;
  minutes_today: number;
  limit: TimeLimit | null;
  safety: { safety_level?: string };
  open_reviews: number;
  controls: ParentControls;
  presence?: { online?: boolean; last_seen_at?: string | null };
  behavior?: { score?: number; level?: string; trend?: string; reasons?: string[] };
  quiz_7d: { attempted: number; correct: number; accuracy: number };
}

export interface FollowRequest {
  child_id: number;
  following_child_id: number;
  requester_name: string;
  target_name: string;
  approval_stage: string;
  actionable: boolean;
  approval_direction: 'OUTGOING' | 'INCOMING' | 'WAITING';
  stage_help: string;
  created_at?: string;
}

export interface ParentDashboardResponse {
  ok: boolean;
  children: ParentChild[];
  unread: number;
  pending: FollowRequest[];
}

export interface ReviewPreview {
  media_type?: string;
  media_url?: string | null;
  poster_url?: string | null;
  caption?: string | null;
  comment_text?: string | null;
  message_type?: string;
  message_text?: string | null;
  moderation_status?: string;
}

export interface ReviewEvent {
  event_id: number;
  child_id: number;
  full_name?: string;
  username?: string;
  content_type: string;
  content_id?: number | null;
  risk_score?: number | string | null;
  decision: string;
  reason?: string | null;
  status: string;
  created_at?: string;
  preview?: ReviewPreview | null;
}

export interface ParentNotification {
  notification_id: number;
  child_id: number;
  notification_type: string;
  notification_message: string;
  target_url?: string | null;
  is_read: boolean;
  created_at?: string;
}

export interface ActivityEvent {
  log_id: number;
  activity_type: string;
  activity_data?: Record<string, unknown>;
  created_at?: string;
}

export interface AdminUser {
  user_id: number;
  username: string;
  full_name: string;
  email: string;
  role: 'CHILD' | 'PARENT' | 'ADMIN';
  age?: number | null;
  account_status: string;
  created_at?: string;
}

export interface AdminAuditEvent {
  audit_id: number;
  admin_id: number;
  admin_name: string;
  action: string;
  target_type?: string | null;
  target_id?: number | null;
  details?: Record<string, unknown>;
  created_at?: string;
}

function body(value: Record<string, unknown>): RequestInit {
  return { method: 'POST', body: JSON.stringify(value) };
}

export function fetchParentDashboard(token: string, signal?: AbortSignal): Promise<ParentDashboardResponse> {
  return apiRequest(routes.parentDashboard, { signal }, token);
}

export function fetchParentControls(token: string, childId: number): Promise<{ ok: boolean; controls: ParentControls; time_limit: TimeLimit | null; categories: string[] }> {
  return apiRequest(routes.parentControls(childId), {}, token);
}

export function updateParentControls(token: string, childId: number, controls: ParentControls): Promise<{ ok: boolean; controls: ParentControls; time_limit: TimeLimit | null; categories: string[] }> {
  return apiRequest(routes.parentControls(childId), { method: 'PUT', body: JSON.stringify(controls) }, token);
}

export function updateTimeLimit(token: string, childId: number, dailyLimitMinutes: number, strictMode: boolean): Promise<{ ok: boolean; limit: TimeLimit }> {
  return apiRequest(routes.parentTimeLimit(childId), { method: 'PUT', body: JSON.stringify({ daily_limit_minutes: dailyLimitMinutes, strict_mode: strictMode }) }, token);
}

export function resetChildScreenTime(token: string, childId: number): Promise<{ ok: boolean; message: string; minutes_today: number }> {
  return apiRequest(routes.parentResetTimeLimit(childId), { method: 'POST' }, token);
}

export function extendChildScreenTime(token: string, childId: number, additionalMinutes = 30): Promise<{ ok: boolean; message: string; daily_limit_minutes: number }> {
  return apiRequest(routes.parentExtendTimeLimit(childId), { method: 'POST', body: JSON.stringify({ additional_minutes: additionalMinutes }) }, token);
}

export function fetchParentSafety(token: string): Promise<{ ok: boolean; events: ReviewEvent[] }> {
  return apiRequest(routes.parentSafety, {}, token);
}

export function resolveParentReview(token: string, eventId: number, action: 'APPROVE' | 'BLOCK'): Promise<{ ok: boolean; result: string }> {
  return apiRequest(routes.parentReview(eventId), body({ action }), token);
}

export function fetchFollowRequests(token: string): Promise<{ ok: boolean; pending: FollowRequest[] }> {
  return apiRequest(routes.parentFollowRequests, {}, token);
}

export function resolveFollowRequest(token: string, childId: number, targetId: number, action: 'approve' | 'reject'): Promise<{ ok: boolean; action: string }> {
  return apiRequest(routes.parentFollowAction, body({ child_id: childId, target_id: targetId, action }), token);
}

export function fetchParentNotifications(token: string): Promise<{ ok: boolean; notifications: ParentNotification[] }> {
  return apiRequest(routes.parentNotifications, {}, token);
}

export function markParentNotificationsRead(token: string): Promise<{ ok: boolean; notifications: ParentNotification[] }> {
  return apiRequest(routes.parentNotifications, body({}), token);
}

export function fetchParentActivity(token: string, childId: number): Promise<{ ok: boolean; events: ActivityEvent[] }> {
  return apiRequest(routes.parentActivity(childId), {}, token);
}

/** Read-only per-child viewing insights: watch totals (7d/30d), per-category
    breakdown, and top reels. Served by parent/api.py; the server enforces the
    parent-owns-child gate. */
export interface ViewingInsights {
  success: boolean;
  child_id: number;
  windows: {
    '7d': { views: number; watch_seconds: number };
    '30d': { views: number; watch_seconds: number };
  };
  by_category: { category: string; views: number; watch_seconds: number }[];
  top_reels: { kind: string; id: number; title: string; category: string; views: number; watch_seconds: number }[];
}

export function fetchViewingInsights(token: string, childId: number): Promise<ViewingInsights> {
  return apiRequest(routes.parentViewingInsights(childId), {}, token);
}

/** Parent sets a new password for their linked child (backend enforces 8+ chars). */
export function resetChildPassword(token: string, childId: number, newPassword: string): Promise<{ ok: boolean; message: string }> {
  return apiRequest(routes.parentResetChildPassword(childId), { method: 'POST', body: JSON.stringify({ new_password: newPassword }) }, token);
}

/** Parent unlinks a child: mapping deleted and child account deactivated server-side. */
export function unlinkChild(token: string, childId: number): Promise<{ ok: boolean; message: string }> {
  return apiRequest(routes.parentChild(childId), { method: 'DELETE' }, token);
}

export function fetchAdminDashboard(token: string): Promise<{ ok: boolean; counts: { users: number; children: number; parents: number; open_reviews: number } }> {
  return apiRequest(routes.adminDashboard, {}, token);
}

export function fetchAdminReviews(token: string): Promise<{ ok: boolean; events: ReviewEvent[] }> {
  return apiRequest(routes.adminReviews, {}, token);
}

export function fetchAdminReview(token: string, eventId: number): Promise<{ ok: boolean; event: ReviewEvent; preview: ReviewPreview | null }> {
  return apiRequest(routes.adminReview(eventId), {}, token);
}

export function resolveAdminReview(token: string, eventId: number, action: 'APPROVE' | 'BLOCK' | 'ESCALATE', notes?: string): Promise<{ ok: boolean; action: string; status: string }> {
  return apiRequest(routes.adminReview(eventId), body({ action, notes: notes?.trim() || undefined }), token);
}

export function fetchAdminUsers(token: string, query: string): Promise<{ ok: boolean; users: AdminUser[] }> {
  const suffix = query.trim() ? `?q=${encodeURIComponent(query.trim())}` : '';
  return apiRequest(`${routes.adminUsers}${suffix}`, {}, token);
}

export function updateAdminUserStatus(token: string, userId: number, status: 'ACTIVE' | 'SUSPENDED'): Promise<{ ok: boolean; user_id: number; status: string }> {
  return apiRequest(routes.adminUserStatus(userId), body({ status }), token);
}

export function fetchAdminAudit(token: string): Promise<{ ok: boolean; events: AdminAuditEvent[] }> {
  return apiRequest(routes.adminAudit, {}, token);
}
