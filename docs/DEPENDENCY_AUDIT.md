# Mobile Dependency Audit

Audit date: 2026-09-13

Commands executed in `mobile_app/`:

```bash
npm install
npm audit --json
npx expo install --check
```

Result: 16 moderate, 0 high, 0 critical findings. No direct package has a safe compatible upgrade reported by npm for the current Expo SDK 57 stack.

## Classification

| Chain | Reachability | Classification | Decision |
|---|---|---|---|
| Expo CLI/config/plugin packages -> `xcode` -> `uuid` | Build/config tooling | Transitive; not application runtime logic | Accept temporarily. npm proposes Expo 46, a breaking downgrade from SDK 57. |
| React Navigation -> `query-string` -> `decode-uri-component` | URI/deep-link parsing may be runtime reachable | Transitive; malformed-input denial-of-service advisory | Accept temporarily. npm proposes React Navigation 3/5, incompatible with the current Navigation 7 APIs. The app does not configure external linking routes. |
| Expo package umbrella | Framework dependency | Direct framework package reporting transitive advisories | Keep SDK 57. `expo install --check` reports dependencies up to date. |

`npm audit fix --force` was not run. Its proposed framework downgrades would destabilize the native client and do not represent a safe submission-week upgrade. Recheck the same chains when compatible Expo 57 / React Navigation 7 releases are published.
