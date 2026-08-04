# Disk Manager changelog

## v3.6.0

- ADD SysApps Hub provider synchronizuje fyzické disky podle normalizovaného PTUUID, jejich aktuální vazbu na host a bezpečná provozní metadata.
- ADD názvy disků se synchronizují oběma směry podle UTC času změny; prázdný název je timestampovaný tombstone a přenese úmyslné odstranění názvu.
- ADD starý formát `diskNames` zůstává kompatibilní a při prvním načtení se doplní čas změny podle mtime konfiguračního souboru.
- FIX dva fyzické disky se stejným PTUUID na jednom hostu synchronizaci odmítnou jako pravděpodobně nedokončený klon místo tichého sloučení.
- UPD přejmenování disku a vygenerování nového disk ID spouští best-effort synchronizaci, která nikdy nezmění úspěšnou lokální operaci na chybu.
