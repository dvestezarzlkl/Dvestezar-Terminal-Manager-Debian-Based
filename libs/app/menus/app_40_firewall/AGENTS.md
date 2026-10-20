# Firewall Manager / UFW scoped agent instructions

- This first stage (module version 0.1.0) is intentionally **read-only**:
  `policy.py` is pure, `hub_provider.py` calls only UFW `status` and
  `--version`, and `menu.py` only reads existing UFW data. No UFW reload,
  no write to `/etc/ufw`, no remote Apply, no local config migration.
- Future Apply belongs to a separate guarded and tested implementation.
  It must stage+validate candidate config, arm automatic rollback before
  applying, verify new remote access and rollback on missing acknowledgement.
- Original manual `ufw_opevpn_update_form_cfg_json.py` behavior was intentional
  (regenerates timestamp, backups and reloads on every manual invocation).
  It is deprecated but remains operational during migration.
- Preserve both exact deployed legacy BOF/EOF managed blocks and their order:
  OpenVPN BAN/forward isolation precedes ZLKL Hard Source Allow.
  Invalid, duplicate or mismatched blocks MUST fail closed (inspection error).
- Semantically compare executable rules excluding audit comments/timestamps;
  content order matters. No difference means `NO_CHANGE`; a BAN with
  `banTo=YYYY-MM-DD` expires after that calendar day, so unchanged source
  configuration may still yield a changed effective ruleset.
- Hub provider can only return the fixed `service` dataset with one
  `HubService(service_key="ufw")`; never get SQL credentials or choose a
  table. No new DB migration for basic UFW presence/state.
- No UFW system administration code belongs in the headless
  `hub_provider.py` beyond safe read-only discovery; no imports of menu.py
  from headless collection.
- Do not infer that `ufw status: active` proves the presence or precedence
  of loaded OpenVPN/custom rules; they need separate read-only validation.
- Future central configuration must integrate existing Hub and the versioned
  `SYSAPP1E` settings registry, not create a second config transport.
- New menu text belongs in default and cs-CZ localization. Keep exact
  `_MENU_NAME_`, `_VERSION_`, `menu(c_menu)` contracts for discovery.
- Physical VM test is required before any UFW apply/legacy takeover.
