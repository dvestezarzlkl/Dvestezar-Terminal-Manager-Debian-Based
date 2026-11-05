# Firewall Manager / UFW scoped agent instructions

- Module 0.5.2 owns local desired state in `/etc/jb_sys_apps/firewall.json` and may mutate UFW **only through the explicit guarded manual Apply/Enable/Disable workflow in `apply.py`**. Config v2 owns a `vpn_servers` catalog with stable `server_id` plus rules that may reference it through `vpn_server_id`. Loading config v1 must migrate in memory without losing src/dst port expressions; saving writes v2 so older clients fail closed instead of silently discarding new fields.
- Use standard JBLibs `c_menu`/`select()`/`get_input()`/`printBlock()`/`confirm()` and `selectFile()`; never introduce a parallel terminal UI/input layer. Wizard input must redraw accepted values before the next prompt like Node-RED `install_instance.py::print_newInstance()`. Interface discovery must reuse JBLibs `getInterfaces()`; select choices must be short and collision-free because the framework bounds choice length.
- Local VPN servers and rules belong only to the current host. Hub collectors `firewall_vpn_servers` and `firewall_rules` may publish only `origin=host_local,target_kind=host` when schema >=008; they must never touch future central host/group/all rows.
- `policy.py` and `compiler.py` remain pure. `hub_provider.py` calls only UFW status/version and MUST remain read-only. All filesystem/service mutation is isolated in `apply.py`; no Hub collector, hourly sync or remote policy callback may import/call the mutator.
- Manual Apply must preserve unrelated UFW lines, stage/validate deterministic candidates, back up every touched file, arm an independent time-limited rollback before live activation, run UFW dry-run validation, apply atomically, require live management acknowledgement and verify candidate hashes before committing local apply state. Dry-run activation of an inactive UFW must use `--force` so the preflight itself never waits for UFW interactive confirmation.
- UFW IPv4 and IPv6 chain namespaces are different: `before.rules` uses `ufw-before-*`, while `before6.rules` uses `ufw6-before-*`. Compile family-neutral IPv6 rules to the latter. Preflight must validate the **exact full candidate files** through `iptables-restore --test` / `ip6tables-restore --test`, never a synthetic subset with invented chain declarations.
- An active `NO_CHANGE` is zero-write/zero-reload. A failed/rejected/unacknowledged Apply restores both touched files and the previous UFW active/inactive state. Do not weaken this for convenience.
- Automatic Hub/hourly Apply remains forbidden in 0.5.0. `reconcile.py` stays a decision-only layer until a separately reviewed opt-in unattended contract is implemented.
- Original manual `ufw_opevpn_update_form_cfg_json.py` behavior was intentional
  (regenerates timestamp, backups and reloads on every manual invocation).
  It is deprecated but remains operational during migration.
- Preserve deployed legacy BOF/EOF ownership and order. Multiple uniquely identified OpenVPN BAN/forward-isolation blocks are allowed and all must precede the single ZLKL Hard Source Allow block; the SysApps Standard Firewall block follows it. Duplicate identities/blocks, nested/unmatched markers or reversed ordering MUST fail closed. A VPN preview/apply must use that server's configured interface, not silently fall back to `tun+`.
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
