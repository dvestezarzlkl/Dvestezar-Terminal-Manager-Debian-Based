-- SysApps Hub migration 005: centrally user-owned single group per host.
-- No host collector may set or overwrite hosts.group_id.
-- Rollout: 2.5.0 clients can sync with schema 004 before migration.
-- Older 2.4.0 clients cannot sync after upgrading the shared schema to 005.
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}host_groups` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT,
    `code` VARCHAR(64) NOT NULL
        COMMENT 'USER-OWNED: immutable logical group key for future policy targeting, e.g. production or test.',
    `name` VARCHAR(255) NOT NULL
        COMMENT 'USER-OWNED: group display label for the central UI.',
    `description` TEXT NULL
        COMMENT 'USER-OWNED: Markdown description for the central UI.',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_host_groups_code` (`code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
-- statement
ALTER TABLE `{{PREFIX}}hosts`
    ADD COLUMN `group_id` INT UNSIGNED NULL DEFAULT NULL
        COMMENT 'USER-OWNED: optional central host group; NULL means unassigned, including all newly collected hosts. Never overwritten by host inventory sync.' AFTER `description`,
    ADD KEY `idx_hosts_group_id` (`group_id`),
    ADD FOREIGN KEY (`group_id`) REFERENCES `{{PREFIX}}host_groups` (`id`)
        ON DELETE SET NULL
