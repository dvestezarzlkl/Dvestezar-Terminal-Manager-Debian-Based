# info pro agenty

## changelog

Po každé změně kódu je potřeba aktualizovat changelog.md v poslední verzi na začátku, verzi neměníme pokud není přímo řečeno, třeba s pushem změn.

changelog je řazen nejnovější verze nahoře, takže při updatu je potřeba zkontrolovat jestli je verze v changelogu stejná jako v libs/app/cfg.py a readme.md, pokud ne tak je potřeba aktualizovat všechny tři verze na stejnou.

## verze

hlavní app verze je v changelog a na to je navázána verze v libs/app/cfg.py a samozřejmě v readme.md, kde je verze v badge. Všechny tři verze musí být stejné, jinak to může způsobit problémy při update.

## verze knihoven

pokud má scritp v sobě někde na začátku `version` nebo `__VERSION__` tak je potřeba aktualizovat i tuto verzi, changelog by měl mít stejný název jako je název souboru s knihovnou, pokud neexistuje tak jej vytvoříme`

## aplikace

je založená komplet na `c_menu` kde má aplikace jedno výchozí menu a z něj se volí jednotlivé podmenu (podaplikace), menu jsou dynamická, hlavně vstupní menu je dynamické a vytváří se vvlastní položky do podaplikací/submenu podle toho co je v app/libs/app/menus, v tomto adresáři jsou jednotlivé subadresáře jako subaplikace které když obashuje menu.py a má správný formát a proměnné je načteno do hlavního bossMenu

víc přímo v `libs/app/menus/menu.md` kde je popis i vlastní hlavičky menu atp

## struktura

- sys_app je název a vstupní bod do app
- libs je složka s knihovnami, které jsou volány z app a z jednotlivých instancí
  - libs/app je hlavní knihovna pro tuto app
    - libs/app/menus je složka s menu pro app, jednotlivá měnu nemusí být jen menu jako takové ale může tvoři vlastní celou podaplikaci
- libs/JBLibs jsou vlastní knihovny - takový malý framework
  - libs/JBLibs/c_menu je hlavní knihovna a class pro právi s menu
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
- Mailing konfigurace patří do hlavního `menuBoss.py` a ukládá se do globálního `config.ini`; malé související submenu klidně nech v jednom `menu.py`, pokud není rozsáhlé.
- `libs/app/cfg.py` má mít jednoduché `load()` a `save()` wrappery; `save()` je nová nadstavba nad dříve read-only app configem a interně používá sdílený helper v `libs/JBLibs/helper.py`.
- Pokud submenu má jen pár souvisejících akcí nebo vlastních podsubmenu, nech je klidně v jednom `menu.py`; rozděluj až ve chvíli, kdy už je to fakt větší nebo sdílené napříč více místy.
