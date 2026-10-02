import { apiRequest, routes } from './client';

export type DemoBoostStatusName = 'OFF' | 'WARMING' | 'READY';

export interface DemoBoostState {
  active: boolean;
  status: DemoBoostStatusName;
  remaining_seconds: number;
  expires_at?: string | null;
  started_at?: string | null;
  last_error?: string | null;
}

export interface DemoBoostResponse {
  ok: boolean;
  demo_boost: DemoBoostState;
}

export function fetchDemoBoostStatus(token: string): Promise<DemoBoostResponse> {
  return apiRequest(routes.demoBoostStatus, {}, token);
}

function postMinutes(path: string, token: string, minutes: number): Promise<DemoBoostResponse> {
  return apiRequest(
    path,
    { method: 'POST', body: JSON.stringify({ minutes }) },
    token,
  );
}

export function startDemoBoost(token: string, minutes: 15 | 30 | 60): Promise<DemoBoostResponse> {
  return postMinutes(routes.adminDemoBoostStart, token, minutes);
}

export function extendDemoBoost(token: string, minutes: 5 | 15 | 30): Promise<DemoBoostResponse> {
  return postMinutes(routes.adminDemoBoostExtend, token, minutes);
}

export function stopDemoBoost(token: string): Promise<DemoBoostResponse> {
  return apiRequest(routes.adminDemoBoostStop, { method: 'POST' }, token);
}


/**
 * Poll fast only while a boost is actually running (countdown warnings matter);
 * otherwise back off so idle devices don't hit the API twice a minute. React
 * Query already pauses intervals while the app is backgrounded.
 */
export function demoBoostPollMs(active: boolean | undefined, activeMs: number, idleMs: number): number {
  return active ? activeMs : idleMs;
}
