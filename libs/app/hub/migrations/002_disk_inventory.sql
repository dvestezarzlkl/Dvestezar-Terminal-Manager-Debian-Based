-- SysApps Hub migration 002: global disk registry and host attachments
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}disks` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `ptuuid` VARCHAR(128) NOT NULL,
    `display_name` VARCHAR(64) NOT NULL DEFAULT '',
    `name_updated_at` DATETIME(6) NULL,
    `size_bytes` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `first_seen_at` DATETIME(6) NOT NULL,
    `last_seen_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_disks_ptuuid` (`ptuuid`),
    KEY `idx_disks_display_name` (`display_name`),
    KEY `idx_disks_last_seen` (`last_seen_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
-- statement
CREATE TABLE IF NOT EXISTS `{{PREFIX}}host_disks` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `host_id` BIGINT UNSIGNED NOT NULL,
    `disk_id` BIGINT UNSIGNED NOT NULL,
    `device_name` VARCHAR(128) NOT NULL,
    `device_path` VARCHAR(255) NOT NULL DEFAULT '',
    `size_bytes` BIGINT UNSIGNED NOT NULL DEFAULT 0,
    `device_type` VARCHAR(32) NOT NULL DEFAULT 'disk',
    `partition_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `mountpoint_count` INT UNSIGNED NOT NULL DEFAULT 0,
    `is_system_disk` TINYINT(1) NOT NULL DEFAULT 0,
    `last_seen_at` DATETIME(6) NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_host_disk` (`disk_id`),
    UNIQUE KEY `uq_host_disk_device` (`host_id`, `device_name`),
    KEY `idx_host_disks_last_seen` (`last_seen_at`),
    FOREIGN KEY (`host_id`) REFERENCES `{{PREFIX}}hosts` (`id`) ON DELETE CASCADE,
    FOREIGN KEY (`disk_id`) REFERENCES `{{PREFIX}}disks` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
