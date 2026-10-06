import { spawnSync } from 'node:child_process';

const ALLOWED_NO_FIX = new Set([
  'GHSA-vfj7-8cjw-p6xm', // braces <=3.0.3: upstream has no patched release
  'GHSA-86w9-cpqp-85rv', // node-forge 1.4.0 follow-up: upstream has no patched release
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
const memo = new Map();

function advisoryAllowed(via) {
  const haystack = [
    via?.url,
    via?.title,
    via?.name,
    via?.source,
  ].filter(Boolean).join(' ');
  return [...ALLOWED_NO_FIX].some((id) => haystack.includes(id));
}

function packageAllowed(name, trail = new Set()) {
  if (memo.has(name)) return memo.get(name);
  if (trail.has(name)) return false;
  const vuln = vulnerabilities[name];
  if (!vuln || (rank[vuln.severity] || 0) < rank.high) {
    memo.set(name, true);
    return true;
  }

  const nextTrail = new Set(trail);
  nextTrail.add(name);
  const vias = Array.isArray(vuln.via) ? vuln.via : [];
  if (!vias.length) {
    memo.set(name, false);
    return false;
  }

  const allowed = vias.every((via) => {
    if (typeof via === 'string') {
      return packageAllowed(via, nextTrail);
    }
    if ((rank[via?.severity] || 0) < rank.high) return true;
    return advisoryAllowed(via);
  });
  memo.set(name, allowed);
  return allowed;
}

const highOrCritical = Object.keys(vulnerabilities).filter(
  (name) => (rank[vulnerabilities[name]?.severity] || 0) >= rank.high,
);
const blocked = highOrCritical.filter((name) => !packageAllowed(name));
const accepted = highOrCritical.filter((name) => packageAllowed(name));

if (accepted.length) {
  console.warn(
    'Accepted temporary no-fix advisories (transitive packages included): ' +
      accepted.sort().join(', '),
  );
}
if (blocked.length) {
  console.error('Unapproved high/critical npm vulnerabilities: ' + blocked.sort().join(', '));
  process.exit(1);
}

console.log('npm high/critical audit gate passed; only explicitly documented no-fix advisories remain.');
