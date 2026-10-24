# Firewall Manager / UFW scoped agent instructions

- Module 0.4.0 may edit **local desired state only** in `/etc/jb_sys_apps/firewall.json`; this is not UFW Apply. Config v2 owns a `vpn_servers` catalog with stable `server_id` plus rules that may reference it through `vpn_server_id`. Loading config v1 must migrate in memory without losing src/dst port expressions; saving writes v2 so older clients fail closed instead of silently discarding new fields.
- Use standard JBLibs `c_menu`/`select()`/`get_input()`/`printBlock()`/`confirm()` and `selectFile()`; never introduce a parallel terminal UI/input layer. Wizard input must redraw accepted values before the next prompt like Node-RED `install_instance.py::print_newInstance()`. Interface discovery must reuse JBLibs `getInterfaces()`; select choices must be short and collision-free because the framework bounds choice length.
- Local VPN servers and rules belong only to the current host. Hub collectors `firewall_vpn_servers` and `firewall_rules` may publish only `origin=host_local,target_kind=host` when schema >=008; they must never touch future central host/group/all rows.
- UFW runtime remains **read-only**: `policy.py` is pure, `hub_provider.py` calls only UFW status/version, comparison only reads `before.rules`. No UFW reload, no write to `/etc/ufw`, no remote Apply.
- Pure `reconcile.py` only classifies plan against verified prior `applied_hash`; never mutates prior state or advances `last_applied_at`. Missing prior hash needs review; unexpected drift blocks automatic Apply. This release has NO persistent state and NO UFW Apply.
- Future Apply belongs to a separate guarded and tested implementation.
  It must stage+validate candidate config, arm automatic rollback before
  applying, verify new remote access and rollback on missing acknowledgement.
- Original manual `ufw_opevpn_update_form_cfg_json.py` behavior was intentional
  (regenerates timestamp, backups and reloads on every manual invocation).
  It is deprecated but remains operational during migration.
- Preserve deployed legacy BOF/EOF ownership and order. Multiple uniquely identified OpenVPN BAN/forward-isolation blocks are allowed and all must precede the single ZLKL Hard Source Allow block. Duplicate OpenVPN marker identities, duplicate Hard Source blocks, nested/unmatched markers or reversed ordering MUST fail closed. A VPN preview must use that server's configured interface, not silently fall back to `tun+`.
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
