import http from 'k6/http';
import { check, fail, sleep } from 'k6';

const FULL = (__ENV.LOAD_PROFILE || '').toLowerCase() === 'full';

export const options = {
  stages: FULL
    ? [
        { duration: '20s', target: 10 },
        { duration: '20s', target: 50 },
        { duration: '20s', target: 100 },
        { duration: '30s', target: 250 },
        { duration: '30s', target: 500 },
        { duration: '30s', target: 1000 },
        { duration: '15s', target: 0 },
      ]
    : [
        { duration: '10s', target: 5 },
        { duration: '20s', target: 10 },
        { duration: '10s', target: 0 },
      ],
  thresholds: {
    http_req_failed: ['rate<0.02'],
    http_req_duration: ['p(95)<1000'],
  },
};

const BASE_URL = (__ENV.BASE_URL || '').replace(/\/+$/, '');
const TOKEN = __ENV.TOKEN || '';
const REEL_ID = Number(__ENV.REEL_ID || '0');

export function setup() {
  if (!BASE_URL) {
    fail('BASE_URL is required; run load tests only against an authorized staging environment.');
  }
  if (!/^https:\/\//.test(BASE_URL) && __ENV.ALLOW_HTTP_LOCAL !== '1') {
    fail('BASE_URL must use HTTPS unless ALLOW_HTTP_LOCAL=1 is explicitly set for localhost.');
  }
  if (!TOKEN) {
    fail('TOKEN is required; no bearer token is committed to the repository.');
  }
  return {};
}

const headers = {
  Authorization: 'Bearer ' + TOKEN,
  'Content-Type': 'application/json',
};

function expectNonServerError(name, response) {
  const checks = {};
  checks[name + ': no server error'] = (r) => r.status < 500;
  checks[name + ': not unauthorized'] = (r) => r.status !== 401;
  check(response, checks);
}

export default function () {
  const resHealth = http.get(BASE_URL + '/healthz');
  check(resHealth, { 'healthz: 200': (r) => r.status === 200 });

  const resMobile = http.get(BASE_URL + '/api/mobile/v1/health');
  check(resMobile, { 'mobile health: 200': (r) => r.status === 200 });

  const resFeed = http.get(BASE_URL + '/api/mobile/v2/kids/feed?cursor=0&limit=10&mode=for_you', { headers });
  expectNonServerError('feed', resFeed);

  const resReels = http.get(BASE_URL + '/api/mobile/v2/kids/reels?cursor=0&limit=8', { headers });
  expectNonServerError('reels metadata', resReels);

  const resDiscover = http.get(BASE_URL + '/api/mobile/v2/kids/discover', { headers });
  expectNonServerError('discover', resDiscover);

  const resNotifications = http.get(BASE_URL + '/api/mobile/v1/kids/notifications', { headers });
  expectNonServerError('notifications', resNotifications);

  if (REEL_ID > 0) {
    const playback = http.get(BASE_URL + '/api/mobile/v2/kids/reels/' + REEL_ID + '/playback', { headers });
    expectNonServerError('playback credential', playback);
  }

  sleep(FULL ? 0.2 : 0.5);
}
