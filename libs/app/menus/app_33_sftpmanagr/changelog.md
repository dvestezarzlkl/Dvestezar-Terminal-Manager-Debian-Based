# SFTP Manager Changelog

## 1.3.2

- FIX top-level počet mountpointů používá stejný local+template resolver jako user detail, takže template-only uživatel už není zobrazen jako `mountpointy:0`.
- FIX CIFS preflight vyhodnocuje enabled effective local+template mountpointy; template-only Samba user už nemůže obejít kontrolu `cifs-utils`, zatímco pouze disabled pointy ji zbytečně nevyžadují.
- UPD Apply používá JBLibs hotfix s resolver-based validací template-only uživatelů.

## 1.3.1

- FIX `selectDir()` vrací `pathlib.Path`; SFTP menu nyní výsledek na UI hranici normalizuje na string před uložením/validací local i template mountpointu, takže přidání a změna cesty nepadá na falešné validaci typu.
- TEST regrese používají skutečný `Path` návrat z `selectDir()` pro lokální i template add workflow.

## 1.3.0

- ADD spravované mountpoint šablony/profily s více přiřazenými uživateli a stabilními interními ID nezávislými na labelu/cestě.
- SAFE nový template mount se uživateli objeví jako Disabled + RO; Enabled a RW jsou explicitní per-user volby. Lokální mounty zůstávají zpětně kompatibilně Enabled, pokud `enabled` chybí.
- ADD vytvoření šablony z lokálních mountpointů existujícího uživatele pro rychlou migraci/onboarding dalších web vývojářů; zdrojový účet se při tom nemění.
- ADD uživatel může přiřazovat/odebírat šablony a v jednom Mountpoints přehledu vidí lokální i template položky se zdrojem a stavem Disabled/RO/RW.
- SAFE disabled položky zůstávají v konfiguraci, ale JBLibs 1.2.30 je vyřadí z effective desired mounts; Apply odstraní případný aktivní mount a znovu jej nevytvoří. Konfliktní výsledné labely failují před změnou systému.
- SAFE šablona sdílí pouze definici pointu; fyzická Samba/CIFS identita zůstává vždy `username + point` (`sftp_mount_<username>_<point>`), takže stejný template/path může mít u různých uživatelů nezávisle Disabled, RO nebo RW.
- SAFE přidání nebo přejmenování pointu v již přiřazené šabloně se před potvrzením validuje proti effective mountům všech jejích uživatelů; případná label kolize změnu okamžitě vrátí zpět místo vytvoření neaplikovatelné konfigurace.
- TEST regrese pokrývají bezpečné defaulty, stabilní ID, delete/recreate, unassign/reassign, per-user RO/RW nad stejným template pointem, fyzickou identitu `sftp_mount_<username>_<point>` a rollback kolizních změn šablony.

## 1.2.14

- UX při selhání Samba/CIFS batch transakce zobrazuje konkrétní důvod z JBLibs místo obecné chyby.
- SAFE neprázdný underlying managed mountpoint má vlastní hlášku s přesnou cestou a doporučením bezpečného rebuild workflow `u` -> `a`; Apply dál odmítá data znovu skrýt pod mount.
- UPD vyžaduje JBLibs 1.2.28 s typed `ManagedCIFSTargetNotEmptyError` a zachováním poslední konkrétní batch chyby.

## 1.2.13

- SAFE před destruktivním odstraněním SFTP uživatele se po fyzickém odpojení všech mountpointů automaticky zazálohuje celý jeho lokální home do `BACKUP_DIRECTORY/sftpusers/<user>/YYYY-MM-DD_HHMMSS_<user>_backup.7z`; připojená zdrojová data se do archivu nedostanou.
- SAFE pokud pod home po odpojení zůstane živý mount nebo vytvoření archivu selže, odstranění uživatele se zastaví. Neočekávaný obsah pod historickým mountpointem tak zůstane zachovaný v backupu před rebuildem.
- ADD hlavní SFTP menu zobrazuje pouze souhrn počtu a celkové velikosti existujících SFTP backupů; správu/restore archivů záměrně nepřidává.
- UPD JBLibs 1.2.27 používá obecný timestampovaný 7z directory-backup helper a po fyzickém odmountování odstraní prázdné mountpoint adresáře přes `rmdir`; do backupu zachová pouze neprázdné targety s neočekávanými underlying daty.

## 1.2.12

- FIX JBLibs 1.2.25 po změně Samba konfigurace reloaduje `smbd` a cíleně ukončí pouze spojení dotčených spravovaných `sftp_mount_*` share; nové CIFS připojení tak převezme změnu RO/RW okamžitě v tomtéž Apply. Pokud cílený `smbcontrol close-share` selže nebo není dostupný, použije se bezpečný fallback na restart `smbd`.
- SAFE spravovaný CIFS target musí být po odmountování prázdný; neprázdný target se už nesmí překrýt mountem a skrýt tak pod ním data. Prázdné underlying targety jsou před remountem root-owned a bez zápisu pro SFTP uživatele.
- FIX `Odinstalovat všechny uživatele` po explicitním potvrzení umí odstranit neprázdný jail rekurzivně, ale nejprve přes `/proc/self/mountinfo` ověří, že jail ani žádný jeho podadresář už není CIFS/bind/jiný mountpoint; při nemožnosti mount stav ověřit se cleanup bezpečně zastaví.
- UX nekritická hláška `loginctl terminate-user` pro uživatele bez aktivní session už neprosakuje přímo do terminálového UI.
- TEST JBLibs regrese pokrývají live close-share, fallback restart, zákaz mountu přes skrytá data, transakční pořadí a bezpečný cleanup neprázdného jailu.

## 1.2.11

- FIX aktualizace na JBLibs 1.2.23 opravuje Samba/CIFS batch transakci při změně RO/RW nebo reálné cesty existujícího mountpointu; fyzický unmount a cleanup se provádí až při finalizaci celé dávky.
- FIX finalizace nejprve odmountuje všechny spravované CIFS mounty, zachová cíle znovu vytvořené ve stejné dávce, odstraní pouze skutečně obsolete adresáře a až poté reloaduje Sambu, systemd a připojí výsledný stav.
- FIX kontrola existujícího Samba mountu používá identitu SFTP uživatele místo vlastníka zdrojového adresáře.
- TEST JBLibs regrese pokrývají pořadí batch operací, zákaz předčasného cleanupu, remove+recreate stejného cíle a správnou identitu share.

## 1.2.10

- FIX ESC ve výběru akce mountpointu i režimu při přidání bezpečně vrací cancel; výsledek `select()` s `item=None` už nezpůsobí `AttributeError`.
- FIX Apply používá požadovanou konfiguraci přímo z paměti a zapisuje ji do `/etc/jb_sftpmanager/config.jsonc` až po úspěšné systémové synchronizaci a restartu SSHD; neúspěšný Apply tak nepřepíše poslední známou uloženou konfiguraci neaplikovaným stavem.
- DIAG při selhání `createUserFromJson()` se do chyby Apply přenese poslední konkrétní chyba uživatele místo samotného obecného `NO_USERS_PROCESSED`.
- UPD vyžaduje JBLibs 1.2.22 s in-memory SFTP reconcile a diagnostikou chyb.

## 1.2.9

- FIX po úspěšném Apply se konfigurace znovu načte z perzistentního souboru a obnoví se `cfg` i seznam uživatelů; další změna cesty nebo RO/RW ve stejném běhu aplikace tak nepoužívá stale objekty z předchozí transakce.
- UPD JBLibs 1.2.21 opravuje obecné `c_menu` veto výstupu: `onExitMenu() -> False` se nyní respektuje pro ESC i `endMenu`, takže odmítnutí zahození neuložených změn skutečně ponechá SFTP menu otevřené.
- TEST regresní pokrytí ověřuje, že úspěšný Apply nahradí in-memory konfiguraci čerstvě načtenou instancí před dalším editováním; JBLibs testy pokrývají ESC i `endMenu` veto.

## 1.2.8

- FIX změna cesty existujícího mountpointu otevírá výběr adresáře na jeho aktuální reálné cestě, pokud stále existuje; `/` se použije pouze jako fallback pro chybějící nebo neplatný adresář.
- FIX hlavní SFTP menu při neuložených změnách před odchodem vyžaduje potvrzení jejich zahození; odmítnutí výstup zablokuje a zachová pending konfiguraci.
- SAFE potvrzení při odchodu pouze rozhoduje o zahození pending změn; výstup z menu nikdy automaticky nespouští Apply ani jiné systémové změny.
- TEST regresní pokrytí ověřuje start na aktuální cestě, fallback na root a ochranu výstupu s neuloženými změnami.

## 1.2.7

- FIX Apply nyní detekuje i samostatnou změnu RO/RW u Samba-backed mountpointu, i když alias a reálná cesta zůstaly stejné.
- UPD JBLibs 1.2.20 porovnává požadované `pointsSet[label].rw` se skutečným `read only = yes/no` v řízené Samba sekci; při rozdílu nebo nečitelném stavu point bezpečně znovu synchronizuje v existující Samba/CIFS transakci.
- SAFE interní `.sftp_mounts_mng` se nepoužívá jako zdroj RO/RW stavu, protože historicky ukládá pouze alias a reálnou cestu.

## 1.2.6

- FIX volba `Pouze čtení (R)` při přidání mountpointu se ukládá jako RO; menu používá datovou hodnotu vybrané položky místo porovnání wrapper objektu z `select()`.
- UX detail existujícího mountpointu umožňuje změnit reálnou cestu při zachování aliasu a RO/RW nastavení.
- Apply používá existující synchronizaci podle rozdílu reálné cesty: starou Samba/CIFS/jail definici odstraní a stejný alias znovu vytvoří z nové cesty; chyby zůstávají v běžném Apply log/return flow.

Starší změny SFTP Manageru jsou evidované v kořenovém `changelog.md` projektu.