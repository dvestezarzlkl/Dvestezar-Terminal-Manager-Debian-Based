# SysApps Hub instructions

- SysApps Hub is a central inventory. MySQL/MariaDB is the transport and storage layer, not the provider API.
- Provider modules never receive a database connection, cursor, table name, SQL fragment, credentials, or migration access. They return typed snapshots only.
- Dynamic `app_*` providers register through module-level `_HUB_PROVIDER_KEY_` and `hub_collect(context)`. Provider keys must be stable, unique, lowercase identifiers.
- The central runtime maps a fixed dataset name to a fixed writer. A provider cannot select or construct a table name.
- Table identifiers are built only from a strictly validated global prefix and a hard-coded suffix allowlist. All values use parameterized SQL.
- Schema changes belong in ordered `migrations/NNN_name.sql` files. The only supported template placeholder is `{{PREFIX}}`; statements are separated by a line containing exactly `-- statement`.
- Applied migrations are recorded with version and SHA-256. A checksum mismatch is an error and must never be silently accepted.
- Each provider synchronizes in its own transaction. A provider failure records an error state and preserves its previous inventory; it must not roll back core host data or other providers.
- Stale provider records may be deleted only after a complete successful snapshot from that provider.
- Hub unavailability, missing schema, or provider failure must never block ordinary local sys_apps functions or a successful local Save.
- Database passwords must not appear in repr output, logs, error messages, status text, mail, tests, or commits. Exported settings use the versioned password-encrypted one-line package; never add a fixed application encryption key.
- The host identity is the existing `cfg.machineInfo.machine_id`, with `/etc/machine-id` only as a fallback. Do not invent another host ID.
- Node-RED inventory contains editor/Admin API users and RW/R access only. Never export bcrypt hashes, plaintext passwords, credentials, or legacy `httpNodeAuth` as Dashboard users.
