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
- `004_host_metadata_timer.sql`: centrálně editovatelná metadata hostu a hlášené zapnutí hodinového timeru.
- `005_host_groups.sql`: centrální skupiny serverů a volitelné přiřazení právě jedné skupiny hostu; `group_id NULL` = nepřiřazeno.
- `006_firewall_rules.sql`: typovaný katalog firewall pravidel s cílem `host/group/all` a odděleným vlastnictvím `host_local/central`.

## Datové sady

- `hosts`: machine-id, systémový hostname/FQDN, samostatný `service_host`, OS, kernel, architektura, hardware a verze sys_apps/JBLibs; navíc `name`/`description` spravované uživatelem a `auto_sync_enabled` hlášené strojem,
- `host_addresses`: samostatný řádek pro každou IPv4/IPv6 adresu a rozhraní,
- `host_services`: SSH, Webmin a ISPConfig včetně zjištěného portu/stavu,
- `sync_sources`: poslední stav každého zdroje,
- `node_red_instances`: instance, služby, URL, Node-RED/Node.js verze, projekt a sanitizovaný Git remote,
- `node_red_editor_users`: uživatelé `adminAuth` a jejich RW/R oprávnění,
- `disks`: globální disk podle jedinečného PTUUID, sdílený název a čas změny,
- `host_disks`: aktuální vazba disku na host, `/dev` zařízení, velikost, partitiony, mounty a systémový příznak.

Pole `hosts.name` a `hosts.description` jsou **user-owned**, v budoucím centrálním UI editovatelná, ale lokální SysApps je nikdy neposílá ani nepřepisuje. `name = NULL` znamená zobrazit `COALESCE(NULLIF(name,''),NULLIF(fqdn,''),hostname)`; FQDN se tedy nekopíruje do uživatelského názvu. `description` ukládá surový Markdown jako `TEXT`, při převodu do HTML jej UI musí bezpečně sanitizovat. Pole `auto_sync_enabled` hlásí skutečný stav `systemctl is-enabled jb-sysapps-hub.timer`, nikoli legacy `HUB_AUTO_SYNC`, a samo neprokazuje úspěšný hodinový běh. Při chybě detekce je hodnota neznámá (`NULL`) a dříve známá hodnota v DB se nemaže. Při změně režimu přes menu proběhne best-effort synchronizace core inventáře, aby vypnutí timeru nezůstalo bez zpětné aktualizace.

**Koordinace migrace 004:** starší SysApps 2.3.3 předpokládá přesnou verzi schématu 003; po globální migraci 004 začne hlásit `SCHEMA OUTDATED` a neprovede synchronizaci. Rozšíření tabulky je aditivní, ale kvůli klientské kontrole verze je nutné před migrací připravit sjednocenou aktualizaci ostatních sběrných klientů a zálohu DB. Akce `Inicializovat/aktualizovat schéma Hubu` spustí migraci až explicitně; samotný Update me ji nespouští.

### Skupiny serverů (schema 005)

`host_groups` je centrální, uživatelsky editovaný katalog `id INT UNSIGNED`, unikátní `code` (stabilní klíč pro policy), `name` a Markdown `description`. V `hosts` je jeden `group_id INT UNSIGNED NULL DEFAULT NULL`, s indexem a FK do `host_groups.id`. Nový i existující host je standardně bez skupiny, žádný default group se automaticky nevytváří. V případě vědomého smazání skupiny FK nastaví `hosts.group_id` na NULL. Stejně jako `hosts.name` a `hosts.description` je i `hosts.group_id` **USER-OWNED**: žádný lokální collector jej nesmí poslat ani změnit při core upsertu.

Skupiny hostů slouží pro budoucí cílení pravidel `host` / `group` / `all`. **Nejsou** to skupiny zdrojových IP adres (`home`/`office`/`vpn_admin`); ty mají budoucí samostatný katalog. Tato migrace zatím neobsahuje firewall pravidla ani nespouští UFW. Viz [firewall-manager-design.md](firewall-manager-design.md).

**Koordinovaný rollout 005/006:** SysApps 2.7.0 toleruje známé aditivní migrace 005 a 006 ještě neaplikované, takže může dál synchronizovat core a starší datasety proti v004/v005. Každý provider deklaruje minimální potřebné schéma; lokální `firewall_rules` se před schema 006 pouze přeskočí bez zápisu. Před ručním spuštěním čekajících migrací nejprve aktualizuj **všechny** klienty používající sdílenou DB na 2.7.0 a zazálohuj DB. Starší klient, který nezná 006, vyšší schéma odmítne. DDL spouští výhradně ruční akce `Inicializovat/aktualizovat schéma Hubu`, nikoli běžný Update me; menu vyžaduje dodatečné potvrzení koordinace flotily a zálohy.

Hesla, bcrypt hashe, Node-RED credentials, SMTP hesla a privátní klíče se do Hubu neukládají.

## Neinteraktivní sběr a plánovač

V hodinovém režimu se v hlavičce menu vedle stavu `systemd timer` uvádí i **Poslední běh služby** (čas startu a výsledek). Jde o poslední systemd spuštění, ať už hodinovým timerem nebo ručně, nikoli o potvrzení posledního automatického triggeru. Údaj se načítá read-only přes `systemctl show` při zobrazení menu; při chybě systemd se zobrazí „nedostupné“ a ostatní ovládání zůstává funkční. V režimech startup/off se tato informace ani nezjišťuje.

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

### Samostatný jednoduchý service collector bez SQL migrace

Od verze 2.4.0 lze v `sys_hub_plg` přidat jediný Python modul, který deklaruje `HUB_PROVIDER_KEY` a `hub_collect(context)`, vracející `HubProviderSnapshot(HUB_PROVIDER_KEY, "service", (HubService(HUB_PROVIDER_KEY, detected=..., status=..., version=...),))`. Tento kontrakt je záměrně úzký: nejvýše jedna služba na plugin, stabilní unikátní klíč shodný s `service_key`, bez rezervovaných klíčů `ssh`, `webmin` a `ispconfig`. Typované údaje zapíše jen pevný centrální writer do stávající `host_services`, a to výhradně pod klíčem příslušného pluginu. Prázdný úspěšný snapshot smaže pouze vlastní záznam, výjimka/selhání ponechá poslední úspěšná data. Core synchronizace nyní maže jen své tři pevné služby, takže nemůže odstranit výsledek sběrného pluginu.

První pilot `sys_hub_plg/bacula_fd.py` bezpečně detekuje Bacula FD pomocí systemd, instalované binárky a verze dpkg; neotevírá `bacula-fd.conf`, neukládá hesla ani nevymýšlí FD port (9102 není zaručené nastavení). Stav `active` neznamená, že funguje centrální zálohování.

Od v2.6.0 přibývá vestavěná podaplikace `app_40_firewall` s read-only UFW providerem. Od v2.7.0 vlastní lokální desired-state soubor `/etc/jb_sys_apps/firewall.json` a editor přes standardní `c_menu`/JBLibs input framework. Import starého JSON/JS používá `selectFile()`; běžné porovnání již nevyžaduje cestu a pracuje s kanonickým lokálním souborem. Lokální editor smí vytvořit jen pravidla tohoto hostu. Samostatný headless collector `firewall_rules` je v schema 006 ukládá jako `origin=host_local,target_kind=host`; nikdy nemaže ani nepřepisuje budoucí centrální `host/group/all` záznamy. Provider deklaruje `min_schema_version=6`, takže před migrací 006 je bezpečně přeskočen. Editace a synchronizace desired-state **stále nikdy** neprovádějí Apply, zápis do /etc/ufw ani UFW reload.

**Důležitá hranice:** obecný dataset `inventory_items`, více služeb/endpointů na jeden collector, plugin-local SQL migrace ani správa firewall/SSH desired-state zatím nejsou implementovány. Pro tyto složitější případy bude v další etapě potřeba samostatný typovaný dataset a centrální kontrola SQL schématu. Plugin nemá SQL spojení ani libovolný writer.

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
