# Changelog

## v1.9.7

- FIX SFTP Apply před reloadem Samby odmountuje všechny spravované loopback CIFS mounty, aby `systemd-fstab-generator` nečekal na stale CIFS reconnect
- UPD změny Samba mountpointů se dokončí v jedné transakci: reload Samba konfigurace, jeden `daemon-reload` a remount výsledného stavu z `/etc/fstab`
- UPD SFTP Manager menu na verzi 1.2.1 a JBLibs submodul na 1.2.12
- ADD setup nyní kontroluje a instaluje systémovou závislost `cifs-utils` pro Samba-backed SFTP mountpointy
- ADD SFTP menu zobrazuje červené upozornění, pokud není dostupný `mount.cifs`
- UPD všechny uživatelské texty SFTP menu byly přesunuty do relativních jazykových souborů `lng/default.py` a `lng/cs-CZ.py`
- UPD validační chyby, výsledky operací a exportní e-mail SFTP helperu používají samostatný katalog `helper_lng/lng`
- FIX odinstalování všech SFTP uživatelů již nepohltí výjimku ani neohlásí falešný úspěch
- FIX SFTP Apply zastaví systémové změny při chybějícím CIFS a ověřuje počet zpracovaných uživatelů i úklid nechtěných uživatelů
- UPD SFTP Manager menu na verzi 1.2.0 a JBLibs submodul na 1.2.11
- FIX SFTP Manager při prvním Apply vytvoří chybějící konfigurační soubor a chybu zápisu vrátí menu místo neošetřené výjimky
- ADD UART loopback diagnostika přímo v UART menu pro rychlosti 9600 až 2 000 000 Bd
- ADD testovací osmibajtové rámce s indexem pokusu a Modbus CRC16
- ADD statistiky TX/RX, timeoutů, CRC chyb, rozdílů dat a cizích bajtů pro každou rychlost
- ADD plný verbose log každého rámce do časově označeného souboru v globálním `LOG_DIR`
- UPD živý průběh testu se v terminálu přepisuje na jednom řádku, po rychlosti zůstane pouze souhrn
- FIX poslední odeslaný rámec dostane celý timeout na odpověď a nevzniká falešný timeout na konci časového okna
- UPD hlavní verze aplikace na 1.9.7

## v1.9.6

- ADD central SMTP mailing config in main app menu, persisted to `config.ini`
- ADD global mailing helper with SMTP login and application-wide fallback admin mail
- UPD SFTP manager mail send now uses the shared SMTP helper and global fallback admin mail
- UPD SMTP mode selection now offers a port swap confirmation and port hints in the mailing menu
- FIX SMTP mail errors now mention suspicious IMAP-like replies and mismatched transport ports
- UPD SFTP key export mails now include the username in the subject and a SysApp version footer
- UPD SFTP key export mails now send multipart text+HTML with key material wrapped in `<pre>`
- UPD mailing submenu now uses ESC for back navigation and adds `SERVER_URL` editing without port
- UPD main settings submenu split into `App settings` and `Mail settings` sections with title separators
- UPD app settings header now uses `c_menu_block_items.append(("label", "value"))` rows like `appHelper`
- UPD app version sync for `readme.md` and `libs/app/cfg.py`
- FIX app config persistence moved out of `libs/app/cfg.py` into shared helper, keeping cfg module schema-only
- ADD `cfg.save()` wrapper for the shared `/etc/jb_sys_apps/config.ini` runtime config, extending the formerly read-only app config

## v1.9.5

- ADD SFTP manager admin mail a per-user mail adresy uložené v JSON konfiguraci
- ADD u certifikátů možnost zobrazit veřejnou část a odeslat key pár mailem na admina a volitelně i na user mail
- UPD key actions ve SFTP manageru přesunuty do vlastního `c_menu` submenu, aby se po zobrazení klíče vracelo zpět jen na nabídku daného klíče

## v1.9.4

- FIX - opraveno SSH restart po updatu změn, pak i s novám userem něbo změnou certifikátu se nešlo přihlásit

## v1.9.3

- ADD - nové UART menu pro tester s uložením konfigurace, výběrem portu, režimu a parametrů komunikace
- ADD - testovací UART příkaz z menu ve tvaru `test{len}n{repeat}` včetně nastavení a uložení výchozích hodnot
- FIX - filtrování seznamu UART portů přes sysfs, aby se nabízely jen relevantní porty
- FIX - překlady UART menu a typů detekovaných UART portů
- UPD - `uart_tester` přesunut na knihovní variantu v `libs/JBLibs`
- UPD - doplněny závislosti v `requirements.txt`

## v1.9.2

- FIX sftpmanager - menu klíče, už se nezobrazuje DEL

## v1.9.1

- FIX synchronize userů sftpmanagera s uživateli v systému, při delete se nemazali staří uživatele, apply teď přidá nové, nebo je updatuje a smaže sftp uživatele kteří nejsou v konfigu (byli vymazáni)
- ADD přidáno generování párů klíče v sftpmanagerovi
- FIX bugů kolem přechodu na ETC konfig cesty

## v1.9.0

- ADD - přidán sftpmanager do menu
- ADD - node-red správa nodejs

## v1.8.7

- FIX menu získání verze node.js

## v1.8.6

- UPD update JBLibs
- FIX získání verze node-red, u verzí pod 4 neuměl parametr --version a spouštěl se, tím selhalo načtení menu s chybou
- ADD - přidána instalce node.js z menu, nebo update major veze - povýšení node.js na další major verzi, nebo update na poslední LTS verzi

## v1.8.5

- ADD - reset machine id pro RPi a OPi na připojené partition, pokud je platný a není již resetován

## v1.8.4

- UPD - převedené některých seznamů na tabulky
- FIX - Zobrazení portu
- FIX - vytvoření názvu backup dir
- FIX - setup, instalace jen free modulů
- ADD - ssh manager operace s heslem
- ADD - readme pro SFTP managera
- FIX - sftp manager run under python 3.10
- ADD - keygen script pro ssh managera
- FIX - zobrazené textů v disk manageru + text pro F5
- ADD - UART tester script pro testování komunikace přes UART převodníky (RS-485, RS-232) - viz uart_tester.md

## v1.8.3

- ADD - recovery sftpmanager

## v1.8.2

- FIX - opraveno lsblk pro starší verze

## v1.8.1

- ADD - disk name - uživatelský popis disků podle PTUUID
- UPD - barvy v menu
- FIX - řazení app menu + přejmenování pro správné řazení
- FIX zadávání do inputů - nefungovalo regex

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
