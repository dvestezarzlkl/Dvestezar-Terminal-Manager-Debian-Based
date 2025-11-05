# Changelog

## v 1.6.1

- FIX - opraveno načítání konfigurace z config.json - cirkularní reference
- UPD - aktualizace JBLibs na verzi 1.2.8

## v 1.6.0

- UPD/ADD - přidán PHP script pro zobrazení instancí na

## v 1.5.2

- ADD - JBLibs version v main menu

## v 1.5.1

- FIX - getKey přidáno sleep kvůli zbytečnému přetěžování vlákna a vytížení cpu na 100% při čekání na stisk klávesy
- FIX - opreveno nastavení ESC_is_quit v init
- FIX - menuBoss exit - souvisí s ESC_is_quit opravou

## v 1.5.0

- ADD - managing menu (new section for instance and backup control)
- ADD - instance backups - check archive integrity using 7z
- ADD - instance backups - interactive restore with service stop/start
- ADD - restore requires triple confirmation including manual instance name
- ADD - update instance allows forced update over major version

## v 1.4.2

- ADD - one instance
- ADD - backups can be listed and deleted, fullBackup and instance backup
- FIX - readme
- FIX - přidáno cls mezi menu - vstup a exit - pro identifikaci stisku klávesy. Pokud se menu dlouho inicializovalo, vypadalo to jako že nebylo nic stisknuto - zamrznutí.
- ADD - new instance - check if port is free
- Add - do assets adresáře přidáno generování souboru `portsInUse.json`
- ADD - do konfigu přidána možnost kopie `portsInUse.json` do jiného adresáře

## v 1.4.1

- add - node red logs directrory fro instance

## v 1.4.0

- dokončování produkce, běh ve venv
- min verze pythonu 3.10

## v 1.3.4

- ADD - ssh key user management - add, remove dialout group

## v 1.3.3

- ADD - install script
- UPD - info v update script

## v 1.3.2

- ADD - update node-red instance

## v 1.3.1

- first rls