# Changelog

## v1.8.0

- ADD - diska  swap manager
- FIX barvy
- ADD Disk a swap manager
- UPD Přechod na ETC pro config cesty

## v1.7.6

- FIX JBLibs init prop pro dědičnost

## v 1.7.5

- FIX - canInstall vyhodnocení

## v 1.7.4

- FIX - menu loading info
- FIX - keyboard timing
- UPD - přes setting json lze ovlivnit title instance i z node-red instance
- UPD - oddělení service manager instance

## v 1.7.3

- ADD - přidáno zobrazení logu journalctl pro instance

## v 1.7.2

- UPD - po updatu app se app ukončí a je potřeba ji znovu spustit

## v 1.7.1

- FIX - opraveno generování sudoers souboru, nejdřív se detekuje cesta k systemctl

## v 1.7.0

- ADD - možnost generovat/updatovat sudoer soubor pro restart node-red instance sama sebe
- ADD - nápověda k sudoer souboru
- ADD - update sebe sama

## v 1.6.7

- FIX - text menu pro safe mode
- UPD - opakování run instance jako app i v safe mode
- UPD - zkrácení zkratky pro safe mode

## v 1.6.6

- UPD - safe mód se po schybě nebo ukončení node-red (CRT+C) zeptá jestli znovu restartovat do safe módu

## v 1.6.5

- FIX - oprvaven spuštění safe mode node instance, protože pi verze špatně interpertuje safe, safe se spouští přímo přes red.js

## v 1.6.4

- ADD - instance run in safe mode - flow stooped

## v 1.6.3

- FIX - opraveno načítání libs pokud je v listu u rovnítka mezera

## v 1.6.2

- FIX - opraveno načítání libs c node-red

## v 1.6.1

- FIX - opraveno načítání konfigurace z config.json - cirkularní reference
- UPD - aktualizace JBLibs na verzi 1.2.8
- UPD - aktualizace možností načítání nastavení a knihoven node-red instancí
- UPD - přidána volba nápovědy pro cfg files v menu

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