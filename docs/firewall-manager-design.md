# Firewall Manager — UFW / OpenVPN takeover design

Status: **read-only UFW inspection + pure policy comparison implemented** as SysApps 2.6.0 (2026-10-20). No firewall writer, automatic policy application, or migration of new21 is implemented.

## Read-only phase (SysApps 2.6.0)

The built-in dynamic subapplication `libs/app/menus/app_40_firewall/` now has:

- `menu.py` using standard `c_menu`/localization: show UFW state, inspect owned marker blocks in `/etc/ufw/before.rules`, and explicitly preview changes against a user-selected legacy JSON/JS file. No write or apply menu action exists.
- `hub_provider.py` returning one typed `HubService("ufw", detected, status, version)` through the existing `service` dataset in `host_services`. Reads only `ufw status` and `ufw --version`. No collector-owned SQL, no schema migration.
- `policy.py` with exact BOF/EOF block matching, duplicate/unmatched/nested marker refusal, OpenVPN-before-Hard-Source ordering validation, rule-token normalization without variable timestamps or iptables `comment` match, and ordered deterministic SHA-256 of effective actions.
- Pure `compile_legacy_openvpn` honoring permanent/temporary BAN and forward isolation, validating IP/CIDR and client types, treating `banTo` as valid **through** its calendar day. It returns the next expiry transition date, so future hourly checks can invalidate the result even when the JSON itself is unchanged.
- Pure `plan_legacy_openvpn`: `NO_CHANGE` / `CHANGED` / `MISSING` / `REVIEW` with hashes, rule counts, expired BAN count; never writes/reloads anything. A changed BOF identity requires review before any future automated takeover.

The hourly Hub now collects **UFW presence/status**, not yet a centralized desired-policy fetch/reconcile with Apply. `NO_CHANGE` is a read-only decision; future persistent `last_checked_at`/`last_applied_at`, staging, applied hash and transactional rollback will be a separate implementation phase. These existing sections remain untouched until that phase is tested on a VM and explicitly enabled.

## Reconciliation decision foundation (SysApps 2.6.1)

Pure `app_40_firewall/reconcile.py` provides `reconcile(plan, previous, checked_at)`. It accepts the established `FirewallPlan` and previously verified `ReconcileState`; **no local state is saved or mutated**, no UFW command or file write exists in this layer. A known, matching `applied_hash` and `NO_CHANGE` produce `NO_CHANGE`, while a changed effective rule set (including a cooldown BAN expiry) produces `PENDING_REVIEW`. Missing/ambiguous markers return `BLOCKED`, and a changed observed hash against last-verified `applied_hash` returns `DRIFT`. No prior applied hash means explicit manual adoption is mandatory, even when observed state matches desired.

Only `last_checked_at` advances during check; `last_applied_at` and `applied_hash` are unchanged until a **later, separate verified Apply transaction**. This prevents hourly checks from asserting an application or restarting any service. Durable state with anti-rollback, actual UFW apply, verification, audit, rollback and central policy fetch are NOT implemented yet. On VM, first test read-only statuses and plans.

## Existing deployed behavior

Source repository: [ufw_opevpn_update_form_cfg_json](https://github.com/dvestezarzlkl/ufw_opevpn_update_form_cfg_json), default branch `master`, script `ufw_opevpn_update_form_cfg_json.py` v1.0.0.

The existing generator parses a JS file with `// BOF JSON CFG` followed by strict JSON (`server_name`, `server_ip`, `server_mask`, `clients`). Per OpenVPN client, `type` selects unrestricted/no generated rule (0), BAN (1, optional `banTo`), or forward isolation (2). It generates an identified marker block `# *** BOF/EOF OpenVPN JB Config - <server_name> <network>` in `/etc/ufw/before.rules`, creates a timestamped backup and calls `ufw reload`.

On the new21 excerpt (user-confirmed 2026-10-20), there are **two separately managed legacy blocks** near the head of `*filter`:
1. `OpenVPN JB Config`: BAN drops in `ufw-before-forward` and `ufw-before-input` with `-i tun+`; isolation drops in forward chain. This block precedes all source exceptions.
2. `ZLKL Hard Source Allow Config - managed by sys_apps`: unconditional `-A ufw-before-input -s ADDRESS -j ACCEPT` for VPN and selected public IPv4 hosts. These ACCEPT rules permit *all* local INPUT ports from a source, on all interfaces; they precede later ordinary UFW policy.

**Keep the two blocks independent and retain their order.** In particular, BAN for a VPN client must remain earlier than a general VPN allowlist, otherwise banned addresses may be accepted. Do not remove or overwrite other administrators' `before.rules` lines. The hard-source block says it was previously managed by sys_apps, not by the legacy OpenVPN generator; locate its canonical original ownership in source before taking it over.

## Required host group/target semantics

Schema `005_host_groups.sql` introduces `host_groups(id INT UNSIGNED, code, name, description)` and centrally USER-OWNED `hosts.group_id INT UNSIGNED NULL DEFAULT NULL` with FK and `ON DELETE SET NULL`. A host belongs to **zero or one** target groups; new installations/records remain unassigned. Host collectors never overwrite membership. Group `code` is a stable machine/policy selector, UI `name` and Markdown `description` are user owned.

`all hosts` is a third target scope (not a synthetic group), and a particular `host.id` a first scope. Source IP groups (home/office/VPN) are a **different table family** from target host groups. No firewall rules are included in migration 005; design the policy tables in a later dedicated migration after verifying the UFW engine.

Recommended future scopes:
- `target_kind = host`, target_host_id set
- `target_kind = group`, target_group_id set
- `target_kind = all`, both target IDs NULL

A rule needs explicit direction (`input`, `forward`, `output`), IP family, protocol, destination ports/ranges, source IPv4/IPv6 CIDRs or source alias, action, ordering/priority and optional `interface`. Use an explicit `trusted_source_bypass` action to preserve new21's all-local-ports ACCEPT semantics, never silently conflate that with ordinary `allow ssh`.

## Intentional manual behavior versus unattended successor

The legacy v1.0.0 generator intentionally **regenerates the block (including its
generation timestamp), backs up the file and reloads UFW on every invocation**.
It was designed for an operator-triggered manual update; this behavior is
**not a bug to repair in the legacy repository**.

The successor SysApps Firewall Manager has a different contract: the hourly Hub
timer checks desired state, expiry of time-limited BAN rules and observed state.
It computes a normalized effective rule set **excluding timestamps and other
volatile annotations**. Only a real change to that effective rule set may
trigger a new generated timestamp, file write, backup and UFW reload. Unchanged
rules must result in `NO_CHANGE`, with zero file writes and zero service reloads.
Track last-check time separately from last-successful-apply time. A time-limited
BAN can expire with unchanged source JSON and must still produce a real
effective-rule change.

The old GitHub repository is marked **DEPRECATED** in
[PR #1](https://github.com/dvestezarzlkl/ufw_opevpn_update_form_cfg_json/pull/1),
but must remain functional until SysApps has safely taken over UFW configuration,
including the OpenVPN and Hard Source Allow blocks, and the old invocation paths
are disabled. Only then should it be archived.

## Migration considerations for original v1.0.0

Review the following as constraints for the *new unattended implementation*, not
requests to change the legacy manual script. Do **not** run the old generator and
the new manager against the same managed block concurrently.

- `reloadUfw` uses `os.system("ufw reload")` and prints success without checking the return code.
- `modifyUfwRules` writes `before.rules` directly (not staged + fsync + atomic replace + validation + rollback); backup alone does not prevent loss of remote access.
- Block identity embeds server name/IP/mask and network assembled by replacing the last IPv4 octet with zero. This is wrong in general for `/23` (use `ipaddress.ip_network(..., strict=False)`). A changed identity can cause the old block to remain and a second block to be inserted.
- `injectBlock` appends a block to the end if `# End required lines` is missing. This may place rules *after* the `COMMIT` of the iptables-restore table, which is not valid placement.
- Duplicate/invalid IP and unknown client type are silently ignored or merely commented. Missing mandatory fields throw errors; user-controlled names/comments appear in `--comment "..."` without a constrained serialization policy.
- `banTo` uses `datetime.strptime(...,"%Y-%m-%d") >= datetime.now()`; it expires at the **start** rather than the end of the specified date. A past-date BAN remains **loaded in UFW** until rules are regenerated and UFW is reloaded. Example from new21: banTo 2026-01-01 appears as an active DROP in the supplied older-generated rules as of 2026-10-20.
- The script has no read-only inspection/diff mode, does not verify ownership of all existing markers and does not guard overlapping edits.

## Proposed replacement owner

- One discoverable built-in `libs/app/menus/app_*_firewall` subapplication for UFW status, rule preview and explicit protected Apply; a generic UFW block parser/validator if reusable belongs in JBLibs-python, **not** duplicated inside Hub.
- `hub_provider.py` in the firewall app is the read-only inventory/health interface. It reports actual loaded/configured state but never modifies UFW.
- SysApps Hub is a **scoped desired-state source**, not a remote SQL execution engine. The host must not get permission to modify others' desired firewall rules. Validate signed/versioned per-host policies, and keep rollback state only on the local host.
- Local dynamic policy: global baseline `all`, one optional target group, and per-host override. Define deterministic ordering; deny precedence and exception priorities must be explicitly tested. Source groups (work/home/VPN) are separate aliases; expire/rotate addresses with history rather than rewriting every rule.
- Migration tooling must detect the legacy BOF/EOF pairs (unique and ordered), generate a preview of exactly owned lines (no manual lines touched), and operate **one time** in a confirmed import/adopt operation. Disable the old job/script only after successful read-back.
- Evaluate UFW implementation and v4/v6 chains on each host. Preserve `*filter`, base chains, other rules and `COMMIT`. Never assume adding a new trusted source is permission to bypass all destination port restrictions.
- For Apply: stage candidates and a complete local backup; validate iptables-restore syntax and UFW backend; verify both v4/v6 where applicable; stage an automatic time-bound local rollback *before* reload; preserve a tested rescue SSH/VPN access route; verify a new authenticated session; confirm before committing. Fail closed and retain original on any problem.
- Observe UFW also controls Ubuntu forwarding/routing; `ufw-before-forward` isolation of a VPN client is distinct from `ufw-before-input` rules for the host.
- No automatic policy auto-apply, `ufw reload` or remote change on new21 until VM tests and explicit approval.

## Deployment order

1. Ship optional schema 005 host groups in SysApps 2.5.0 code. A v2.5.0 client accepts existing v004 as ready; old v2.4.0 clients will **not** accept upgraded v005. Update the fleet before invoking the manual schema migration.
2. After all Hub-enabled clients run 2.5.0, take DB backup, run menu **Initialize/update Hub schema** once; all existing `hosts.group_id` values remain NULL. Check lookup/edit and repeated core sync.
3. Implement read-only UFW collector and a diff parser against real backup copies of new21 (not production writes).
4. Build desired-state rules/addresses schema and scoped policy compiler. Test precedence for BAN, global hard source allow, group/host policy and ordinary UFW.
5. VM adopt/import of both marker blocks, test rollback and repeated idempotent Apply, then gradual opt-in fleet migration. Only after verified takeover disable legacy script/cron.

This design intentionally avoids replacing the existing working new21 rules with unverified code.
