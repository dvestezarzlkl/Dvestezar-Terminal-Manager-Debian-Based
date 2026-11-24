# Central Firewall Policy UI Contract

Status: design contract for Redmine #3675. The web/UI implementation may evolve, but it must preserve the safety and state semantics below.

## Non-negotiable safety boundary

The central web/UI owns **desired-state only**.

It must never expose or call any remote action that:

- runs UFW Apply/reload/enable/disable,
- confirms the fresh-SSH acknowledgement token,
- bypasses the local rollback guard,
- marks a policy as applied without a successful local SysApps manual Apply.

The only supported activation path is an explicit action in SysApps on the target host. That action must reuse the existing guarded Firewall Manager Apply transaction, including preview, backup, pre-armed rollback, UFW dry-run and cross-session acknowledgement when required.

## Per-host state machine

Policy equality is determined by a deterministic SHA-256 of the **effective central policy for one host**. Revision is audit/display metadata only.

The central UI distinguishes:

1. **waiting_for_delivery**
   - desired_hash != delivered_hash
   - Central desired-state changed, but the target host has not yet acknowledged successful local caching.

2. **waiting_for_apply**
   - desired_hash == delivered_hash
   - desired_hash != applied_hash
   - The host has the policy cached and must be changed only by a local manual SysApps Apply.

3. **applied**
   - desired_hash == applied_hash
   - The last successfully activated central policy equals the current desired policy.

4. **apply_failed / rolled_back**
   - The latest manual Apply failed or rolled back.
   - applied_hash must remain the last successfully applied value.

The UI should show transport/provider health separately from the desired/delivered/applied state. A host can be offline while still having a known last applied policy.

## Schema 010 host state

The Hub schema exposes one row per host in firewall_policy_host_state:

- desired_hash
- desired_revision
- desired_at
- delivered_hash
- delivered_revision
- delivered_at
- applied_hash
- applied_revision
- applied_at
- apply_status
- apply_error
- reported_at

firewall_policy_meta stores the central writer revision and last writer identity for UI/audit display.

A missing/empty central policy on a host with no previous central state is a clean baseline, not a pending firewall change.

## Delivery acknowledgement

Returning a policy from the Hub database is **not** enough to call it delivered.

The Hub runtime marks delivered_hash only after the target provider has successfully validated and atomically cached the remote policy. If local cache application fails, desired remains pending delivery.

The next normal provider report also carries cached/applied state so Hub state can recover after temporary DB/network failures.

## Manual Apply result

After a successful local manual Apply:

- SysApps persists applied_hash and applied_revision locally,
- reports the state back through the normal Hub provider,
- Hub updates the per-host row,
- web UI changes from waiting to applied.

NO_CHANGE is a successful Apply outcome when the currently live managed UFW state already equals the confirmed effective desired state.

On exception or rollback, SysApps may report status/error but must not advance applied_hash.

## Central writer permissions

Future web/API code must call the typed central writer contract, not write firewall tables directly.

ACL capabilities are fixed by the backend contract:

- `firewall.policy.read`
- `firewall.policy.write`

Write permission also permits the typed read snapshot. There is intentionally **no** `firewall.policy.apply` remote permission.

The web/API authentication layer must construct `HubFirewallPolicyActor` from the authenticated identity and granted ACL; callers must never supply arbitrary permissions themselves. Every mutation requires the current `expected_revision`; a stale revision fails with a conflict instead of silently overwriting another editor.

The writer validates ownership (`origin=central`), target (`host/group/all`), host/group existence, stable IDs, position, VPN references and canonical Firewall Manager field normalization before commit.

`HubFirewallPolicyAdmin.get_snapshot()` is the supported editor read model. It returns policy revision/update identity, typed central rule/VPN records with resolved host/group/all targets, and per-host desired/delivered/applied states. Future web UI must use this typed service rather than querying firewall tables directly.

## Host groups and future group editor

A `group` firewall target can reference only an already existing centrally owned `host_groups.code`. Group catalog and host membership are a separate user-owned Hub domain; this firewall writer intentionally does not create groups or reassign hosts.

When a future host/group metadata editor changes membership, it must invoke the same central-policy recomputation service for the affected host(s) so the desired hash changes immediately in the web UI rather than waiting for a later host sync. Do not implement group membership by editing `firewall_policy_host_state` directly.

## UI data useful for listing hosts

For each host the UI should be able to show:

- hostname/FQDN/user name/group,
- current central desired revision/hash,
- last delivered revision/hash/time,
- last applied revision/hash/time,
- derived state: waiting for delivery / waiting for Apply / applied / failed,
- latest apply error,
- latest Hub/provider sync state,
- counts of applicable central rules/VPN servers when useful.

Never infer applied state from the presence of rules in the database or from a successful Hub sync alone.
