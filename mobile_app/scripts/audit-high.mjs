import { spawnSync } from 'node:child_process';

const ALLOWED_NO_FIX = new Set([
  'GHSA-vfj7-8cjw-p6xm', // braces <=3.0.3: no patched upstream release
  'GHSA-86w9-cpqp-85rv', // node-forge 1.4.0 follow-up: no patched upstream release
]);

const rank = { low: 1, moderate: 2, high: 3, critical: 4 };
const run = spawnSync('npm', ['audit', '--json'], {
  encoding: 'utf8',
  maxBuffer: 20 * 1024 * 1024,
});

let report;
try {
  report = JSON.parse(run.stdout || '{}');
} catch (error) {
  console.error('Could not parse npm audit JSON.');
  console.error(run.stdout || run.stderr || String(error));
  process.exit(1);
}

const vulnerabilities = report.vulnerabilities || {};
const rootMemo = new Map();

function advisoryId(via) {
  const haystack = [via?.url, via?.title, via?.name, via?.source]
    .filter(Boolean)
    .join(' ');
  const match = haystack.match(/GHSA-[0-9a-z-]+/i);
  return match ? match[0].toUpperCase() : null;
}

function rootAdvisories(name, trail = new Set()) {
  if (rootMemo.has(name) && trail.size === 0) return new Set(rootMemo.get(name));
  if (trail.has(name)) return new Set();

  const vuln = vulnerabilities[name];
  if (!vuln || (rank[vuln.severity] || 0) < rank.high) return new Set();

  const nextTrail = new Set(trail);
  nextTrail.add(name);
  const roots = new Set();
  for (const via of Array.isArray(vuln.via) ? vuln.via : []) {
    if (typeof via === 'string') {
      for (const root of rootAdvisories(via, nextTrail)) roots.add(root);
      continue;
    }
    if ((rank[via?.severity] || 0) < rank.high) continue;
    roots.add(advisoryId(via) || `UNIDENTIFIED:${name}`);
  }

  if (trail.size === 0) rootMemo.set(name, [...roots]);
  return roots;
}

const highOrCritical = Object.keys(vulnerabilities).filter(
  (name) => (rank[vulnerabilities[name]?.severity] || 0) >= rank.high,
);

const blocked = [];
const accepted = [];
for (const name of highOrCritical) {
  const roots = rootAdvisories(name);
  const ids = [...roots];
  if (ids.length > 0 && ids.every((id) => ALLOWED_NO_FIX.has(id))) {
    accepted.push(name);
  } else {
    blocked.push({ name, roots: ids.length ? ids : ['UNRESOLVED_ROOT'] });
  }
}

if (accepted.length) {
  console.warn(
    'Accepted temporary no-fix advisories (transitive packages included): ' +
      accepted.sort().join(', '),
  );
}
if (blocked.length) {
  for (const item of blocked) {
    console.error(`Unapproved high/critical npm vulnerability: ${item.name} <- ${item.roots.join(', ')}`);
  }
  process.exit(1);
}

console.log('npm high/critical audit gate passed; only explicitly documented no-fix root advisories remain.');
