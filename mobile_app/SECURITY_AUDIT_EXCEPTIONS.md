# Temporary npm audit exceptions

The release gate still fails on every unapproved **high** or **critical** npm advisory.

Two transitive Expo/Metro build-tool advisories are temporarily accepted because no patched upstream release exists as of 2026-10-06:

- `GHSA-vfj7-8cjw-p6xm` — `braces <= 3.0.3`. The package is reached through Metro/micromatch for local project glob processing; LittleNet does not pass child/user content into glob patterns.
- `GHSA-86w9-cpqp-85rv` — `node-forge 1.4.0`. The package is reached through Expo CLI code-signing tooling and is not used by LittleNet application runtime cryptography.

`source-map-js` is **not** excepted: it has a patched 1.2.2 release and the lockfile is pinned to that version.

Remove each exception immediately when its upstream project publishes a patched compatible release.
