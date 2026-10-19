# SysApps Hub

SysApps Hub je centrální inventář instalací Terminal Manageru. MySQL/MariaDB slouží jako přenosová a úložná vrstva; lokální funkce aplikace musí zůstat použitelné i při výpadku Hubu.

## Konfigurace

Globální nastavení se ukládá do `/etc/jb_sys_apps/config.ini` přes běžné `cfg.save()`:

```ini
HUB_ENABLED = true
HUB_DB_HOST = "db.internal.example"
HUB_DB_PORT = 3306
HUB_DB_USER = "sysapps"
HUB_DB_PASSWORD = "..."
HUB_DB_NAME = "sys_apps"
HUB_DB_PREFIX = "sysapps_"
HUB_CONNECT_TIMEOUT = 3
HUB_AUTO_SYNC = true
```

Prefix musí začínat malým písmenem a smí obsahovat pouze malá písmena, číslice a podtržítko. Název databáze smí obsahovat pouze písmena, číslice a podtržítko.

Lokální `SERVER_URL` je historický kompatibilní klíč pro **Service host / FQDN / IP**. Není součástí centrálního settings balíku. Hub jej ukládá do `hosts.service_host` odděleně od systémových `hostname` a `fqdn`, protože systémový název stroje a adresa používaná pro přístup ke službám přes VPN nemusí být stejné.

Původní balíky `SYSHUB1E:` lze dál ručně importovat. Nový obecný export/import používá dynamický balík `SYSAPP1E:` popsaný v [central-settings.md](central-settings.md) a společně přenáší Hub a SMTP.

## Schéma a migrace

Schéma je uloženo ve verzovaných souborech `libs/app/hub/migrations/NNN_name.sql`.

- jediný podporovaný placeholder je `{{PREFIX}}`,
- SQL příkazy odděluje samostatný řádek `-- statement`,
- runtime skládá názvy pouze z validovaného prefixu a pevné allowlist přípony,
- hodnoty se zapisují parametrizovaným SQL,
- provedené migrace ukládají verzi, název a SHA-256 původní šablony,
- checksum mismatch zastaví upgrade a vyžaduje ruční kontrolu.

Akce **Inicializovat/aktualizovat schéma Hubu** může vytvořit nakonfigurovanou databázi a aplikuje pouze migrace dodané s aplikací.

Aktuální migrace:

- `001_initial_schema.sql`: host, adresy, služby, zdroje synchronizace a Node-RED,
- `002_disk_inventory.sql`: globální registr disků a vazby disk-host-device,
- `003_service_host_identity.sql`: samostatná lokální service host/FQDN/IP identita hostu.

## Datové sady

- `hosts`: machine-id, systémový hostname/FQDN, samostatný `service_host`, OS, kernel, architektura, hardware a verze sys_apps/JBLibs,
- `host_addresses`: samostatný řádek pro každou IPv4/IPv6 adresu a rozhraní,
- `host_services`: SSH, Webmin a ISPConfig včetně zjištěného portu/stavu,
- `sync_sources`: poslední stav každého zdroje,
- `node_red_instances`: instance, služby, URL, Node-RED/Node.js verze, projekt a sanitizovaný Git remote,
- `node_red_editor_users`: uživatelé `adminAuth` a jejich RW/R oprávnění,
- `disks`: globální disk podle jedinečného PTUUID, sdílený název a čas změny,
- `host_disks`: aktuální vazba disku na host, `/dev` zařízení, velikost, partitiony, mounty a systémový příznak.

Hesla, bcrypt hashe, Node-RED credentials, SMTP hesla a privátní klíče se do Hubu neukládají.

## Neinteraktivní sběr a plánovač

V hodinovém režimu se v Hub menu zobrazí také **Ověřit/otestovat systemd synchronizaci**. Nejprve pouze čte skutečný systemd stav obou jednotek (spravované soubory, enabled/active, poslední plánovaný trigger, poslední dokončení služby a exit status, příští trigger). Kontrola času používá u hodinového kalendáře toleranci 65 min kvůli nastavení RandomizedDelaySec=2min a AccuracySec=1min. Čerstvý ruční sběr není důkazem, že se již spustil samotný timer: oba časy se evidují zvlášť. Pokud ještě plánovaný běh nenastal, diagnostika to přizná. Po výpisu se nabídne potvrzený jednorázový běh přes systemctl start jb-sysapps-hub.service; timer se nemění a žádná služba se nespouští před souhlasem uživatele. Čeká se na dokončení oneshot (do limitu služby) a následně se ověří exit status i čerstvý výsledek. Neúspěch lze dohledat v journalctl -u jb-sysapps-hub.service.

Hlavní aplikace nabízí lokální volbu: **startup**, **timer** (každou hodinu) nebo **off**; ruční synchronizace zůstává dostupná vždy, pokud je Hub zapnutý. Výběr režimu je přes JBLibs `select()` (šipky/Enter nebo zkratky S/T/O, ESC bez změny). Prázdná hodnota nového lokálního `HUB_SYNC_MODE` zachovává historickou politiku `HUB_AUTO_SYNC` bez zásahu do stávajících instalací. `HUB_SYNC_MODE` se nikdy nedistribuuje centrálním balíkem `SYSAPP1E`.

Volba **timer** z menu vytvoří spravované jednotky `/etc/systemd/system/jb-sysapps-hub.service` a `jb-sysapps-hub.timer`, aktivuje časovač a teprve pak uloží režim. Timer spouští `run.sh --hub-sync` přes stejný Python virtualenv a bez grafického/terminálového menu. Všechna spuštění sdílejí procesní lock pro synchronizaci, nezávislý na zámku otevřeného menu. Manuální a automatické spouštění mohou koexistovat; při souběhu druhý sběr bezpečně skončí chybou/skipped, ne paralelním zápisem.

Pro ruční ověření lze použít `sudo /opt/sys_apps/run.sh --hub-sync` a `systemctl status jb-sysapps-hub.timer` / `journalctl -u jb-sysapps-hub.service`. V reálné instalaci se cesta určí podle umístění aplikace. Při nedostupnosti centrální DB neproběhne schema upgrade ani změna lokální konfigurace.

## Headless provider a sběrné pluginy

Samostatné sběrné moduly jsou interní, důvěryhodné soubory v `libs/app/hub/sys_hub_plg/` a neobjevují se jako další terminálová menu. Jeden modul implementuje `HUB_PROVIDER_KEY` a `hub_collect(context)` a vrací `HubProviderSnapshot` pro aktuálně podporovaný `dataset`. Načítání je sdílené v headless i interaktivním režimu. Stávající `app_*` poskytovatelé zůstávají funkční přes `hub_provider.py` a starší `menu.py` kontrakt, včetně oprávnění v PluginRegistry.

Příklad rozhraní (až po přidání datasetu do centrálního writeru):

```python
HUB_PROVIDER_KEY = "bacula_fd"

def hub_collect(context):
    # Pouze read-only lokální detekce; bez SQL a DB credentials.
    return HubProviderSnapshot("bacula_fd", "inventory_items", items)
```

**Důležitá hranice:** obecný dataset `inventory_items` ani plugin-local schema migrace v této etapě ještě nejsou implementovány. Současný DB writer přijímá pouze existující typované datasety. Nový plugin nesmí sám provádět SQL; rozšíření tabulek bude v další etapě řešit centrální migrátor s verzemi, SHA-256 a kontrolou namespace. Záměr je zachovat možnost přidat nový jednoduchý collector jediným souborem, aniž by získal přístup k DB.

## Provider kontrakt

Dynamická podaplikace může v `menu.py` nabídnout jednosměrný provider:

```python
_HUB_PROVIDER_KEY_ = "node_red"

def hub_collect(context):
    return typed_snapshot
```

Obousměrný provider navíc nabídne applier změn vrácených centrálním writerem:

```python
_HUB_PROVIDER_KEY_ = "disks"

def hub_collect(context):
    return typed_snapshot

def hub_apply_remote(updates):
    apply_validated_updates(updates)
```

Provider nedostává DB spojení, kurzor, SQL ani názvy tabulek. Centrální runtime ověří zdroj a datovou sadu a zavolá pevně známý writer. Zpětné změny se aplikují až po úspěšném commitu databázové transakce.

Každý provider běží odděleně. Chyba provideru:

- nezruší úspěšný core host snapshot,
- nezablokuje ostatní providery,
- zapíše stav `error` do `sync_sources`, pokud je DB dostupná,
- zachová poslední úspěšná data provideru.

Staré záznamy se mažou pouze po kompletním úspěšném snapshotu daného provideru.

## Disk Manager a PTUUID

PTUUID je globální identita celého disku. Název zařízení jako `sda` nebo `nvme0n1` je pouze aktuální lokální vazba.

- tabulka `disks` má nad PTUUID unikátní klíč,
- tabulka `host_disks` drží jedinou aktuální vazbu disku; synchronizace na novém hostu automaticky nahradí starý host a dovolí sledovat fyzický přesun,
- lokální názvy se ukládají s UTC časem změny,
- novější název vyhraje v obou směrech, včetně úmyslného vymazání názvu,
- starý `diskNames` JSON zůstává kompatibilní a při prvním načtení dostane čas podle mtime souboru,
- dva fyzické disky se stejným PTUUID na jednom hostu synchronizaci odmítnou jako pravděpodobně špatně dokončený klon,
- loop zařízení se do globálního registru neposílají.

## Synchronizace

Při startu se provede krátký health-check. Stav je vidět v hlavní hlavičce:

- `DISABLED`,
- `NOT CONFIGURED`,
- `OFFLINE`,
- `DATABASE MISSING`,
- `SCHEMA MISSING`,
- `SCHEMA OUTDATED`,
- `READY`,
- `ERROR`.

Pokud je Hub `READY` a `HUB_AUTO_SYNC=true`, proběhne jeden startup `Sync all`. Ruční synchronizace je přímo v hlavním menu, pokud je Hub zapnutý; položka je aktivní pouze ve stavu `READY`. `HUB_AUTO_SYNC=false` vypíná jen automatiku a ruční synchronizaci neblokuje.

Node-RED Save a změna názvu nebo ID disku spouští best-effort synchronizaci svého provideru. Chyba Hubu nikdy nezmění úspěšnou lokální operaci na chybu.
