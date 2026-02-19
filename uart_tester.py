#!/usr/bin/env python3
import sys
import serial
import hashlib
import re
import time
import argparse
import atexit
import os
import types

try:
    import readline
except ImportError:
    try:
        import pyreadline as readline
    except ImportError:
        readline = None  # fallback, historie nebude

version = '1.3.0'
DEFAULT_BAUDRATE = 19200
DEFAULT_TEST_LEN = 64
TIMEOUT = 2  # vteřiny pro čekání na odpověď
HISTORY_FILE = os.path.expanduser("~/.serial_sender_history")

"""
Pro win   : pip install pyreadline3
Pro linux : pip install pyreadline3
"""

if readline:
    # Načtení historie příkazů
    try:
        readline.read_history_file(HISTORY_FILE)
    except FileNotFoundError:
        pass
    readline.set_history_length(50)
    atexit.register(readline.write_history_file, HISTORY_FILE)

def get_hash128(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]

def generate_test_text(length: int) -> str:
    base = "Nejobdelavatelnejsi-se-vse-obdelavatelnych-1234567890-"
    return (base * ((length // len(base)) + 1))[:length]

def parse_command(line):
    match = re.match(r'^test(?P<len>\d+)?(?:n(?P<rep>\d+))?$', line.strip().lower())
    if match:
        length = int(match.group("len")) if match.group("len") else DEFAULT_TEST_LEN
        repeat = int(match.group("rep")) if match.group("rep") else 1
        return length, repeat
    return None, None

def send_and_wait_for_response(ser:serial , payload:str, attempt: int) -> bool:
    """Odešle zprávu a čeká na odpověď.

    Args:
        ser (serial): serial port
        payload (str): co se má odeslat, k tomuto se přidává časové razítko a iterace
        attempt (int): pořadové číslo pokusu

    Returns:
        bool: True pokud byla odpověď OK, jinak False
    """
    payload = '~' + payload + str(attempt) + '~'
    full_msg = "test_" + payload
    expected_hash = get_hash128(payload)

    ser.write((full_msg + "\r\n").encode())
    ser.flush()
    ln=len(full_msg)
    
    # attempt zarovnáme na 3 znaky
    attempt = str(attempt).rjust(3)
    
    print(f"[SEND {attempt}] bytes: {ln} (hash: {expected_hash})",end='     ')

    start_time = time.time()
    while time.time() - start_time < TIMEOUT:
        line = ser.readline().decode(errors="replace").strip()
        if not line:
            continue

        if line.startswith("resp_"):
            try:
                content = line[5:]
                data, received_hash = content.rsplit("_", 1)
                computed_hash = get_hash128(data)

                if received_hash == computed_hash:
                    if data == payload:
                        print(f"[OK   {attempt}] Hash i obsah odpovídá.")
                        return True
                    else:
                        print(f"[FAIL {attempt}] Hash OK - CHYBA obsahu.")
                        return False
                else:
                    print(f"[FAIL {attempt}] Hash CHYBA {received_hash} != {computed_hash}")
                    return False
            except ValueError:
                print(f"[FAIL {attempt}] Neplatný formát odpovědi: {line}")
                return False

    print(f"[TIMEOUT {attempt}] Nebyla přijata žádná odpověď.")
    return False

def serialGet(port:str, baudrate:int, timeout:float = 0.2) -> serial.Serial|str:
    """Otevře sériový port.
    Args:
        port (str): název portu, např. /dev/ttyS3
        baudrate (int): rychlost v baudech
        
    Returns:
        serial.Serial|str: otevřený port nebo chybová zpráva
    
    """
    try:
        ser = serial.Serial(port, baudrate, timeout=timeout)
        return ser
    except serial.SerialException as e:
        return f"[ERROR] Nelze otevřít port {port}: {e}"

def receiver_mode(ser:serial.Serial) -> str|None:
    """Režim příjmu - čeká na zprávy a odpovídá.
    Args:
        ser (serial.Serial): otevřený sériový port
    Returns:
        str|None: None když vše ok, nebo chybová zpráva pokud došlo k problému
    """
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"[INFO] Serial tester - Receiver {version} by dvestezar.cz")
    print(f"[INFO] Port: {ser.port} @ {ser.baudrate} baud\n")

    print(f"[RECEIVER] Režim příjmu aktivní. Čekám na zprávy...")
    print(f"[RECEIVER] Ukonči pomocí Ctrl+C\n")

    try:
        while True:
            line = ser.readline().decode(errors="replace").strip()
            if not line:
                continue

            ln=len(line)

            if line.startswith("test_"):
                print(f"[IN ] bytes received: {ln}",end='     ')
                payload = line[5:]  # nezapomenout že sender přidává `~` z obou stran
                hash_val = get_hash128(payload)
                resp = f"resp_{payload}_{hash_val}"
                ser.write((resp + "\r\n").encode())
                ser.flush()
                ln=len(resp)
                print(f"[OUT] bytes sent: {ln}, hash: {hash_val}")
            else:
                print(f"[IN ] {line}")
    except KeyboardInterrupt:
        return "[RECEIVER] Ukončeno uživatelem."

def cls():
    os.system('cls' if os.name == 'nt' else 'clear')

def header(ser:serial.Serial,clear = True):
    if clear:
        cls()
    print("*"*70)
    print(f"********** Serial tester - Sender {version} by dvestezar.cz **********")
    print("*"*70)
    print(f"[INFO] Port: {ser.port} @ {ser.baudrate} baud")
    print("Zadej příkaz 'test[<len>][n<repeat>]' nebo 'exit'.")
    print("Pro nápovědu zadej 'help'.")
    print("Pro spuštění režimu příjmu zadej 'rcv'.")
    print("\n")

def transmiter_mode(ser:serial.Serial):
    header(ser)
    while True:        
        try:
            line = input("> ")
        except EOFError:
            break
        if line.strip().lower() == "exit":
            break
        if line.strip().lower() == "cls":
            header(ser)
            continue
        if line.strip().lower() == "rcv":
            print("--- >>> Spouštím režim příjmu...")            
            if x:=receiver_mode(ser):
                print(x)
            print("--- <<< Návrat do odesílacího režimu.")
            time.sleep(1)
            header(ser)
                        
            continue
        if line.strip().lower() == "help":
            print("\n*** Dostupné příkazy: ***")
            print("  test              → syntaxe = test[<len>][n<repeat>]")
            print("  - test              → odešle 64 znaků (defaultní test)")
            print("  - test120           → odešle 120 znaků")
            print("  - test80n5          → odešle 80 znaků, opakuje 5x")
            print("  - testn3            → odešle 64 znaků, opakuje 3x")
            print("  rcv               → spustí režim příjmu")
            print("  cls               → smaže obrazovku")
            print("  exit              → ukončí skript")
            print("  help              → zobrazí tento přehled\n")
            continue        

        length, repeat = parse_command(line)
        if length:
            # testovací režim
            if length < 1:
                print("[ERROR] Délka musí být větší než 0.")
                continue
            if length > 1024:
                print("[ERROR] Délka je příliš velká (max 1024).")
                continue
            if repeat < 1:
                print("[ERROR] Počet opakování musí být větší než 0.")
                continue
            if repeat > 100:
                print("[ERROR] Počet opakování je příliš velký (max 100).")
                continue
            
            print(f"[INFO] Odesílám testovací zprávy ({length} znaků, {repeat}x)...")
            try:
                payload = generate_test_text(length)
                for i in range(1, repeat + 1):
                    send_and_wait_for_response(ser, payload, i)
                    time.sleep(0.3)
                # wait for a keypress
                input("Pro pokračování stiskněte ENTER...")
            except KeyboardInterrupt:
                print("\n[INFO] Ukončeno uživatelem.")
                time.sleep(1)
            header(ser)
        else:
            ser.write((line + "\r\n").encode())
            ser.flush()

def runAs(port:str, baudrate:int=DEFAULT_BAUDRATE, transmitter:bool=True)->str|None:
    """Spustí skript v zadaném režimu (transmitter/receiver) bez interaktivního promptu.
    Args:
        port (str): název portu, např. /dev/ttyS3
        baudrate (int, optional): rychlost v baudech. Defaults to DEFAULT_BAUDRATE.
        transmitter (bool, optional): True pro odesílací režim, False pro příjmový režim. Defaults to True.
    Returns:
        str|None: chybová zpráva nebo None pokud vše proběhlo v pořádku
    """
    ser=serialGet(port, baudrate)
    
    if isinstance(ser, str):
        return ser

    try:
        if transmitter:
            transmiter_mode(ser)
        else:
            return receiver_mode(ser)
    except Exception as e:
        return f"[ERROR] Došlo k chybě: {e}"
    finally:
        try:
            ser.close()
        except Exception as e:
            return f"[ERROR] Nelze zavřít port: {e}"
    return None

def main():
    cls()
    
    parser = argparse.ArgumentParser(description="Odesílá testovací zprávy na sériový port a ověřuje odpovědi.")
    parser.add_argument("port", help="Sériový port, např. /dev/ttyS3")
    parser.add_argument("-b", "--baudrate", type=int, default=DEFAULT_BAUDRATE, help="Rychlost v baudech (default: 19200)")
    parser.add_argument("-r", "--receiver", action="store_true", help="Spustit jako receiver (příjemce zpráv)")
    args = parser.parse_args()

    ret=runAs(args.port, args.baudrate, not args.receiver)
    chyba=False
    if ret:
        print(ret)
        chyba=True
    
    print("Ukončuji.")
    if chyba:
        sys.exit(1)

if __name__ == "__main__":
    main()
