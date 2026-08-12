# Changelog

## v2.2.4

- PERF startup už neobsahuje historický pevný 2s splash delay; po základním bootstrapu pokračuje rovnou inicializací menu.
- UX automatická SysApps Hub synchronizace při startu zobrazuje dynamický postup `x/y` přes základní inventář, každý registrovaný provider a finalizaci; detailní DB/collector časování zůstává v logu.
- UX Swap Manager 2.5.2 rozšiřuje sloupec `Type` na 10 znaků, aby se hodnota `partition` zobrazila bez rozhození tabulky.
- UPD hlavní verze aplikace na 2.2.4.

## v2.2.3

- DIAG startup nyní časuje celý bootstrap: načtení cfg, logger/jazyk/terminal a `menuBoss` import, runtime preflight, explicitní 2s splash delay, discovery a import každého `app_*`, update-check, central settings, Hub a předání do hlavního menu; z jednoho logu je tak vidět přesná fáze případného čekání.
- UX hlavní menu při startu best-effort porovná lokální core HEAD s `origin/main` přes read-only `git ls-remote` a u `Update me` zobrazí `up to date`, `update available` nebo `check unavailable`; kontrola nespouští pull/fetch, submoduly, pluginy ani setup.
- SAFE kontrola používá stávající Git credentials, `GIT_TERMINAL_PROMPT=0`, 3s timeout a 5min cache v lokálním `.git`; síťová chyba nebo vadné credentials pouze nastaví stav `check unavailable` a neblokují spuštění aplikace. Změna lokálního HEAD cache automaticky zneplatní.
- UPD hlavní verze aplikace na 2.2.3.

## v2.2.2

- DIAG Startup diagnostics log timed INFO milestones for SysApps Hub DB/core/provider synchronization and centralized settings download/decode/policy/apply phases; mandatory JBLibs 1.2.29 additionally flushes each rendered `c_menu` ANSI frame before blocking for keyboard input, so rare startup stalls can be separated from stale terminal redraws without exposing credentials or package contents.
- UX SFTP Manager 1.2.14 + JBLibs 1.2.28 propagují konkrétní Samba/CIFS batch chybu do menu; neprázdný underlying managed target se zobrazí s přesnou cestou a doporučením bezpečného `u` -> `a` rebuildu místo obecného selhání Apply.
- SAFE SFTP Manager 1.2.13 + JBLibs 1.2.27 před destruktivním odstraněním SFTP uživatele po odpojení mountpointů archivují celý lokální home do `BACKUP_DIRECTORY/sftpusers/<user>/...`; prázdné odpojené target adresáře se před backupem odstraní a zachovají se pouze neprázdné targety s underlying daty. Hlavní menu zobrazuje počet a celkovou velikost záloh bez další správy/restore UI.
- FIX SFTP Manager 1.2.12 + JBLibs 1.2.25 fyzicky obnovují RO/RW změnu aktivního Samba-backed mountpointu cíleným uzavřením pouze dotčeného managed share po reloadu konfigurace; při selhání je fallback plný restart `smbd`. JBLibs 1.2.25 navíc ověřuje zbylé bind/CIFS mounty přes `/proc/self/mountinfo` před destruktivním cleanupem jailu.
- SAFE SFTP Manager 1.2.12 odmítne remount přes neprázdný underlying CIFS target a opravuje potvrzený uninstall-all cleanup neprázdného jailu po kontrole zbylých mountů.
- FIX SFTP Manager 1.2.11 integruje JBLibs 1.2.23 s opravenou Samba/CIFS batch transakcí; změny RO/RW a reálné cesty stejného mountpointu se dokončují v jednom Apply bez předčasného unmount/cleanup mezistavu.
- TEST JBLibs 1.2.23 ověřuje pořadí finalizace, zachování cíle odstraněného a znovu vytvořeného v jedné dávce a správnou identitu Samba share.
- FIX SFTP Manager 1.2.10 opravuje cancel ve výběru mountpointu, nepersistuje neúspěšný Apply před fyzickou synchronizací a zobrazuje konkrétní příčinu selhání reconcile.
- UPD SFTP Manager 1.2.10 vyžaduje JBLibs 1.2.22 s in-memory desired-state synchronizací.
- FIX SFTP Manager 1.2.9 po úspěšném Apply znovu načítá uloženou konfiguraci, aby opakované změny mountpointu nebo RO/RW ve stejném běhu nepoužívaly stale in-memory stav.
- FIX JBLibs 1.2.21 opravuje `c_menu` veto výstupu pro ESC a `endMenu`; odpověď N na zahození neuložených SFTP změn tak skutečně ponechá menu otevřené.
- FIX SFTP Manager 1.2.8 při změně cesty existujícího mountpointu otevírá adresářový výběr na aktuální reálné cestě; na `/` padá pouze tehdy, když uložená cesta už není platný adresář.
- SAFE SFTP Manager 1.2.8 při pokusu opustit hlavní menu s neuloženými změnami vyžaduje potvrzení jejich zahození; odmítnutí ponechá menu i změny otevřené.
- FIX SFTP Manager 1.2.7 při Apply synchronizuje také samotnou změnu RO/RW u Samba-backed mountpointu bez nutnosti měnit cestu nebo point ručně mazat; JBLibs aktualizováno na 1.2.20.
- FIX SFTP Manager 1.2.6 správně respektuje volbu pouze pro čtení při vytvoření mountpointu; výsledek `select()` se vyhodnocuje přes zvolená data místo porovnání wrapper objektu.
- UX SFTP Manager 1.2.6 umožňuje u existujícího mountpointu změnit reálnou cestu při zachování aliasu a RO/RW nastavení; následný Apply využije stávající detekci změny cesty a znovu synchronizuje Samba/CIFS/jail konfiguraci.
- UX všechny podnabídky `c_menu` v SysApps trvale zobrazují identitu aktuálního hostu/FQDN, takže je stroj viditelný i hluboko v Disk, Swap, SSH, SFTP a dalších manažerech.
- UPD JBLibs na 1.2.19 s obecným persistentním `c_menu.globalTitle`; jednotlivé menu mohou globální kontext vypnout přes `showGlobalTitle=False`.
- UX hlavní HOME globální řádek skrývá, protože FQDN už zobrazuje ve vlastním systémovém souhrnu.
- UPD hlavní verze aplikace na 2.2.2.

## v2.2.1

- FIX Disk Manager 3.6.8 opravuje Ubuntu Server/U-Boot one-shot PTUUID: PARTUUID v initramfs ověřuje přes `lsblk` a finalizační unit před armingem validuje přes `systemd-analyze verify`.
- ADD Disk Manager 3.6.7 podporuje dvojitě potvrzenou one-shot změnu PTUUID živého systémového GPT disku v initramfs, s GPT backupem a kontrolou PARTUUID po bootu.
- UX Disk Manager 3.6.6 zobrazuje PTUUID přímo v detailu disku pro rychlou identifikaci klonů.
- FIX Disk Manager 3.6.5 odděluje skutečná úložiště a loop image od zram, MTD a interních eMMC boot/RPMB zařízení.
- FIX Swap Manager 2.5.1 zobrazuje všechny aktivní swapy z `swapon --show`; pouze souborové swapy mají editační submenu, zram a swap partition jsou informativní.
- FIX Disk Manager 3.6.4 zahrnuje živý systémový disk do Hub inventáře a synchronizuje jej s `is_system_disk=1`; provozní blokace zapisujících operací zůstávají beze změny.
- SAFE Disk Manager 3.6.3 zpřístupňuje systémový disk pouze pro přehled a přejmenování; záloha, obnova a změna PTUUID živého systémového disku jsou blokované.
- FIX seznam disků a partition zobrazuje skutečné mountpointy a zachovává zarovnání i u barevných uživatelských názvů.
- UPD JBLibs na 1.2.18 s rekurzivní detekcí systémového disku.
- UX Disk Manager 3.6.2 přejmenovává zavádějící reset Machine ID na přípravu identity pro první boot a dokumentuje záměrné zachování first-boot stavu
- FIX Disk Hub synchronizuje také pojmenované PTUUID z lokálního katalogu Disk Manageru, i když fyzický disk právě není připojený
- FIX globální záznam disku je oddělený od aktuální host-device vazby; katalogový sync nevytváří falešný device a nepřepisuje známou velikost ani poslední fyzické nalezení
- UPD Disk Manager na 3.6.2 a hlavní aplikace na 2.2.1

## v2.2.0

- ADD lokální dynamická politika centrálního importu umožňuje pro každou registrovanou sekci nastavit `Skip`; nové budoucí sekce se v menu zobrazí automaticky
- ADD SMTP podporuje jemnou lokální výjimku `Skip SMTP From address`, která importuje transportní nastavení, ale zachová odesílatele konkrétního serveru
- SAFE `SETTINGS_IMPORT_POLICY` je pouze lokální bootstrap a nikdy není součástí `SYSAPP1E`; podpis aplikovaných sekcí zahrnuje přeskočené sekce i zachovaná pole, takže změna politiky znovu vyhodnotí stejnou revision
- UX potvrzení importu vypisuje konkrétní zbývající sekce a po potvrzení ihned zobrazí `Processing centralized settings import...`, aby pomalejší ARM server nepůsobil zamrzle
- UPD hlavní verze aplikace na 2.2.0

## v2.1.2

- FIX SysApps Hub se nesynchronizuje bez platného lokálního service host/FQDN; prázdná hodnota i historický placeholder `moje.domena.fake` vrátí stav NOT CONFIGURED a běžná lokální práce zůstane dostupná
- SAFE ruční import vyžaduje potvrzení před změnou již nastaveného SMTP hostu nebo From adresy; odmítnutí přeskočí celou SMTP sekci a ostatní sekce mohou pokračovat
- SAFE automatický startup import konfliktní SMTP sekci nepřepíše, ale přeskočí ji s varováním; po odstranění konfliktu lze stejnou revision korektně aplikovat znovu
- UPD kompatibilní klíč `SERVER_URL` je v UI a dokumentaci označen jako Service host / FQDN a generované URL používají pouze normalizovaný hostname/FQDN/IP

## v2.1.1

- ADD centrální settings URL podporuje volitelný HTTP Basic Auth přes samostatný lokální bootstrap user/password; přihlašovací údaje nejsou v URL ani v šifrovaném SYSAPP1E balíku
- SEC Authorization hlavička se při redirectu zachová pouze na stejném scheme/host/port; redirect na jiný origin je zablokovaný a HTTP 401 vrací bezpečnou diagnostiku bez hesel
- UPD menu, dokumentace a regresní testy pro ISPConfig/Apache endpoint s rewrite a souborem uloženým mimo webroot

## v2.1.0

- ADD dynamický šifrovaný globální settings package `SYSAPP1E:` se samostatně verzovanými sekcemi; první sekce společně přenášejí SysApps Hub a SMTP, původní `SYSHUB1E:` zůstává kompatibilní pro ruční import
- ADD centrální read-only distribuce nastavení z HTTPS URL, ruční import z URL, automatický startup import pouze vyšší revision, SHA-256 ochrana stejné revision a bezpečný fallback na poslední lokální konfiguraci
- ADD ruční `Synchronize SysApps Hub` přímo v hlavním menu; položka je viditelná při zapnutém Hubu a aktivní pouze ve stavu `READY`, nezávisle na `HUB_AUTO_SYNC`
- ADD obousměrný Disk Manager provider: globální identita podle PTUUID, vazba disk-host-device, synchronizace názvů podle času změny a odmítnutí duplicitního PTUUID na jednom hostu jako pravděpodobného chybného klonu
- ADD Hub migrace `002_disk_inventory.sql` vytváří tabulky `disks` a `host_disks`; Disk Manager aktualizován na 3.6.0
- UPD hlavní verze aplikace na 2.1.0 a dokumentace centrálních nastavení, bezpečnostních pravidel a rozšiřitelného budoucího `sftp_backup` profilu

## v2.0.0

- FIX setup instaluje systémovou runtime závislost `lsof`; JBLibs 1.2.17 již při jejím chybění neukončí celou aplikaci během importu a chybu vrátí pouze při skutečné práci s mountpointem
- ADD SysApps Hub jako centrální MySQL/MariaDB inventář hostů, síťových adres a administračních služeb s neblokujícím health-checkem v hlavní hlavičce
- ADD verzované SQL migrace s jediným validovaným `{{PREFIX}}`, pevnou allowlist mapou tabulek, SHA-256 kontrolou a explicitní inicializací/upgrade schématu
- ADD obecný provider kontrakt `_HUB_PROVIDER_KEY_` + `hub_collect(context)`; provideři vrací pouze typované snapshoty a synchronizují se v oddělených transakcích
- ADD první Node-RED provider ukládá instance, systémové uživatele, porty/URL, Node-RED a Node.js verze, projekty, sanitizované Git remote a editorové uživatele RW/R bez hesel a hashů
- ADD App settings obsahuje konfiguraci Hubu, ruční Sync all, automatický startup sync a heslem šifrovaný jednořádkový export/import databázového nastavení
- UPD hlavní verze aplikace na 2.0.0 a runtime závislost PyMySQL 1.2.0

## v1.9.7

- FIX JBLibs 1.2.16 ukončí `c_menu` po Ctrl+C během čekání na volbu čistě bez tracebacku; KeyboardInterrupt z aktivní akce se dál nepolyká, aby zůstalo zachováno její cleanup/finally chování
- UPD verze podaplikací v hlavním menu mají jednoznačný prefix `v.`, například `(v. 3.5.0)`
- ADD hlavní dynamické menu zobrazuje vpravo vlastní verzi každé app_* podaplikace; Node-RED a SSH mají první explicitní verzi 1.0.0 a SFTP Manager je aktualizován na 1.2.5
- UPD Node-RED, SSH a SFTP mailové akce zobrazují fázi generování obsahu a společný SMTP wrapper těsně před transportem vypíše `Odesílám e-mail...`

- FIX Node-RED uživatelé jsou správně rozlišeni: předávací protokol uvádí jen uživatele editoru z adminAuth; legacy httpNodeAuth již nevydává za Dashboard 2 uživatele a menu jej označuje jako HTTP Node Auth

- ADD Node-RED Manager umí odeslat bezpečný předávací protokol instance bez hesel: URL, služba, Node-RED/Node.js verze, uživatelé RW/R, projekt a sanitizovaný Git remote i identita zařízení podle Disk Manageru

- FIX společný SMTP transport nyní přidává povinnou RFC Date hlavičku ještě před odesláním; JBLibs submodul aktualizován na verzi 1.2.15

- FIX mailové balíčky nyní jasně rozlišují běžný SSH účet s terminálovým přístupem a možností SCP/SFTP od omezeného SFTP účtu určeného pouze pro přenos souborů bez shellu; SFTP Manager 1.2.4

- ADD SSH Manager ukládá per-user e-mail kontakt do `~/.config/jb_sys_apps/contact.jsonc` a umí odeslat vybraný pár klíčů přes společný SMTP/ZIP transport; public-only importy neposílají dummy soukromý klíč

- UPD SFTP Manager 1.2.3 doplňuje do ZIP README konkrétní nastavení Total Commander SFTP pluginu a WinSCP, výchozí port 22 a vysvětlení serverem řízených práv; konkrétní host zůstává odděleným kanálem

- ADD SFTP Manager 1.2.2 odesílá veřejný a dostupný soukromý klíč jako ZIP s praktickými názvy souborů a přiloženým návodem
- FIX soukromý SFTP klíč se již nevypisuje přímo do textového ani HTML těla e-mailu
- ADD centrální SMTP transport v JBLibs podporuje přílohy z cest, bytes a streamů i ZIP archiv vytvořený bez dočasných souborů
- UPD aplikační `mail_hlp` používá společný transport, zachovává stávající SMTP konfiguraci a přijímá `attachments=` pro SFTP, SSH a Node-RED menu
- UPD JBLibs submodul na verzi 1.2.14 s redakcí SMTP hesla, dokumentací a unit testy
- ADD bezpečný self-updater aktualizuje hlavní repo, povinný JBLibs gitlink, povolené pluginy a spouští `setup.sh --no-run`
- FIX nepovinný privátní plugin bez tokenu již nezablokuje aktualizaci core ani JBLibs; povinné kroky se po updatu ověřují
- ADD `pluginy.jsonc` je katalog pluginů a `/etc/jb_sys_apps/plugins.jsonc` ukládá lokální enable/disable stav s vyšší prioritou než token
- ADD Plugin settings zobrazuje tabulkový katalog, správu tokenů, enable/disable a lokální uninstall se zachováním tokenu
- UPD dynamický loader nenačítá lokálně vypnuté pluginy a technické rozhraní je popsáno v `docs/plugin-system.md`
- ADD `setup.sh --no-run` provede instalaci bez spuštění vnořené instance aplikace
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
