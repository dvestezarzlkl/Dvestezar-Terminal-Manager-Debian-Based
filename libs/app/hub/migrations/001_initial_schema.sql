-- SysApps Hub migration 001: core host and Node-RED inventory
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}schema_migrations` (
    `version` INT UNSIGNED NOT NULL,
    `filename` VARCHAR(255) NOT NULL,
    `checksum_sha256` CHAR(64) NOT NULL,
    `applied_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}hosts` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `machine_id` VARCHAR(64) NOT NULL,
    `hostname` VARCHAR(255) NOT NULL,
    `fqdn` VARCHAR(255) NOT NULL DEFAULT '',
    `operating_system` VARCHAR(255) NOT NULL DEFAULT '',
    `kernel` VARCHAR(255) NOT NULL DEFAULT '',
    `architecture` VARCHAR(64) NOT NULL DEFAULT '',
    `hardware_vendor` VARCHAR(255) NOT NULL DEFAULT '',
    `hardware_model` VARCHAR(255) NOT NULL DEFAULT '',
    `sys_apps_version` VARCHAR(32) NOT NULL DEFAULT '',
    `jblibs_version` VARCHAR(32) NOT NULL DEFAULT '',
    `first_seen_at` DATETIME(6) NOT NULL,
    `last_seen_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_hosts_machine_id` (`machine_id`),
    KEY `idx_hosts_hostname` (`hostname`),
    KEY `idx_hosts_fqdn` (`fqdn`),
    KEY `idx_hosts_last_seen` (`last_seen_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}host_addresses` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `host_id` BIGINT UNSIGNED NOT NULL,
    `interface_name` VARCHAR(128) NOT NULL,
    `family` VARCHAR(8) NOT NULL,
    `address` VARCHAR(128) NOT NULL,
    `netmask` VARCHAR(128) NOT NULL DEFAULT '',
    `prefix_length` SMALLINT UNSIGNED NULL,
    `mac` VARCHAR(64) NOT NULL DEFAULT '',
    `scope` VARCHAR(32) NOT NULL DEFAULT '',
    `last_seen_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_host_address` (`host_id`, `interface_name`, `family`, `address`),
    KEY `idx_host_address_value` (`address`),
    FOREIGN KEY (`host_id`) REFERENCES `{{PREFIX}}hosts` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}host_services` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `host_id` BIGINT UNSIGNED NOT NULL,
    `service_key` VARCHAR(64) NOT NULL,
    `detected` TINYINT(1) NOT NULL DEFAULT 0,
    `port` INT UNSIGNED NULL,
    `url` VARCHAR(512) NOT NULL DEFAULT '',
    `status` VARCHAR(64) NOT NULL DEFAULT '',
    `version` VARCHAR(128) NOT NULL DEFAULT '',
    `last_seen_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_host_service` (`host_id`, `service_key`),
    KEY `idx_host_service_key` (`service_key`),
    FOREIGN KEY (`host_id`) REFERENCES `{{PREFIX}}hosts` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}sync_sources` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `host_id` BIGINT UNSIGNED NOT NULL,
    `source_key` VARCHAR(64) NOT NULL,
    `status` VARCHAR(32) NOT NULL,
    `item_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `error_text` VARCHAR(1024) NOT NULL DEFAULT '',
    `synced_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_sync_source` (`host_id`, `source_key`),
    KEY `idx_sync_source_status` (`status`),
    FOREIGN KEY (`host_id`) REFERENCES `{{PREFIX}}hosts` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}node_red_instances` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `host_id` BIGINT UNSIGNED NOT NULL,
    `system_user` VARCHAR(128) NOT NULL,
    `title` VARCHAR(255) NOT NULL DEFAULT '',
    `service_name` VARCHAR(255) NOT NULL DEFAULT '',
    `port` INT UNSIGNED NOT NULL,
    `url` VARCHAR(512) NOT NULL DEFAULT '',
    `node_red_version` VARCHAR(64) NOT NULL DEFAULT '',
    `node_js_version` VARCHAR(64) NOT NULL DEFAULT '',
    `node_js_global` TINYINT(1) NULL,
    `project_name` VARCHAR(255) NOT NULL DEFAULT '',
    `git_remote` VARCHAR(512) NOT NULL DEFAULT '',
    `service_running` TINYINT(1) NULL,
    `service_enabled` TINYINT(1) NULL,
    `last_seen_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_node_red_instance` (`host_id`, `system_user`),
    KEY `idx_node_red_version` (`node_red_version`),
    KEY `idx_node_js_version` (`node_js_version`),
    FOREIGN KEY (`host_id`) REFERENCES `{{PREFIX}}hosts` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}node_red_editor_users` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `instance_id` BIGINT UNSIGNED NOT NULL,
    `username` VARCHAR(128) NOT NULL,
    `access_level` VARCHAR(8) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_node_red_editor_user` (`instance_id`, `username`),
    KEY `idx_node_red_editor_username` (`username`),
    FOREIGN KEY (`instance_id`) REFERENCES `{{PREFIX}}node_red_instances` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
