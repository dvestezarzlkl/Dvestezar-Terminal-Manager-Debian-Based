-- SysApps Hub migration 004: user-owned host UI metadata and reported timer state.
-- WARNING: Apply only after the fleet compatibility rollout; older clients
-- expect exact schema version 003 and will report SCHEMA OUTDATED after 004.
-- statement
ALTER TABLE `{{PREFIX}}hosts`
    ADD COLUMN `name` VARCHAR(255) NULL DEFAULT NULL
        COMMENT 'USER-OWNED: optional UI label; NULL means display FQDN/hostname. Never synchronized or overwritten by a host collector.' AFTER `service_host`,
    ADD COLUMN `description` TEXT NULL
        COMMENT 'USER-OWNED: Markdown description edited centrally in future UI. Never synchronized or overwritten by a host collector.' AFTER `name`,
    ADD COLUMN `auto_sync_enabled` TINYINT(1) NULL DEFAULT NULL
        COMMENT 'HOST-REPORTED: whether jb-sysapps-hub.timer is systemd-enabled (1=yes, 0=no, NULL=unknown/not yet reported); not a health check.' AFTER `jblibs_version`
