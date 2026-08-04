# Centralizovaná nastavení SysApps

SysApps 2.1 používá obecný šifrovaný balík `SYSAPP1E:` pro přenos nastavení, která mají být společná na více serverech. První podporované sekce jsou `hub` a `smtp`. Formát je záměrně dynamický, aby později mohl přibýt například profil `sftp_backup` bez změny kryptografické obálky.

## Rozdělení konfigurace

Do centrálního balíku patří přenositelné sekce:

- SysApps Hub / MySQL připojení,
- SMTP transport a fallback adresa,
- budoucí globální SFTP backup profily.

Lokální bootstrap se nikdy neimportuje z balíku:

```ini
SETTINGS_URL = "https://config.example/sys_apps/settings.txt"
SETTINGS_PASSWORD = "..."
SETTINGS_AUTO_UPDATE = true
SETTINGS_CONNECT_TIMEOUT = 5
SETTINGS_ALLOW_HTTP = false
SETTINGS_LAST_REVISION = 42
SETTINGS_LAST_SHA256 = "..."
SETTINGS_LAST_APPLIED = "hub:1,smtp:1"
```

Tím si vzdálený balík nemůže změnit vlastní zdroj, dešifrovací heslo ani ochranu proti návratu na starší verzi.

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
- nastavení bootstrap URL, hesla, timeoutu a startup aktualizace.

Před ručním importem se zobrazí bezpečný náhled sekcí bez hesel. Všechny podporované sekce se nejdřív kompletně validují a pak uloží jedním `cfg.save()`. Ruční import může po výslovném potvrzení provést downgrade.

Původní Hub-only balík `SYSHUB1E:` z verze 2.0 zůstává podporovaný pro ruční import jako sekce `hub`. Automatický URL import legacy balíky nepřijímá. Legacy import zachová poslední anti-rollback revision, ale zneplatní uložený SHA centrálního balíku, aby se aktuální centrální konfigurace při dalším startu znovu aplikovala.

## Import z URL

- výchozí a doporučený transport je HTTPS,
- HTTP lze zapnout pouze explicitní varovnou volbou pro izolovanou LAN,
- URL nesmí obsahovat vložené jméno ani heslo,
- kontroluje se i finální URL po redirectu,
- platí krátký timeout a limit 64 KiB,
- klient z URL pouze čte; export nebo upload z klienta není podporovaný.

Centrální soubor může být obsloužen běžným statickým webem spravovaným přes ISPConfig a jeho zálohy. Obsah souboru je jediný šifrovaný řádek vytvořený ručním exportem.

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
