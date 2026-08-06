# Jednorázová změna PTUUID systémového disku

Disk Manager umožňuje u živého systémového GPT disku připravit změnu diskového GUID pro příští restart. Funkce je určená hlavně pro vzdálené stroje vytvořené klonováním image, které už mají unikátní Machine ID, ale stále sdílejí stejné PTUUID.

## Bezpečnostní hranice

- Za běhu systému se GPT systémového disku nemění.
- Přímá akce `Vygeneruj nové ID disku` zůstává pro systémový disk zakázaná.
- U systémového disku je dostupná pouze akce `Připravit nové PTUUID při restartu`.
- Příprava vyžaduje potvrzení Y/N a následně přesné opsání celého nového PTUUID.
- Initramfs používá výhradně `sgdisk --disk-guid=<uuid>`; nepoužívá `--randomize-guids` ani `--partition-guid`.
- Chyba validace v initramfs nesmí zastavit boot. Změna se přeskočí a systém pokračuje se stávajícím GPT.

## Příprava

Před vytvořením initramfs payloadu se ověří:

1. vybrané zařízení je živý systémový disk typu `disk`,
2. disk používá platné GPT UUID,
3. aktuální PTUUID odpovídá hodnotě z Disk Manageru,
4. velikost zařízení je čitelná,
5. jsou dostupná PARTUUID partition,
6. `sgdisk --verify` nehlásí chybu.

Do `/etc/jb_sys_apps/ptuuid-change/` se uloží:

- `pending.json` s očekávaným stavem,
- `pending.env` pro initramfs,
- `layout-before-change.gpt` jako záloha GPT,
- po dokončení také `last-result.json`.

Obecný hook a boot script se instalují do `/etc/initramfs-tools/`. Hook vloží pending stav a potřebné binárky do initramfs a následně se spustí `update-initramfs -u`.

## Časný boot

Skript v `local-premount` běží po nalezení a kontrole root zařízení, ale před připojením root filesystemu. Znovu ověří:

- cestu zařízení,
- původní PTUUID,
- velikost disku,
- konzistenci GPT.

Pokud vše souhlasí, zapíše pouze nové GPT disk GUID. Jakákoli odchylka způsobí přeskočení změny a boot pokračuje.

## Kontrola po bootu

`sysapps-ptuuid-finalize.service` ověří:

- nové PTUUID,
- nezměněnou velikost disku,
- přesnou shodu všech uložených PARTUUID,
- platnou GPT po změně.

Při úspěchu převede lokální uživatelský název disku ze starého PTUUID na nové a spustí best-effort synchronizaci Disk Hub provideru. Pending payload se odstraní a initramfs se znovu vytvoří bez jednorázového stavu.

## Zrušení před restartem

Disk Manager nabídne `Zrušit připravenou změnu PTUUID`. Nejprve vloží do initramfs deaktivovaný payload, znovu vytvoří initramfs a teprve potom odstraní lokální pending soubory. Uživatel tedy nedostane potvrzení o zrušení, pokud nebyla deaktivace úspěšně zapsaná do initramfs.

## Nouzová obnova

Záloha `layout-before-change.gpt` je určená pro ruční obnovu z rescue systému nebo po připojení disku k jinému stroji. Obnova GPT je destruktivní servisní zásah a Disk Manager ji automaticky nespouští.
