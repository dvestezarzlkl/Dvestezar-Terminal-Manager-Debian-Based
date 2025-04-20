# Dvestezar Terminal Manager - Debian Based
<!-- cspell:ignore submoduly,submodul,symlinku,pipx,venv,pipreqs,ensurepath,pushurl,utilitku,standartní -->

v1.4.0

[ENG](readme_en.md)

[Náhled](preview_v1-3-1.mp4)

## Popis aplikace

Dvestezar Terminal Manager je nástroj pro správu systémů založených na Debianu, jako jsou Ubuntu, Raspbian, OrangePi a další distribuce. Poskytuje jednoduché menu pro ovládání různých funkcí systému přímo z terminálu.

Tento nástroj je navržen jako modulární framework, který lze snadno rozšiřovat o nové podaplikace a funkce podle potřeb. 

**Aktuální funkce aplikace:**

1. **User Management:**
   - Správa uživatelů systému včetně přidávání, mazání a nastavování hesel.
   - Generování a správa SSH klíčů s automatickým ukládáním do `authorized_keys`.
   - Správa přístupu uživatelů k sudo.

2. **Node-RED Instance Manager:**
   - Vytváření, editace, zálohování a mazání instancí Node-RED.
   - Správa šablon pro rychlé nasazení nových instancí.
   - Automatická kontrola a konfigurace služeb pro každou instanci.

### Výzva k rozšíření

Aplikace je připravena na rozšiřování o další moduly a podaplikace. Pokud máš nápad na novou funkcionalitu nebo chceš přidat podporu pro specifickou službu, jsi vítán!

Každý nový modul může být jednoduše přidán jako nová podaplikace do adresáře `libs/app/menus/<app_dir>`. Tato struktura umožňuje snadnou integraci do hlavního menu a přehlednou správu kódu.

## Popis vytváření menu aplikací

Hlavní menu se vytváří tak, že projde `libs/app/menus/<app_dir>` kde `app_dir` je adresář aplikace, který musí obsahovat`:
- `menu.py` tento soubor musí obsahovat:
  - property `_MENU_NAME_` které obsahuje text zobrazený pro volbu v hlavním neu
  - class `menu` které bude z hlavního menu voláno jako výchozí menu aplikace

### Node-Red Instance Control

**Node-Red Instance Control** je nástroj pro správu instancí Node-RED, který umožňuje konfigurovat a spravovat jednotlivé instance na serveru. Aplikace poskytuje uživatelsky přívětivé menu přímo v terminálu, které vám umožní snadno provádět různé úkony, jako je vytváření, úprava, zálohování a mazání instancí Node-RED. Tento nástroj je určen zejména pro efektivní správu instancí v multi-uživatelském prostředí, kde každý uživatel může mít svou vlastní instanci Node-RED.

#### Hlavní funkce aplikace:

1. **Nastavení nových instancí a jejich úprava**:
   - Možnost vytvoření nové instance Node-RED pro konkrétního systémového uživatele.
     - Instalace z čistého Node-Red z aktuální repo verze
     - Instalace ze 7z archivu, tyto archivy musí být v adresáři `/var/node-red-install-instances`, pokud jsou nalezené 7z soubory tak jsou nabídnuty při nové instalaci, obsah archivu viz níže
   - Úprava stávajících instancí, včetně změny názvu, hesla, portu nebo typu instalace (např. čistá instalace nebo instalace z archivu).
   - Nastavení služby na čtení nebo plný přístup.

2. **Správa služeb Node-RED**:
   - Spuštění, zastavení a zakázání služby Node-RED.
   - Možnost ověřit stav služby pro konkrétního uživatele.

3. **Zálohování a obnovení**:
   - Automatické zálohování všech instancí nebo jednotlivých instancí Node-RED.
   - Vytvoření zálohy aktuální konfigurace a uživatelských dat.

4. **Šablony služeb**:
   - Možnost vytvoření šablony služby Node-RED, která slouží jako výchozí pro nové instance.
   - Odinstalace či odstranění šablon služby.

5. **Správa uživatelů**:
   - Přidání nového uživatele.
   - Nastavení a úprava uživatelského přístupu do Node-RED Dashboard-u.
   - Možnost nastavit uživatele na režim pouze pro čtení nebo plný přístup.
  
#### Archiv pro instalaci

Jak bylo zmíněno, zipy 7z musí být v `/var/node-red-install-instances`, tyto jsou potom nabídnuty při nové instalaci. Podporovány jsou jen přípony `7z`. Zabalené musí být viz níže, jinak není zaručena funkčnost nebo dokonce poškození dat instancí nebo dokonce systému.

Archiv pro instance lze vytvořit tak že zazálohujeme nějakou instanci a tento zip použijeme takto:

1. root adresář zipu přejmenujeme ze jména uživatele, ze kterého byla záloha udělána na `defaultNodeInstance`
2. promažeme obsah tohoto adresáře, ponecháme jen adresář `.node-red` a `node_instance`, pokud jsou nějaké i skryté soubory v tomto root-u tak je smažeme  
   Základní vzhled tří úrovní, samozřejmě bude mít více úrovní. Jde hlavně o první a druhou úroveň, tj root `defaultNodeInstance` a jeho podadresáře `.node-red` a `node_instance`.

   ```txt
   defaultNodeInstance
    |   
    +---.node-red
    |   |   soubory.*
    |   |   
    |   +---adresáře
    |   +---např
    |   +---lib
    |   |   \---flows
    |   +---node_modules
    |   \---projects
    \---node_instance
        |   package-lock.json
        |   package.json
        |   
        \---node_modules
   ```

#### Menu a ovládání

- **Hlavní menu** nabízí přehled o konfiguraci, jako je URL serveru, adresáře pro zálohy, dočasné adresáře a výchozí instance. Můžete zde provést akce, jako je vytváření nebo úprava instancí, zálohování, nebo vytvoření šablony.
- **Editační menu** umožňuje detailně konfigurovat konkrétní instance – měnit porty, názvy, přístupy a další parametry.
- **Uživatelské menu** poskytuje možnosti pro přidávání uživatelů, nastavení přístupů, a správu jednotlivých uživatelských profilů.

#### Typ instalace

- **Fresh**: Čistá instalace z repozitáře, vhodná pro nové uživatele nebo vytvoření zcela nové instance.
- **Copy**: Instalace z existujícího archivu, která umožňuje rychlé obnovení nebo klonování předchozí konfigurace.

#### Další vlastnosti

- **Bezpečnost a přístup**: Uživatelé mohou být nastaveni s úrovněmi oprávnění "full" a "pouze pro čtení", což je vhodné pro auditní nebo kontrolní účely.

Tento nástroj zjednodušuje správu více instancí Node-RED v jednom prostředí a nabízí flexibilitu při správě jednotlivých uživatelů, což zajišťuje efektivitu a konzistenci v provozu. 

### SSH Groups manager

Manager spravuje certifikáty ssh SSH pro připojení k terminálu, ale lze využít jakkoliv.

Je určeno hlavně pro správce serveru. Např správa instancí např node-red, kde vytvoříme instanci a na ni pak vytvoříme SSH klíč pro uživatele, který se může připojit pro debug node-red

Spravuje přímo soubor uživatelů `authorized_keys`

- Spravovat uživatele systému:
    - vytvořit uživatele systému
    - nastavit heslo uživatele systému
    - smazat uživatele systému, nejdřív je ale provedena záloha home adresáře uživatele a po úspěchu je uživatel kompletně smazán ze systému vč. dat home adresáře.
    - spravovat sudo práva uživatele
    - spravovat dialout skupinu uživatele
- v home uživatele vytvoří v `~/.ssh/sshManager` kde ukládá generované klíče
- generované klíče může:
    - generovat ssh klíč pro uživatele
    - přidat veřejný klíč do `authorized_keys`
    - odstranit veřejný klíč z `authorized_keys`
    - zobrazit privátní klíč pro předání uživateli

## Hlavní soubor/y


### `run.sh`

Spouštíme pomocí `run.sh` - spouští aplikaci


### `setup.sh`

Je tu ještě jeden soubor a to `setup.py` který se spouští při prvním spuštění a instaluje potřebné programy, knihovny, submoduly a další související věci vč. **node.js**, **zip** a knihoven potřebných pro aplikaci.

Tento soubor vytváří virtual env pro python 3.10 `venv310` a do něj instaluje potřebné knihovny podle `requirements.txt`

!!! Tento soubor je potřeba spustit jako root nebo se sudo právy.

!!! Pozor node se instaluje globálně do systému a z repo ve verzi 22.x - pokud nechceme tak se musíme postarat o instalaci node ručně aby v době spuštění setup.sh byl node dostupný. !!!

Nakonec pokud neexistuje tak vytvoří symlink pro `sys_apps.sh` do `bin` adresáře, aby bylo možné spouštět aplikaci z terminálu bez nutnosti přepínat se do adresáře aplikace.

### `update_from_git.sh`

Poslední 'méně' hlavním souborem je `update_from_git.sh` který aktualizuje lokální repo podle aktuálního stavu na GITu. Pokud tu budeme mít nějaké změny tak budou anulovány.  
Script kontroluje jestli je repo v módu readonly, pokud není tak se nespustí a zobrazí hlášení o nutnosti přepnutí do readonly.  
Toto lze provést příkazem z terminálu

```sh
git config remote.origin.pushurl no_push
```

## Requires

Co je potřeba ke spuštění

### Soubory


**Nutné pro běh:**

- `config.ini` je potřeba vytvořit před prvním spuštěním podle `cfg.py` v root aplikace, tzn kde je `!run.py`  
  Příklad:
  ```ini
   [globals]
   LANGUAGE                = "cs-CZ"
   SERVER_URL              = "moje.domena.real"
   DEFAULT_NODE_ARCHIVE    = "/home/defaultNodeInstance.7z"
   DEFAULT_JS_CONFIG       = "muj-node-config.default.js"
   TEMP_DIRECTORY          = "/tmp/default_node"
   BACKUP_DIRECTORY        = "/var/backups"
   MIN_WIDTH               = 60

   # Pokud vynecháme bude ssl vypnuto, viz default hodnoty v cfg.py
   # vynecháme zakomentováním nebo nastavením na null None
   # httpsKey = '/root/.acme.sh/moje.domena.real/moje.domena.real.key'
   # httpsCert = '/root/.acme.sh/moje.domena.real/fullchain.cer'

  ```

**Doporučené:**

- `/home/defaultNodeInstance.7z` výchozí zabalený adresář s instancí, (není povinné)  
  Tento soubor může obsahovat kompletní instanci node-red v dané verzi, nainstalovanými moduly a základní flow  
  Uvnitř musí být jako root dir adresář se jménem `defaultNodeInstance` a v něm je vpodstatě zabalený (jen potřebný obsah) home uživatelského adresáře  
  ![root](image/readme/Screenshot_11.jpg)  
  ![root](image/readme/Screenshot_10.jpg)  

### Systém

Testováno na Ubuntu 22+

### Python

Testováno na python 3.10+ - virtual env
- python3.10-venv
- python3.10-pip
- python3.10-dev

### Python knihovny

Viz [soubor - requirements.txt](requirements.txt)

Lze instalovat pomocí souboru 'requirements.txt' pomocí příkazu

```sh
pip install -r requirements.txt
```

Pozor, musíme být ve virtual env

### Aplikace z apt

**7zip:**

```sh
apt install p7zip-full
```

**Node.js:**

Pro bezproblémovou funkčnost musí být node.js instalován globálně, pro aktuální LTS 22 je to takto:

Provádíme pod sudo nebo se sudo příkazem

```sh
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt-get install -y nodejs
```


### Submoduly

Tato app používá submodul 'JBLibs-python', takže po naklonování tohoto repo je potřeba:

```sh
git submodule update --init --recursive
```

Nebo přímé přidání, pokud by nic se submoduly nefungovalo

```sh
git submodule add -b <branch> https://github.com/dvestezarzlkl/JBLibs-python.git libs/JBLibs
```

## Soubory v root adresáři

### `run.sh`

Hlavní soubor kterým se app spouští viz [výše](#runpy)

Tento soubor vytváří soubor `setup.sh` na konci běhu.

### `sys_apps.sh`

Soubor kterým lze spustit `run.sh` z linku.

**Př. globální spuštění bez modifikace PATH:**

Vytvoříme link do `/usr/local/bin` a v systému pak stačí napsat kdekoliv `sys_app.sh` nebo jiný název podle názvu symlinku.

např:

```sh
ln -s /cesta/k/tvemu_skriptu/sys_apps.sh /usr/local/bin/sys_apps
```

Toto vytvoří symlink pro příkaz `sys_apps` který lze potom odkudkoliv spustit.

### `setup.sh`

Instaluje potřebné programy, knihovny, submoduly a další související věci vč. **node.js**, **zip** a knihoven potřebných pro aplikaci. Jak bylo uvedeno výše.

### `rq.sh`

Generuje requirements.txt, knihovny které nejsou standartní součástí pythonu

**Soubor:**

- `requirements.txt` obsahuje seznam potřebných knihoven, které můžeme doinstalovat
  - `pip install -r requirements.txt` pro venv
- `rq.log` - poslední log i verzí pythonu pro které bylo generováno

#### Co potřebuje

utilitku `pipreqs`

Pokud máme např čistý ubuntu server kde je python3, a chceme nainstalovat globálně, kde nefunguje pip kvůli externí správě (apt), tak budeme potřebovat `pipx`

Ve virtual env je to jednoduché, stačí mít nainstalovaný pip a pipreqs
Pokud nemáme nainstalovaný pip tak je potřeba ho nainstalovat, např. na ubuntu serveru:

```sh
apt install python3-pip
```

Pokud nemáme nainstalovaný pipreqs tak je potřeba ho nainstalovat, např. na ubuntu serveru:

```sh
pipx install pipreqs

# čteme info co zobrazí a popřípadě, pokud potřebujeme tak nainstalujeme

pipx ensurepath

```

**PO TOMTO KROKU je nutné restartovat terminál !!!!**

Pokud chceme instalovat v prostředí venv tak postup je viz. venv prostředí.

### `update_from_git.sh`

!!! Script má základní ochranu na test přepnutí lokálního repo do readonly, pokud není provedeno, script se nespustí !!!

!!! Script může zrušit nebo přepsat lokální změny v případě ručních změn v readonly módu !!!

Aktualizuje lokální repo podle aktuálního stavu na GITu. Pokud tu budeme mít nějaké změny tak budou anulovány.

**Přepnutí do readonly:**

Lokální repo přepneme do readonly pomocí příkazu z terminálu

```sh
git config remote.origin.pushurl no_push
```

### `makeRelease.py`

Zabalí tento adresář do ZIP jen se soubory a adresáři, které jsou potřeba a výsledný soubor uloží do podadresáře `release`.

Adresář `release` nebude součástí ZIP a je v `gitignore`

### logy, __pycache__

Tyto nebudou součástí `release` a  jsou v `gitignore`

## Práva souborů

Spustitelné soubor musí mít samozřejmě práva pro spuštění

Např. pro základní skripty

```sh
chmod +x 'run.sh' 'sys_apps.sh'
```

## Aktivace venv

Pokud jsme prošli instalací a máme nainstalovaný python3.10 a venv, tak je pro terminál potřeba aktivovat venv

```sh
source venv310/bin/activate
```

Zrušení venv je jednouše

```sh
deactivate
```

