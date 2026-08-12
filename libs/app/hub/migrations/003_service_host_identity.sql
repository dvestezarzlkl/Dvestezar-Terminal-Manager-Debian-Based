-- SysApps Hub migration 003: separate service host identity
-- statement
ALTER TABLE `{{PREFIX}}hosts`
    ADD COLUMN `service_host` VARCHAR(255) NOT NULL DEFAULT '' AFTER `fqdn`,
    ADD KEY `idx_hosts_service_host` (`service_host`)
