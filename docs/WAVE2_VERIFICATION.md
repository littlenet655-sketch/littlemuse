# Wave 2 verification scope

This branch is intentionally limited to lightweight safety/privacy hardening:

- replay-resistant two-parent friendship activation at the PostgreSQL trigger layer;
- canonical post/story visibility checks before local or R2 media delivery;
- active-friend requirement for direct message media after friendship changes;
- discovery authorization for child profile-picture delivery;
- Messages Notes limited to ACTIVE two-parent-approved friends, excluding blocked/muted peers.

No heavyweight Hugging Face candidate is enabled on the default request path in this wave.
