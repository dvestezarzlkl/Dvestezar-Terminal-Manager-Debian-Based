from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from libs.JBLibs.systemUserManager import sshMng
from libs.app import mail_hlp


_DUMMY_PRIVATE_KEY_PREFIX = "DUMMY PRIVATE KEY - IMPORTED PUBLIC KEY ONLY"


@dataclass(frozen=True)
class SshKeyBundleNames:
    public_filename: str
    private_filename: str
    readme_filename: str
    archive_filename: str


def safe_export_component(value: str, fallback: str = "ssh_user") -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    return safe or fallback


def key_file_stem(public_key: str) -> str:
    key_type = public_key.split(maxsplit=1)[0] if public_key else ""
    return {
        "ssh-ed25519": "id_ed25519",
        "sk-ssh-ed25519@openssh.com": "id_ed25519_sk",
        "ssh-rsa": "id_rsa",
        "ssh-dss": "id_dsa",
        "ecdsa-sha2-nistp256": "id_ecdsa",
        "ecdsa-sha2-nistp384": "id_ecdsa",
        "ecdsa-sha2-nistp521": "id_ecdsa",
        "sk-ecdsa-sha2-nistp256@openssh.com": "id_ecdsa_sk",
    }.get(key_type, "id_ssh_key")


def build_bundle_names(
    label: str,
    public_key: str,
    archive_suffix: str = "ssh_keys",
) -> SshKeyBundleNames:
    safe_label = safe_export_component(label)
    safe_suffix = safe_export_component(archive_suffix, "ssh_keys")
    key_stem = key_file_stem(public_key)
    return SshKeyBundleNames(
        public_filename=f"{safe_label}_{key_stem}.pub",
        private_filename=f"{safe_label}_{key_stem}",
        readme_filename=f"{safe_label}_README.txt",
        archive_filename=f"{safe_label}_{safe_suffix}.zip",
    )


def create_key_bundle_attachment(
    names: SshKeyBundleNames,
    public_key: str,
    private_key: str,
    readme: str,
) -> mail_hlp.MailAttachment:
    items = [
        mail_hlp.ZipItem(
            names.public_filename,
            (public_key.rstrip() + "\n").encode("utf-8"),
        )
    ]
    if private_key:
        items.insert(
            0,
            mail_hlp.ZipItem(
                names.private_filename,
                (private_key.rstrip() + "\n").encode("utf-8"),
            ),
        )
    items.append(mail_hlp.ZipItem(names.readme_filename, readme.encode("utf-8")))
    return mail_hlp.create_zip_attachment(names.archive_filename, items)


def read_managed_key_pair(
    username: str,
    key_name: str,
) -> Tuple[bool, Optional[Tuple[str, str]], Optional[str]]:
    """Read one SSH Manager key pair; imported public-only dummy files are omitted."""
    if not isinstance(key_name, str) or not key_name.strip():
        return False, None, "SSH key name is missing."
    key_name = key_name.strip()
    if Path(key_name).name != key_name or "\x00" in key_name:
        return False, None, "SSH key name is invalid."

    manager_dir = sshMng.getDirPath_sshManager(username, True)
    if not manager_dir:
        return False, None, f"SSH Manager directory does not exist for user {username}."

    public_path = Path(manager_dir) / f"{key_name}.pub"
    private_path = Path(manager_dir) / key_name
    if not public_path.is_file():
        return False, None, f"Public key file does not exist: {public_path}"

    try:
        public_key = public_path.read_text(encoding="utf-8").strip()
        if not public_key:
            return False, None, f"Public key file is empty: {public_path}"

        private_key = ""
        if private_path.is_file():
            candidate = private_path.read_text(encoding="utf-8").strip()
            if candidate and not candidate.startswith(_DUMMY_PRIVATE_KEY_PREFIX):
                private_key = candidate
        return True, (public_key, private_key), None
    except Exception as exc:
        return False, None, f"Cannot read SSH key files: {exc}"
