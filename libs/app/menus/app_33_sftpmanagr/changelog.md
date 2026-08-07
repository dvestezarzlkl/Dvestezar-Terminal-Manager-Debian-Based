# SFTP Manager Changelog

## 1.2.6

- FIX volba `Pouze čtení (R)` při přidání mountpointu se ukládá jako RO; menu používá datovou hodnotu vybrané položky místo porovnání wrapper objektu z `select()`.
- UX detail existujícího mountpointu umožňuje změnit reálnou cestu při zachování aliasu a RO/RW nastavení.
- Apply používá existující synchronizaci podle rozdílu reálné cesty: starou Samba/CIFS/jail definici odstraní a stejný alias znovu vytvoří z nové cesty; chyby zůstávají v běžném Apply log/return flow.

Starší změny SFTP Manageru jsou evidované v kořenovém `changelog.md` projektu.
