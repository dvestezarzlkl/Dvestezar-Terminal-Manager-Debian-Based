#!/usr/bin/env python3
import os
import re
import sys
import base64
import subprocess
from datetime import datetime

NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")

def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)

def run(cmd: list[str]) -> None:
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if r.returncode != 0:
        die(f"Command failed: {' '.join(cmd)}\n{r.stderr.strip()}")

def main() -> None:
    name = input("Zadej jméno (A-Z a-z 0-9 _): ").strip()
    if not name:
        die("Jméno je prázdné.")
    if not NAME_RE.match(name):
        die("Neplatné jméno. Povolené znaky: A-Z a-z 0-9 _")

    ts = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    base_dir = os.path.join("keys", name, ts)
    os.makedirs(base_dir, exist_ok=False)

    # bezpečné práva na adresář
    os.chmod(base_dir, 0o700)

    priv_path = os.path.join(base_dir, "key.priv")
    pub_path  = os.path.join(base_dir, "key.pub")
    b64_path  = os.path.join(base_dir, "key.base64")

    # vygeneruj ED25519 klíč bez passphrase (-N "")
    # Pozn.: ssh-keygen vytvoří <file> a <file>.pub, tak to hned přejmenujeme.
    tmp_key_path = os.path.join(base_dir, "key_tmp")
    run(["ssh-keygen", "-t", "ed25519", "-a", "64", "-f", tmp_key_path, "-N", "", "-C", name])

    # přejmenuj na požadované názvy
    os.replace(tmp_key_path, priv_path)
    os.replace(tmp_key_path + ".pub", pub_path)

    # nastav práva na klíče
    os.chmod(priv_path, 0o600)
    os.chmod(pub_path, 0o644)

    # base64 z PUBLIC klíče (celý řádek key.pub)
    with open(pub_path, "rb") as f:
        raw = f.read()
    b64 = base64.b64encode(raw).decode("ascii")
    with open(b64_path, "w", encoding="utf-8") as f:
        f.write(b64 + "\n")
    os.chmod(b64_path, 0o644)  # public info

    print("\nHotovo:")
    print(f"  {priv_path}")
    print(f"  {pub_path}")
    print(f"  {b64_path}")

if __name__ == "__main__":
    # rychlá kontrola dostupnosti ssh-keygen
    if subprocess.run(["which", "ssh-keygen"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        die("Chybí ssh-keygen. Doinstaluj balík: apt install openssh-client")
    main()
