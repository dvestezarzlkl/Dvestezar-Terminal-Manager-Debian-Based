-- SysApps Hub migration 006: firewall desired-rule catalog.
-- Local Firewall Manager sync writes ONLY origin=host_local,target_kind=host
-- rows for the current host. It must never modify central/group/all rules.
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}firewall_rules` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `rule_uid` CHAR(32) NOT NULL
        COMMENT 'Stable UUID-like hex ID. Local editor owns host_local IDs; central UI owns central IDs.',
    `origin` VARCHAR(16) NOT NULL
        COMMENT 'Ownership: host_local for rules edited on the target host; central reserved for future Hub UI rules.',
    `target_kind` VARCHAR(16) NOT NULL
        COMMENT 'Scope: host/group/all. Local editor is restricted to host.',
    `host_id` BIGINT UNSIGNED NULL,
    `group_id` INT UNSIGNED NULL,
    `rule_type` VARCHAR(32) NOT NULL,
    `enabled` TINYINT(1) NOT NULL DEFAULT 1,
    `name` VARCHAR(255) NOT NULL DEFAULT '',
    `direction` VARCHAR(16) NOT NULL DEFAULT 'input',
    `action` VARCHAR(16) NOT NULL DEFAULT 'allow',
    `protocol` VARCHAR(16) NOT NULL DEFAULT 'any',
    `source` VARCHAR(128) NOT NULL DEFAULT '',
    `destination` VARCHAR(128) NOT NULL DEFAULT '',
    `destination_invert` TINYINT(1) NOT NULL DEFAULT 0,
    `port_from` SMALLINT UNSIGNED NULL,
    `port_to` SMALLINT UNSIGNED NULL,
    `interface_name` VARCHAR(32) NOT NULL DEFAULT '',
    `ban_to` DATE NULL,
    `last_seen_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_firewall_rules_uid` (`rule_uid`),
    KEY `idx_firewall_rules_host` (`host_id`, `origin`),
    KEY `idx_firewall_rules_group` (`group_id`, `origin`),
    KEY `idx_firewall_rules_target` (`target_kind`, `origin`),
    CONSTRAINT `fk_firewall_rules_host`
        FOREIGN KEY (`host_id`) REFERENCES `{{PREFIX}}hosts` (`id`)
        ON DELETE CASCADE,
    CONSTRAINT `fk_firewall_rules_group`
        FOREIGN KEY (`group_id`) REFERENCES `{{PREFIX}}host_groups` (`id`)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
