# SFTP Jail Manager

Skript pro správu SFTP uživatelů v SSH jailu (chroot) s možností připojit adresáře do jailu buď:

* bind mountem, nebo
* “Samba vault” režimem (ghosting přes CIFS), kdy se do jailu připojí CIFS mounty a Samba sharepointy se generují automaticky.

Verze knihovny: `3.6.0` (viz `glob.py`).

## Co to umí

Po `install` podle konfigurace typicky udělá:

1. Vytvoří systémového uživatele (pokud neexistuje) v `/home_sftp_users/<user>/`
2. Vytvoří jail adresář: `/home_sftp_users/<user>/__sftp__/`
3. Vygeneruje SSHD konfiguraci do `/etc/ssh/sshd_config.d/sftp-<user>.conf` (Match User, ChrootDirectory, internal-sftp)
4. Zajistí `.ssh/authorized_keys` a vloží veřejné klíče
5. Vytvoří mountpointy v jailu:

   * buď bind mount (default), nebo
   * Samba vault (CIFS ghosting): generuje Samba share sekce + systemd mount jednotky (a řeší samba uživatele pro mounty)

Po `uninstall` uživatele smaže včetně jeho navázaných věcí (mounty, sshd config, klíče, atd. podle implementace tříd).

## Požadavky

* spouštět jako root (nebo přes sudo)
* OpenSSH server se složkou `/etc/ssh/sshd_config.d/` (Ubuntu typicky ano)
* pokud používáš `sambaVault: true`:

  * nainstalovaná Samba + CIFS utils
  * funkční `smb.conf`
  * povolené a funkční mounty (systemd mount jednotky / fstab dle implementace)

## Umístění konfigurace

Skript používá fixní cestu:

* adresář: `/etc/jb_sftpmanager`
* soubor: `/etc/jb_sftpmanager/config.jsonc`

Při prvním spuštění se adresář vytvoří automaticky a do něj se nakopíruje ukázkový config z `assets/sftpManagerExampleConfig.jsonc` jako `config.jsonc`, ale s úmyslnou hlavičkou:

`! Nový soubor, upravte podle potřeby!`

Dokud ji neodstraníš, `install` odmítne pokračovat.

## Spuštění

Příklady (přizpůsob si cestu na skutečný soubor skriptu):

### Instalace uživatelů z konfigurace

```bash
sudo ./sftpmanager.py install
```

* načte `/etc/jb_sftpmanager/config.jsonc`
* vytvoří/aktualizuje uživatele, mounty, klíče, sshd konfiguraci
* skript během operace restartuje sshd

### Odinstalace jednoho uživatele

```bash
sudo ./sftpmanager.py uninstall --user zlkl_web
```

### Odinstalace všech spravovaných uživatelů

```bash
sudo ./sftpmanager.py uninstall
```

(bez `--user` se bere jako “all”)

### Výpis aktivních SFTP uživatelů

```bash
sudo ./sftpmanager.py list
```

Poznámka: list filtruje uživatele podle home adresáře začínajícího `/home_sftp_users`.

## Formát konfigurace `config.jsonc`

Používá se JSON5 (jsonc). Můžeš mít buď:

* jeden objekt uživatele v rootu, nebo
* root objekt s polem `users: []`

Doporučené je pole `users`.

### Root struktura

```jsonc
{
  "users": [
    { /* user 1 */ },
    { /* user 2 */ }
  ]
}
```

### Struktura uživatele

Povinné:

* `sftpuser` (string)

  * jméno uživatele
  * povolené znaky: `a-zA-Z0-9._-`

Volitelné:

* `sambaVault` (bool)

  * `false` (default) = bind mount
  * `true` = Samba vault (ghosting přes CIFS)

* `sftpmounts` (object)

  * mapování: `mountpointName` → `/absolutni/cesta/k/realnym/ datum`
  * cesta musí existovat a být absolutní

* `pointsSet` (object)

  * mapování: `mountpointName` → `{ my: bool, rw: bool }`
  * `my` default `true`

    * “vlastnictví mountu” (v Samba vault režimu se to překlápí do způsobu jak se share/mount připraví)
  * `rw` default `true`

    * `false` = readonly režim

* `sftpcerts` (array of strings)

  * veřejné SSH klíče
  * musí začínat `ssh-` nebo `ecdsa-`
  * podporuje i `b64:<base64>` (pak se dekóduje)

### Minimální příklad

```jsonc
{
  "users": [
    {
      "sftpuser": "testuser",
      "sftpcerts": [
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI.... user@pc"
      ]
    }
  ]
}
```

### Příklad s mounty

```jsonc
{
  "users": [
    {
      "sftpuser": "zlkl_web",
      "sambaVault": true,
      "sftpmounts": {
        "main": "/var/www/clients/client3/web9/web"
      },
      "pointsSet": {
        "main": { "my": false, "rw": true }
      },
      "sftpcerts": [
        "ssh-ed25519 AAAA... zlkl_web@key"
      ]
    }
  ]
}
```

## Co se typicky mění v systému

Při instalaci se běžně objeví / upraví:

* `/home_sftp_users/<user>/__sftp__/` (jail root)
* `/home_sftp_users/<user>/.ssh/authorized_keys`
* `/etc/ssh/sshd_config.d/sftp-<user>.conf`
* mountpoint adresáře v jailu:

  * `/home_sftp_users/<user>/__sftp__/<mountName>`
* při `sambaVault: true`:

  * doplnění share sekcí do `smb.conf` (typicky `sftp_mount_<user>_<mount>`)
  * systémové mount jednotky (systemd) pro CIFS ghosting
  * “samba technický uživatel” pro přístup k share (interně)

## Troubleshooting

### Install hlásí “Config file not configured yet”

* otevři `/etc/jb_sftpmanager/config.jsonc`
* smaž úvodní řádek začínající `! Nový soubor...`
* doplň své uživatele/mounty/klíče

### Klíč se nepřidal

* `sftpcerts` musí začínat `ssh-` nebo `ecdsa-`
* nebo použij `b64:...` (bude dekódováno)

### Mountpoint se nevytvořil

* u `sftpmounts` musí cesta existovat a být absolutní
* u sambaVault režimu navíc zkontroluj:

  * Samba běží
  * `smb.conf` je validní
  * CIFS mounty nejsou blokované (credentials, síť, práva)

### SSH jail nefunguje

* zkontroluj, že existuje `/etc/ssh/sshd_config.d/sftp-<user>.conf`
* zkontroluj restart sshd po instalaci
* ověř `ChrootDirectory` musí být vlastněný rootem a nesmí být zapisovatelný pro user (to je pravidlo OpenSSH)

## Doporučené workflow pro správu

* `/etc/jb_sftpmanager/config.jsonc` drž jako “single source of truth”
* do `/etc/jb_sftpmanager/` přidej `README.md` s mapou mountů (přehled)
* reálné klíče neukládej do gitu (správně), ale config si klidně verzuj interně:

  * například privátní repo
  * nebo tar snapshoty do `/root/backup/`

## Samba Vault režim (bezpečnější sandbox sdílení)

### Proč nepoužívat bind mount

Klasický bind mount:

```sh
mount --bind /real/data /home_sftp_users/user/__sftp__/data
```

Problém:

* SFTP uživatel fyzicky pracuje nad reálným filesystemem.
* Oprávnění řešíš jen POSIX právy.
* Pokud něco pokazíš (ACL, group), můžeš otevřít víc než chceš.
* Nelze snadno oddělit "SFTP pohled" od reálného systému.

Je to rychlé, ale není to oddělené.

### Co dělá Samba Vault

Místo přímého bind mountu:

1. Vygeneruje Samba share sekci pro konkrétní mount
2. Připojí ji přes CIFS zpět do jailu
3. SFTP uživatel pracuje nad CIFS mountem, ne nad skutečným adresářem

Architektura:

```txt
/var/www/webX
        ↓
[Samba share]
        ↓
CIFS mount (localhost)
        ↓
/home_sftp_users/user/__sftp__/webX
```

Tím vznikne vrstva oddělení.

### Co to přináší bezpečnostně

#### 1. Oddělení identity

CIFS mount běží pod kontrolovaným systémovým účtem (ne pod SFTP uživatelem).

To znamená:

* SFTP user nikdy přímo nepracuje s reálným inode.
* Nemůže obejít chroot přes filesystem triky.

#### 2. Můžeš omezit práva na úrovni Samba

V `smb.conf` můžeš řídit:

* read only = yes/no
* valid users
* force user
* force group
* create mask
* directory mask

To je druhá bezpečnostní vrstva nad POSIX právy.

#### 3. Lze použít readonly mount

Pokud v configu dáš:

```jsonc
"pointsSet": {
  "main": { "my": false, "rw": false }
}
```

Mount se vytvoří readonly.

To znamená:

* SFTP uživatel může jen číst
* Nemůže nic smazat ani přepsat

To je ideální pro:

* export dat
* reporting
* download-only přístup

#### 4. Žádné přímé vazby na systémové ACL

Bind mount:

* je jen jiný pohled na tentýž strom.

Samba Vault:

* je síťová vrstva (byť localhost).
* odděluje namespace.
* odděluje file handles.

To je fakticky mini sandbox.

### Jak ověřit, že běží Samba Vault správně

#### 1. Ověř share v smb.conf

Měl by existovat share typu:

```ini
[sftp_mount_user_mountname]
   path = /real/path
   valid users = ...
   read only = no
```

#### 2. Ověř mount

```sh
mount | grep home_sftp_users
```

Měl bys vidět něco jako:

```sh
 //127.0.0.1/sftp_mount_user_main on /home_sftp_users/user/__sftp__/main type cifs (...)
```

Pokud tam není `type cifs`, neběží vault režim.

#### 3. Ověř izolaci

Zkus:

```sh
stat /var/www/realpath/file.txt
stat /home_sftp_users/user/__sftp__/main/file.txt
```

UID/GID a mount info by se měly lišit (CIFS vrstva).

### Kdy Samba Vault dává smysl

Používej ho když:

* dáváš přístup externím subjektům
* je to produkční web
* nechceš, aby SFTP uživatel měl přímý přístup k reálnému FS
* chceš možnost readonly exportu
* chceš logiku řídit přes centrální config

### Kdy stačí bind mount

* interní dev prostředí
* izolovaný server
* malý projekt bez víc uživatelů

### Výkonnostní poznámka

CIFS přes localhost má minimální overhead, ale:

* je to stále síťová vrstva
* není to tak rychlé jako bind mount

Na web deploy nebo běžné SFTP operace je to naprosto v pohodě.
Na miliony malých souborů to bude pomalejší.

### Doporučená bezpečnostní kombinace

Pro produkci:

* sambaVault = true
* rw = false pokud není nutný zápis
* každý mount samostatný share
* žádné sdílení jednoho share mezi víc SFTP usery
* pravidelně kontrolovat smb.conf a mount stav

## Proč to vůbec vzniklo

### 1. Chroot není sandbox

OpenSSH `ChrootDirectory`:

* omezí root adresář procesu
* ale proces běží stále jako daný unixový uživatel
* pracuje nad skutečnými inody

Pokud uděláš:

```sh
bind /var/www/web1 → /home_sftp_users/user/__sftp__/web1
```

tak:

* je to tentýž filesystem
* stejné inode
* stejné ACL
* stejné ownership
* žádná další vrstva

Chroot jen změní pohled, ne realitu.

### 2. Problém s právy při bind mountu

Typický scénář:

* Web běží pod `www-data`
* SFTP uživatel je `zlkl_web`
* Data vlastní `www-data`

Řešení bývá:

* přidat uživatele do group
* nebo změnit group ownership
* nebo 775 práva
* nebo ACL

To znamená:

* otevíráš přístup k reálným datům
* musíš měnit systémová práva
* zasahuješ do produkční logiky

A to je špatně.

## Co Samba Vault řeší

Samba Vault zavádí mezivrstvu.

Namísto:

```txt
SFTP user → reálný FS
```

je:

```txt
SFTP user → CIFS mount → Samba → reálný FS
```

To je architektonicky jiná situace.

## Schéma hrozeb a mitigace

### Hrozba 1: Únik mimo jail

Bind mount:

* uživatel pracuje nad skutečným stromem
* pokud by existovala chyba v chroot nebo jiný lokální exploit, má přímý přístup

Samba Vault:

* mount je síťová vrstva
* pracuješ nad CIFS
* inode nejsou lokální
* žádné přímé filesystem triky

Mitigace:
✔ oddělení namespace
✔ oddělení file handles

### Hrozba 2: Eskalace přes práva

Bind mount:

* musíš upravovat POSIX práva
* často přidáš group write
* tím otevřeš reálná data víc, než chceš

Samba Vault:

* Samba může použít:

  * `force user`
  * `force group`
  * `read only`
  * `create mask`
* mount běží pod řízeným systémovým účtem

Mitigace:
✔ práva pro SFTP uživatele nejsou systémová práva
✔ web může zůstat čistě pod www-data

### Hrozba 3: Náhodné poškození produkčních dat

Bind mount:

* SFTP user zapisuje přímo
* žádná kontrolní vrstva

Samba Vault:

* můžeš dát readonly
* můžeš oddělit upload složku
* můžeš omezit masky

Mitigace:
✔ granularita přístupu
✔ možnost read-only exportu

### Hrozba 4: Více SFTP uživatelů nad jedním FS

Bind mount:

* řešíš to přes group a ACL
* začneš vrstvit práva
* zvyšuješ komplexitu

Samba Vault:

* každý mount je samostatný share
* každý share může mít vlastní pravidla
* izolace mezi SFTP uživateli je silnější

Mitigace:
✔ per-user izolace
✔ oddělené Samba identity

## Proč je force user důležitý

Typický problém:

Web:

```txt
www-data:www-data
```

SFTP user:

```txt
zlkl_web:zlkl_web
```

Bez Samba vrstvy musíš měnit group nebo ACL.

Se Samba:

```txt
force user = www-data
force group = www-data
```

Co to znamená:

* SFTP user si myslí, že zapisuje
* ale Samba přemapuje vlastnictví
* na FS zůstává vše konzistentní

To je klíčový moment.

Neřešíš produkční ownership.
Oddělíš přístup od vlastnictví.

## Co tím reálně mitigujeme

Ne:

* kernel exploit
* root-level kompromitaci
* full LPE

Ano:

✔ chybnou konfiguraci práv
✔ příliš široké group přístupy
✔ náhodné otevření webového stromu
✔ nechtěné zásahy do ownership
✔ chybné ACL kombinace
