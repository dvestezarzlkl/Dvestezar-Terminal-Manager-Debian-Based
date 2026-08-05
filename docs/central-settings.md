# Centralizovaná nastavení SysApps

SysApps 2.1.1 používá obecný šifrovaný balík `SYSAPP1E:` pro přenos nastavení, která mají být společná na více serverech. První podporované sekce jsou `hub` a `smtp`. Formát je záměrně dynamický, aby později mohl přibýt například profil `sftp_backup` bez změny kryptografické obálky.

## Rozdělení konfigurace

Do centrálního balíku patří přenositelné sekce:

- SysApps Hub / MySQL připojení,
- SMTP transport a fallback adresa,
- budoucí globální SFTP backup profily.

Lokální bootstrap se nikdy neimportuje z balíku:

```ini
SETTINGS_URL = "https://config.example/sys_apps/settings.txt"
SETTINGS_PASSWORD = "..."
SETTINGS_AUTH_USER = "optional-http-user"
SETTINGS_AUTH_PASSWORD = "optional-http-password"
SETTINGS_AUTO_UPDATE = true
SETTINGS_CONNECT_TIMEOUT = 5
SETTINGS_ALLOW_HTTP = false
SETTINGS_LAST_REVISION = 42
SETTINGS_LAST_SHA256 = "..."
SETTINGS_LAST_APPLIED = "hub:1,smtp:1"
```

Tím si vzdálený balík nemůže změnit vlastní zdroj, dešifrovací heslo, HTTP Basic Auth údaje ani ochranu proti návratu na starší verzi.

## Formát po dešifrování

```json
{
  "format": "sysapps-settings",
  "format_version": 1,
  "revision": 42,
  "created_at": "2026-08-04T16:00:00+00:00",
  "sections": {
    "hub": {
      "version": 1,
      "data": {}
    },
    "smtp": {
      "version": 1,
      "data": {}
    }
  }
}
```

- `format_version` určuje kryptografickou a strukturální generaci balíku,
- `revision` je kladná monotónní verze obsahu; ruční export generuje mikrosekundovou časovou revision, takže ani rychlé opakované exporty nepoužijí stejnou hodnotu,
- každá sekce má vlastní nezávislou verzi,
- neznámá budoucí sekce se přeskočí s varováním,
- známá sekce s nepodporovanou verzí se neaplikuje,
- import selže, pokud balík neobsahuje žádnou podporovanou sekci.

Balík je zašifrovaný AES-GCM, klíč se odvozuje ze zadaného hesla přes Scrypt a base64url slouží pouze jako jednořádková transportní obálka. Hesla se nezobrazují v náhledu ani logu.

## Ruční použití

V **App settings → Centralized settings** jsou akce:

- export šifrovaného balíku,
- ruční import vloženého řádku,
- import z nakonfigurované URL,
- nastavení bootstrap URL, dešifrovacího hesla, volitelného HTTP Basic Auth user/password, timeoutu a startup aktualizace.

Před ručním importem se zobrazí bezpečný náhled sekcí bez hesel. Všechny podporované sekce se nejdřív kompletně validují a pak uloží jedním `cfg.save()`. Ruční import může po výslovném potvrzení provést downgrade.

Původní Hub-only balík `SYSHUB1E:` z verze 2.0 zůstává podporovaný pro ruční import jako sekce `hub`. Automatický URL import legacy balíky nepřijímá. Legacy import zachová poslední anti-rollback revision, ale zneplatní uložený SHA centrálního balíku, aby se aktuální centrální konfigurace při dalším startu znovu aplikovala.

## Import z URL

- výchozí a doporučený transport je HTTPS,
- HTTP lze zapnout pouze explicitní varovnou volbou pro izolovanou LAN,
- URL nesmí obsahovat vložené jméno ani heslo,
- volitelný HTTP Basic Auth používá samostatné lokální `SETTINGS_AUTH_USER` a `SETTINGS_AUTH_PASSWORD`; klient posílá standardní `Authorization` hlavičku,
- oba HTTP auth údaje musí být nastavené společně nebo oba prázdné,
- redirect je povolen pouze v rámci stejného scheme, hostu a portu; Authorization se nikdy nepřenese na jiný origin,
- HTTP 401 rozlišuje chybějící autentizaci a odmítnuté přihlašovací údaje bez výpisu hesla,
- platí krátký timeout a limit 64 KiB,
- klient z URL pouze čte; export nebo upload z klienta není podporovaný.

Centrální soubor může být obsloužen běžným statickým webem spravovaným přes ISPConfig a jeho zálohy. Obsah souboru je jediný šifrovaný řádek vytvořený ručním exportem.

### Doporučené nasazení endpointu

Pro veřejně dosažitelný server je doporučená kombinace:

1. samostatná HTTPS subdoména a dlouhé náhodné veřejné cesty,
2. ISPConfig/Apache HTTP Basic Auth nad webem nebo fyzickým adresářem,
3. `Options -Indexes` a fallback rewrite neexistujících cest na společný `index.php`,
4. `index.php` funguje jako dispatcher: normalizuje `REQUEST_URI` a porovnává ji pouze s pevnou allowlist mapou rout,
5. každá routa volá konkrétní handler s pevně definovaným souborem v private adresáři mimo webroot; cesta z URL se nikdy neskládá do `include`, `require` ani filesystem cesty,
6. neznámé routy vracejí 404 a download handlery přijímají pouze GET/HEAD,
7. odpověď používá `text/plain`, `X-Robots-Tag: noindex` a `Cache-Control: no-store`.

Příklad obecného fallbacku v `.htaccess`:

```apache
Options -Indexes
RewriteEngine On

RewriteCond %{REQUEST_FILENAME} !-f
RewriteCond %{REQUEST_FILENAME} !-d
RewriteRule ^ index.php [END]
```

Dispatcher nesmí dynamicky načítat skript podle textu z URL. Použije pevnou mapu veřejná cesta -> handler:

```php
<?php

declare(strict_types=1);

$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH);
if (!is_string($path)) {
    http_response_code(404);
    exit;
}
$path = '/' . trim($path, '/');

$routes = [
    '/bnQFjPjxbuYndvZ4uys' => static function (): void {
        require __DIR__ . '/handlers/sysapps-settings.php';
    },
    // Budoucí samostatný endpoint:
    // '/jina-nahodna-cesta' => static function (): void { ... },
];

$handler = $routes[$path] ?? null;
if ($handler === null) {
    http_response_code(404);
    exit;
}

$handler();
```

Jednotlivý handler pak čte pouze svoji pevnou serverovou cestu, například `/var/www/clients/clientX/webY/private/sysapps/settings.txt`. Tím zůstane subdoména rozšiřitelná o další centrální konfigurace, ale náhodná cesta nemůže způsobit libovolné načtení souboru nebo PHP skriptu.

Náhodné cesty omezují hluk ze scannerů, ale nejsou autentizace. Basic Auth chrání stažení a AES-GCM/Scrypt balík chrání důvěrnost i integritu samotných nastavení. Skutečné PHP jméno ani private cesta nemusí být ve veřejné URL vidět.

## Automatická aktualizace při startu

Startup aktualizace běží po načtení lokálního `config.ini`, ale před Hub health-checkem a synchronizací.

- použije pouze vyšší `revision`,
- stejná revision se stejným SHA-256 je beze změny,
- stejná revision s jiným obsahem je chyba,
- nižší revision se automaticky nikdy neaplikuje,
- nedostupná URL, špatné heslo nebo vadný balík pouze vypíše varování a aplikace pokračuje s posledním lokálním nastavením,
- úspěšný import uloží revision, SHA-256 a podpis skutečně aplikovaných sekcí; po update klienta se stejný balík znovu aplikuje, pokud nová verze nově podporuje dříve přeskočenou sekci.

## Přidání nové sekce

Nová sekce registruje stabilní klíč, verzi a pět kontraktů:

1. seznam konfiguračních klíčů pro rollback,
2. exportér,
3. validátor a normalizátor,
4. applier bez samostatného `cfg.save()`,
5. bezpečný preview bez citlivých hodnot.

Budoucí `sftp_backup` bude obsahovat pouze globální profil cíle. Konkrétní aplikace, například Node-RED nebo Disk Manager, budou na profil pouze odkazovat a vytvořený artefakt předají společné transportní vrstvě. Privátní klíč ani heslo nebude vlastnit jednotlivý provider.
