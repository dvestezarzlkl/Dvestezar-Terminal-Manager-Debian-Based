-- statement
ALTER TABLE `{{PREFIX}}firewall_rules`
    ADD COLUMN `src_ports` VARCHAR(1024) NOT NULL DEFAULT '' AFTER `port_to`,
    ADD COLUMN `dst_ports` VARCHAR(1024) NOT NULL DEFAULT '' AFTER `src_ports`
