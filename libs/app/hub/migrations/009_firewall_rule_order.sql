-- SysApps Hub migration 009: deterministic ordering for central firewall rules.
-- Local host collectors remain owner of origin=host_local,target_kind=host rows.
-- Central policy delivery uses this position only for origin=central rows.
-- statement
ALTER TABLE `{{PREFIX}}firewall_rules`
    ADD COLUMN `position` INT UNSIGNED NOT NULL DEFAULT 0 AFTER `target_kind`,
    ADD KEY `idx_firewall_rules_scope_order`
        (`origin`, `target_kind`, `position`, `id`)
