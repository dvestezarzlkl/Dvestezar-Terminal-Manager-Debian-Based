# SysApps Hub 2.0.0

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

Nastavení lze exportovat jako jeden heslem šifrovaný řádek s prefixem `SYSHUB1E:`. Base64url je pouze transportní obálka; obsah je šifrovaný AES-GCM a klíč se odvozuje ze zadaného hesla přes Scrypt. Aplikace neobsahuje žádný pevný šifrovací klíč.

## Schéma a migrace

Schéma je uloženo ve verzovaných souborech `libs/app/hub/migrations/NNN_name.sql`.

- jediný podporovaný placeholder je `{{PREFIX}}`,
- SQL příkazy odděluje samostatný řádek `-- statement`,
- runtime skládá názvy pouze z validovaného prefixu a pevné allowlist přípony,
- hodnoty se zapisují parametrizovaným SQL,
- provedené migrace ukládají verzi, název a SHA-256 původní šablony,
- checksum mismatch zastaví upgrade a vyžaduje ruční kontrolu.

Akce **Inicializovat/aktualizovat schéma Hubu** může vytvořit nakonfigurovanou databázi a aplikuje pouze migrace dodané s aplikací.

## První datové sady

- `hosts`: machine-id, hostname/FQDN, OS, kernel, architektura, hardware a verze sys_apps/JBLibs,
- `host_addresses`: samostatný řádek pro každou IPv4/IPv6 adresu a rozhraní,
- `host_services`: SSH, Webmin a ISPConfig včetně zjištěného portu/stavu,
- `sync_sources`: poslední stav každého zdroje,
- `node_red_instances`: instance, služby, URL, Node-RED/Node.js verze, projekt a sanitizovaný Git remote,
- `node_red_editor_users`: uživatelé `adminAuth` a jejich RW/R oprávnění.

Hesla, bcrypt hashe, Node-RED credentials, SMTP hesla a privátní klíče se do Hubu neukládají.

## Provider kontrakt

Dynamická podaplikace může v `menu.py` nabídnout:

```python
_HUB_PROVIDER_KEY_ = "node_red"

def hub_collect(context):
    return typed_snapshot
```

Provider nedostává DB spojení, kurzor, SQL ani názvy tabulek. Centrální runtime ověří zdroj a datovou sadu a zavolá pevně známý writer.

Každý provider běží odděleně. Chyba provideru:

- nezruší úspěšný core host snapshot,
- nezablokuje ostatní providery,
- zapíše stav `error` do `sync_sources`, pokud je DB dostupná,
- zachová poslední úspěšná data provideru.

Staré záznamy se mažou pouze po kompletním úspěšném snapshotu daného provideru.

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

Pokud je Hub `READY` a `HUB_AUTO_SYNC=true`, proběhne jeden startup `Sync all`. Ruční synchronizace je v App settings. Node-RED Save spouští best-effort synchronizaci Node-RED provideru; chyba Hubu nikdy nezmění úspěšný lokální Save na chybu.
