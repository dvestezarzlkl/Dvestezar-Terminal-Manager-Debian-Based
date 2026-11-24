-- SysApps Hub migration 010: central firewall desired/delivered/applied host state.
-- Web/UI owns desired-state only. Remote Apply/reload is intentionally absent.
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}firewall_policy_meta` (
    `id` TINYINT UNSIGNED NOT NULL,
    `revision` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `updated_at` DATETIME(6) NOT NULL,
    `updated_by` VARCHAR(128) NOT NULL DEFAULT '',
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
-- statement
INSERT IGNORE INTO `{{PREFIX}}firewall_policy_meta`
    (`id`, `revision`, `updated_at`, `updated_by`)
VALUES
    (1, 0, UTC_TIMESTAMP(6), 'schema-bootstrap')
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}firewall_policy_host_state` (
    `host_id` BIGINT UNSIGNED NOT NULL,
    `desired_hash` CHAR(64) NOT NULL DEFAULT '',
    `desired_revision` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `desired_at` DATETIME(6) NULL,
    `delivered_hash` CHAR(64) NOT NULL DEFAULT '',
    `delivered_revision` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `delivered_at` DATETIME(6) NULL,
    `applied_hash` CHAR(64) NOT NULL DEFAULT '',
    `applied_revision` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `applied_at` DATETIME(6) NULL,
    `apply_status` VARCHAR(16) NOT NULL DEFAULT 'unknown',
    `apply_error` VARCHAR(512) NOT NULL DEFAULT '',
    `reported_at` DATETIME(6) NULL,
    PRIMARY KEY (`host_id`),
    KEY `idx_firewall_policy_desired` (`desired_revision`, `desired_hash`),
    KEY `idx_firewall_policy_applied` (`applied_revision`, `applied_hash`),
    CONSTRAINT `fk_firewall_policy_state_host`
        FOREIGN KEY (`host_id`) REFERENCES `{{PREFIX}}hosts` (`id`)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
