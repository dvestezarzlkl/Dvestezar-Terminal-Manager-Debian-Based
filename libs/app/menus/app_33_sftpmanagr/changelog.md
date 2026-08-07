# SFTP Manager Changelog

## 1.2.7

- FIX Apply nyní detekuje i samostatnou změnu RO/RW u Samba-backed mountpointu, i když alias a reálná cesta zůstaly stejné.
- UPD JBLibs 1.2.20 porovnává požadované `pointsSet[label].rw` se skutečným `read only = yes/no` v řízené Samba sekci; při rozdílu nebo nečitelném stavu point bezpečně znovu synchronizuje v existující Samba/CIFS transakci.
- SAFE interní `.sftp_mounts_mng` se nepoužívá jako zdroj RO/RW stavu, protože historicky ukládá pouze alias a reálnou cestu.

## 1.2.6

- FIX volba `Pouze čtení (R)` při přidání mountpointu se ukládá jako RO; menu používá datovou hodnotu vybrané položky místo porovnání wrapper objektu z `select()`.
- UX detail existujícího mountpointu umožňuje změnit reálnou cestu při zachování aliasu a RO/RW nastavení.
- Apply používá existující synchronizaci podle rozdílu reálné cesty: starou Samba/CIFS/jail definici odstraní a stejný alias znovu vytvoří z nové cesty; chyby zůstávají v běžném Apply log/return flow.

Starší změny SFTP Manageru jsou evidované v kořenovém `changelog.md` projektu.
