# Tokens for repositories and private plugins

This directory contains local Git access credentials used by the sys_apps self-updater.

Permanent plugin-system documentation is in `docs/plugin-system.md`.

## File naming

Files use this format:

- `<token_id>.cd`

Reserved token IDs:

- `sys_apps.cd` — optional credentials for the main sys_apps repository
- `JBLibs-python.cd` — optional credentials for the mandatory JBLibs repository; updater falls back to `sys_apps.cd`
- `<plugin_id>.cd` — credentials for the matching entry in `pluginy.jsonc`

Each file contains one logical line:

```text
<username>:<token>
```

A final newline is allowed. The token settings menu writes files with mode `0600`.

## Security rules

Token files:

- are ignored by Git through `assets/tokens/*.cd`;
- must never be committed, logged, printed, pasted into documentation or included in diffs;
- must contain exactly one non-empty username and token separated by the first `:`;
- must not contain whitespace inside the username or token;
- are used only through a temporary Git credential-helper file that is removed after the command;
- may be created, replaced or removed through **Plugin settings** without displaying the stored token value.

A token grants repository access, but does not force a plugin to run. Local plugin state in `/etc/jb_sys_apps/plugins.jsonc` has priority: a plugin with `enabled: false` is skipped even when its token exists.
