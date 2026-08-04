# info pro agenty

## inicializace práce

- Hlavní pracovní vstup a runtime paměť projektu je `dvestezarzlkl/todo_md`, sekce `+SysApp_terminal` v `my_todo.md`.
- Před zahájením každého úkolu načti `todo_md/AGENTS.md`, `todo_md/README.md`, aktuální sekci `+SysApp_terminal` a potom instrukce `AGENTS.md` v tomto repozitáři.
- Pro každý upravovaný soubor zkontroluj také všechny bližší `AGENTS.md` v jeho nadřazených adresářích; lokální instrukce rozšiřují nebo zpřesňují kořenové instrukce.
- Chat není jediná historie práce. Nové bugy, nápady, odskoky, stav řešení a bod návratu zapisuj průběžně do `todo_md` podle jeho instrukcí.
- Hlavní repozitář, `dvestezarzlkl/JBLibs-python` i `dvestezarzlkl/todo_md` používají pro společnou práci cílovou větev `main`.
- Obecně použitelná funkčnost patří do `JBLibs-python`; následně aktualizuj odkaz submodulu `libs/JBLibs` v tomto repozitáři.

## runtime prostředí, lokální data a testy

- Integrační a fyzické testy na cílovém terminálu může provést uživatel. Připrav přesný scénář nebo příkazy, výsledek nepovažuj za fyzicky ověřený, dokud jej uživatel nepotvrdí, a potvrzený výsledek zapiš do `todo_md`.
- `etc_jb_sys_apps` je unixový symlink na živou konfiguraci v systému. Obsah aktuálního `config.ini` nelze odvozovat z GitHubu; pokud je potřeba, vyžádej si od uživatele konkrétní obsah nebo výpis z terminálu.
- `log` je unixový symlink na živý logovací adresář. Aktuální logy nejsou součástí repozitáře a při diagnostice je musí dodat uživatel.
- `venv310` je aktuální Python runtime aplikace a je záměrně ignorovaný Gitem. Změny závislostí řeš přes `requirements.txt`, `setup.sh` a `venv_install_step.py`, ne přímou úpravou obsahu venv.
- Systémové utility potřebné za běhu musí instalovat `setup.sh`. Volitelná funkce nesmí kvůli chybějící utilitě ukončit celou aplikaci už při importu; konkrétní a bezpečnou chybu má vrátit až při použití dané funkce.
- Přenositelné globální konfigurace přidávej jako samostatně verzované handlery v `libs/app/settings_package.py`; handler musí mít export, úplnou validaci/normalizaci, apply bez vlastního `cfg.save()`, seznam měněných config klíčů pro rollback a bezpečný preview bez tajných hodnot.
- Bootstrap `SETTINGS_URL`, `SETTINGS_PASSWORD`, auto-update, lokální revision, SHA-256 a podpis aplikovaných sekcí se nikdy nesmí stát importovatelnou sekcí centrálního balíku. Klient z centrální URL pouze čte a export/upload na URL neimplementuj.
- Obousměrný Hub provider může vedle `hub_collect(context)` nabídnout `hub_apply_remote(updates)`. Provider nedostává DB/SQL a zpětné změny se smějí aplikovat až po úspěšném databázovém commitu.
- `assets/tokens/readme.md` dokumentuje lokální přístupové tokeny. Soubory `assets/tokens/*.cd` jsou ignorované Gitem, obsahují citlivé údaje a nesmí se vypisovat do logu, chatu, diffu ani commitu.
- Plugin systém má čtyři oddělené zdroje stavu: `.gitmodules` pro Git cestu/URL, `pluginy.jsonc` pro katalog a výchozí politiku, `/etc/jb_sys_apps/plugins.jsonc` pro lokální enable/disable a `assets/tokens/<id>.cd` pro přístup. Formát a postupy udržuj v `docs/plugin-system.md`; token nikdy nesmí implicitně přebít lokální `enabled: false`.
- Obrázky vložené do Markdown dokumentů přes VSCode Office Viewer se ukládají relativně jako `image/<nazev_md>/resources.*`; tuto strukturu zachovej při úpravách dokumentace.

## GitHub konektor a malé změny ve velkých souborech

- GitHub konektor při přímé úpravě existujícího souboru vyžaduje kompletní nový obsah. Nepřepisuj proto velký soubor z neúplného nebo zkráceného výpisu.
- Pro malé změny ve velkých souborech použij `.github/scripts/apply_repo_changes.py`, `.github/workflows/apply-repo-patch.yml` a JSON manifest v `.github/changes/`.
- Vytvoř větev `automation/<nazev>` z aktuálního `main`, přidej manifest a otevři draft PR do `main`. Workflow ověří přesné výskyty, zachová LF/CRLF, provede náhrady, odstraní manifest a commitne výsledek do stejné větve.
- Po proběhnutí Actions zkontroluj výsledný diff a teprve potom PR sluč.
- Manifest používá `version`, `commit_message` a pole `replacements`; každá náhrada obsahuje `path`, přesné `old`, `new` a obvykle `expected: 1`.

## changelog

Po každé změně kódu je potřeba aktualizovat `changelog.md` v poslední verzi na začátku. Changelog je řazen nejnovější verzí nahoře.

## verze

- Větší změna, která patří pouze do hlavní aplikace `sys_apps` / hlavního menu a není samostatnou změnou pluginu ani JBLibs, má běžně zvýšit verzi hlavní aplikace.
- Kompatibilní oprava nebo menší provozní změna používá patch verzi; větší nová funkce hlavní aplikace minor verzi; nekompatibilní nebo zásadní architektonická změna major verzi.
- Drobné změny uvnitř právě rozpracované a dosud nevydané verze nemusí zakládat další verzi, ale musí být uvedené v jejím changelogu.
- Hlavní verze je uvedená v `changelog.md`, `libs/app/cfg.py` a badge v `readme.md`. Všechny tři hodnoty musí být stejné, jinak může vzniknout problém při update.
- Verze pluginů a JBLibs se spravují samostatně; jejich změna sama o sobě automaticky neznamená zvýšení hlavní verze, pokud nejde zároveň o větší uživatelskou změnu `sys_apps`.

## verze knihoven

pokud má scritp v sobě někde na začátku `version` nebo `__VERSION__` tak je potřeba aktualizovat i tuto verzi, changelog by měl mít stejný název jako je název souboru s knihovnou, pokud neexistuje tak jej vytvoříme`

## aplikace

Aplikace i pomocná výběrová menu jsou založená na `c_menu`. Hlavním prostorem pro menu a podaplikace je `libs/app/menus`.

`libs/app/menus/menuBoss.py` obsahuje hlavní dynamickou menu class. Vyhledává podadresáře začínající `app_`; pokud podadresář obsahuje správně definovaný `menu.py`, načte jej jako položku hlavního menu.

`libs/app/menus/menu.md` je dokumentace struktury a funkcí menu, nikoliv hlavní wrapper nebo hlavní menu class.

Pokud během vývoje vznikne potřeba samostatného nástroje nebo rozsáhlejšího submenu, navrhni jej jako novou podaplikaci, zapiš úkol do `todo_md` a vytvoř nový adresář `libs/app/menus/app_<poradi>_<nazev>` se souborem `menu.py`.

Aktuální podaplikace zahrnují mimo jiné UART tester, SSH manager, SFTP manager, Node-RED instance manager a self-updater.

## struktura

- sys_app je název a vstupní bod do app
- libs je složka s knihovnami, které jsou volány z app a z jednotlivých instancí
  - libs/app je hlavní knihovna pro tuto app
    - libs/app/menus je složka s menu pro app, jednotlivá menu nemusí být jen menu jako takové, ale mohou tvořit vlastní celou podaplikaci
- libs/JBLibs jsou vlastní knihovny - takový malý framework
  - libs/JBLibs/c_menu je hlavní knihovna a class pro práci s menu
  - libs/JBLibs/term.py je knihovna pro práci s terminálem, print, klávesový vstup, barevný výpis, atd.
  - libs/JBLibs/input.py je knihovna pro práci s klávesovým vstupem, čtení znaků, atd., confirm, select z voleb, selectDir, selectFile atd.
  - libs/JBLibs/fs_utils.py je knihovna pro práci se souborovým systémem, čtení, zápis, rozložení disku a jiné fs příkazy, atd.
  - libs/JBLibs/fs_swap.py je knihovna pro práci s swapem, zjištění velikosti, zapnutí/vypnutí, atd., tvorba atp
  - libs/JBLibs/systemdService.py je knihovna pro práci se systemd service, tvorba, editace, restart, status, atd. v jedné class s info classy, včetně timerů
  - libs/JBLibs/format.py je knihovna pro formátování textu, jako převod na jednotky kB, datetime, řešeno přes class pro daný formát
  - libs/JBLibs/jbjh.py je knihovna s pomocnými funkcemi pro různé účely, převážně pro validaci a normalizaci hodnot, např. is_int, is_float, is_bool, atd. víc viz libs/JBLibs/jbjh.md
  - libs/JBLibs/git.py je knihovna pro práci s git repozitářem, zjištění stavu, update z gitu atp
  - libs/JBLibs/sftp je knihovna pro práci s SFTP konfigurací v systému, jako uživatelé přístup, certifikáty userů, mountpointy přes sambu (sandboxy) atd.
  - libs/JBLibs/sftp/ssh.py je knihovna pro práci se SSHD démonem a pomocné funkce jako generování certifikátů a jiná správa SSHD
- `libs/app/cfg.py` je runtime konfigurace celé aplikace načtená z `config.ini`; je to jiný kontext než `libs/app/c_cfg.py`, které patří k dynamické konfiguraci node-red instancí.
- Aplikační nastavení patří do hlavního `menuBoss.py` a ukládá se do globálního `config.ini`; zahrnuje `SERVER_URL` i mailing a malé související submenu klidně nech v jednom `menu.py`, pokud není rozsáhlé.
- `libs/app/cfg.py` má mít jednoduché `load()` a `save()` wrappery; `save()` je nová nadstavba nad dříve read-only app configem a interně používá sdílený helper v `libs/JBLibs/helper.py`.
- Pro nápovědu ve vstupních polích používej `get_input(..., titleNote=...)`, klidně s víc řádky přes `\n`; nepřidávej kvůli tomu nový prompt helper, pokud už to stačí.
- U SMTP měj režim a port svázané dohromady; výchozí porty jsou `plain=25`, `starttls=587`, `ssl=465` a port `993` je obvykle IMAPS, ne SMTP.
- V mailovém submenu používej ESC jako návrat a neschovávej to za vlastní `b` back položku.
- `SERVER_URL` je aplikační adresa bez portu; v menu je lepší nabídnout FQDN, lokální IPv4 a ruční zadání.
- Záhlaví menu skládaj přes `c_menu_block_items` podobně jako `appHelper._setAppHeader`: jeden titulkový řádek a samostatné stavové řádky přes `append(("label", "value"))`, ne mix všeho do jediné hlavičky.
- Pokud submenu má jen pár souvisejících akcí nebo vlastních podsubmenu, nech je klidně v jednom `menu.py`; rozděluj až ve chvíli, kdy už je to fakt větší nebo sdílené napříč více místy.
