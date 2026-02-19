# Serial tester pro RS-485 (UART převodníky) – návod

Pokud znáš ***iperf***, tak tohle je v podstatě podobný typ nástroje, jen místo TCP/UDP testuje UART (a cokoliv na něj připojené), typicky třeba RS-485 převodníky.

Tento skript slouží jako jednoduchý “ping” test RS-485 linky: jedna strana posílá zprávu `test_...`, druhá strana odpoví `resp_..._<hash>`. Odesílatel ověří, že se vrátil stejný payload a že sedí hash (SHA-256 zkrácený na 128 bitů).

Verze skriptu: 1.3.0  
Výchozí rychlost: 19200 baud  
Timeout na odpověď: 2 s

## Co test ověřuje

1. Že data projdou jedním směrem (Sender → Receiver).
2. Že odpověď projde zpět (Receiver → Sender).
3. Že se data cestou nezměnila (kontrola obsahem + hash).
4. Že převodník/RS-485 směr/DE-RE není “rozbitý” (timeouty a chyby hashů).

Poznámka: Samotný hash tady není šifrování, jen rychlá kontrola integrity.

## Požadavky

- Python 3
- Knihovna `pyserial`

Instalace:

```bash
pip install pyserial
````

Historie příkazů v konzoli (nepovinné):

```bash
pip install pyreadline3
```

Skript si ukládá historii do:

- Linux: `~/.serial_sender_history`
- Windows: typicky také do profilu uživatele (přes `~`)

## Zapojení a topologie

Typické scénáře:

### 1) Dva převodníky RS-485 ↔ USB (nebo UART)

- PC1 spustí Receiver
- PC2 spustí Sender
- A/B (D+ / D-) propojit křížem konzistentně (A na A, B na B)
- Na sběrnici doporučeně terminace 120 Ω na koncích (podle délky a rychlosti)

### 2) Jeden PC + dvě sériové rozhraní

- Na jednom PC můžeš mít dvě USB-RS485 “COM” zařízení a spustit:
  - Receiver na jednom portu
  - Sender na druhém portu
- Pozor: oba porty musí být fyzicky propojené po RS-485 (A/B).

## Základní spuštění

Skript má dva režimy:

- Sender (výchozí)
- Receiver (`-r` / `--receiver`)

### Linux příklady

Vylistování portů (orientačně):

```bash
ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

Receiver:

```bash
python3 serial_tester.py /dev/ttyUSB0 -b 19200 -r
```

Sender:

```bash
python3 serial_tester.py /dev/ttyUSB1 -b 19200
```

### Windows příklady

Receiver:

```powershell
python serial_tester.py COM5 -b 19200 -r
```

Sender:

```powershell
python serial_tester.py COM6 -b 19200
```

## Ovládání v režimu Sender

Po spuštění Senderu se objeví hlavička a čeká se na příkazy.

### Dostupné příkazy

- `test`
  Odešle testovací payload délky 64 znaků (default), 1×
- `test120`
  Odešle payload 120 znaků, 1×
- `test80n5`
  Odešle 80 znaků a opakuje 5×
- `testn3`
  Odešle 64 znaků a opakuje 3×
- `rcv`
  Přepne do receiver režimu (na stejném portu)
- `cls`
  Vyčistí obrazovku a znovu vytiskne hlavičku
- `help`
  Vypíše nápovědu
- `exit`
  Ukončí skript

Syntaxe testu:

- `test[<len>][n<repeat>]`
- `<len>`: 1 až 1024
- `<repeat>`: 1 až 100

## Co uvidíš na výstupu

### Sender – odeslání a vyhodnocení

Příklad:

- `[SEND  1] bytes: 90 (hash: ...)`
- `[OK    1] Hash i obsah odpovídá.`

Možné výsledky:

- `OK`
  Payload i hash sedí.
- `FAIL Hash OK - CHYBA obsahu`
  Hash sedí, ale payload nesedí (většinou chyba parsování/prohození částí, nebo někde po cestě dochází k úpravě obsahu a zároveň se přepočítal hash – u tohoto receiveru prakticky ne, pokud neběží jiný).
- `FAIL Hash CHYBA ... != ...`
  Data se změnila po cestě (rušení, špatné nastavení parity/baud, špatný převodník, half-duplex směr, kolize na lince).
- `TIMEOUT`
  Receiver neodpověděl do 2 s (není spuštěn, špatný port, špatné zapojení A/B, špatný směr DE/RE, špatná rychlost, linka je umlčená).

### Receiver – příjem a odpověď

Receiver vypisuje:

- kolik bajtů přijal (`[IN ] bytes received: ...`)
- kolik bajtů poslal (`[OUT] bytes sent: ...`)
- a hash, který k payloadu spočítal

Receiver reaguje pouze na řádky začínající `test_`. Ostatní vypíše jen jako text.

## Doporučený postup testování (prakticky)

1. Spusť Receiver na jednom konci.
2. Spusť Sender na druhém konci.
3. Dej `test` (64 znaků). Musí padat `OK`.
4. Dej delší zprávu, třeba `test256n10`.
5. Pokud jsou chyby:

   - ověř, že oba konce mají stejný baudrate
   - ověř, že A/B nejsou prohozené (někdy výrobce značí A/B opačně)
   - zkus přidat terminaci 120 Ω (nebo ji naopak odpojit, pokud je všude a přetěžuje sběrnici)
   - zkrať kabel, nebo sniž baudrate (např. 9600)
   - ověř společnou zem (GND), hlavně u UART ↔ RS-485 modulů

## Poznámky k protokolu a formátu

### Formát zprávy Sender → Receiver

Sender posílá:

- `test_~<payload><attempt>~`

`attempt` je pořadové číslo opakování (1..repeat) přilepené do payloadu, aby se testy lišily.

### Formát odpovědi Receiver → Sender

Receiver odpoví:

- `resp_~<payload><attempt>~_<hash>`

Kde `<hash>` je prvních 32 hex znaků SHA-256 z payloadu (tj. 128 bitů v hex).

---

## Troubleshooting

### 1) Samé TIMEOUT

- Na druhé straně neběží Receiver (nebo špatný port).
- RS-485 převodník neotáčí směr (DE/RE).
- Prohozené A/B.
- Špatný baudrate (nebo parita/stop bity, pokud je mění hardware – skript používá default nastavení pyserialu).

### 2) FAIL – Hash CHYBA

- Rušení na lince, dlouhý kabel, špatná terminace.
- Nesedí rychlost.
- Kolize na sběrnici (víc zařízení mluví naráz).
- Převodník dělá nějakou transformaci (typicky ne, ale stát se může u “divných” modulů).

### 3) Občas OK, občas fail

- Hraniční linka: terminace, biasing, rušení, kabeláž, zemnění.
- Zkus snížit baudrate nebo zkrátit délku.

## Do budoucna

- Přidat volbu pro timeout (`--timeout`).
- Přidat volbu pro délku pauzy mezi zprávami.
- Přidat logování do souboru (CSV) pro hromadné porovnání převodníků.
- Přidat statistiku (počet OK/FAIL/TIMEOUT na konci testu).
