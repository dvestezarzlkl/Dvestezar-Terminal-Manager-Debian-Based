-- SysApps Hub migration 008: VPN server catalog and rule association.
-- Local collectors own only origin=host_local,target_kind=host rows.
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}firewall_vpn_servers` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `server_uid` CHAR(32) NOT NULL,
    `origin` VARCHAR(16) NOT NULL,
    `target_kind` VARCHAR(16) NOT NULL,
    `host_id` BIGINT UNSIGNED NULL,
    `group_id` INT UNSIGNED NULL,
    `name` VARCHAR(128) NOT NULL,
    `server_ip` VARCHAR(45) NOT NULL,
    `server_mask` TINYINT UNSIGNED NOT NULL,
    `interface_name` VARCHAR(32) NOT NULL DEFAULT 'tun+',
    `last_seen_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_firewall_vpn_server_uid` (`server_uid`),
    KEY `idx_firewall_vpn_servers_host` (`host_id`, `origin`),
    KEY `idx_firewall_vpn_servers_group` (`group_id`, `origin`),
    CONSTRAINT `fk_firewall_vpn_servers_host`
        FOREIGN KEY (`host_id`) REFERENCES `{{PREFIX}}hosts` (`id`)
        ON DELETE CASCADE,
    CONSTRAINT `fk_firewall_vpn_servers_group`
        FOREIGN KEY (`group_id`) REFERENCES `{{PREFIX}}host_groups` (`id`)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
-- statement
ALTER TABLE `{{PREFIX}}firewall_rules`
    ADD COLUMN `vpn_server_uid` CHAR(32) NULL AFTER `rule_type`,
    ADD KEY `idx_firewall_rules_vpn_server` (`vpn_server_uid`);
