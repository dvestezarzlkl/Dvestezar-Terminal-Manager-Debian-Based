from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from libs.JBLibs.systemUserManager import sshMng
from libs.app import mail_hlp


_DUMMY_PRIVATE_KEY_PREFIX = "DUMMY PRIVATE KEY - IMPORTED PUBLIC KEY ONLY"
_MAX_KEY_BYTES = 1024 * 1024
_DIR_OPEN_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_FILE_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


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


def _open_child_directory(parent_fd: int, name: str, label: str) -> int:
    fd = os.open(name, _DIR_OPEN_FLAGS, dir_fd=parent_fd)
    info = os.fstat(fd)
    if not stat.S_ISDIR(info.st_mode):
        os.close(fd)
        raise ValueError(f"{label} is not a directory.")
    return fd


def _read_regular_text(
    directory_fd: int,
    filename: str,
    required: bool,
) -> Optional[str]:
    try:
        file_fd = os.open(
            filename,
            os.O_RDONLY | _FILE_NOFOLLOW,
            dir_fd=directory_fd,
        )
    except FileNotFoundError:
        if required:
            raise
        return None

    try:
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(f"SSH key file is not a regular file: {filename}")
        if info.st_size > _MAX_KEY_BYTES:
            raise ValueError(f"SSH key file is too large: {filename}")

        chunks: list[bytes] = []
        remaining = _MAX_KEY_BYTES + 1
        while remaining > 0:
            chunk = os.read(file_fd, min(8192, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        if len(payload) > _MAX_KEY_BYTES:
            raise ValueError(f"SSH key file is too large: {filename}")
        return payload.decode("utf-8").strip()
    finally:
        os.close(file_fd)


def read_managed_key_pair(
    username: str,
    key_name: str,
) -> Tuple[bool, Optional[Tuple[str, str]], Optional[str]]:
    """Read one managed key pair without following user-controlled symlinks."""
    if not isinstance(key_name, str) or not key_name.strip():
        return False, None, "SSH key name is missing."
    key_name = key_name.strip()
    if Path(key_name).name != key_name or "\x00" in key_name:
        return False, None, "SSH key name is invalid."

    home = sshMng.getUserHome(username)
    if not home:
        return False, None, f"System user does not exist: {username}."

    home_fd: Optional[int] = None
    ssh_fd: Optional[int] = None
    manager_fd: Optional[int] = None
    try:
        home_fd = os.open(home, _DIR_OPEN_FLAGS)
        ssh_fd = _open_child_directory(home_fd, ".ssh", "User SSH directory")
        manager_fd = _open_child_directory(ssh_fd, "sshManager", "SSH Manager directory")

        public_key = _read_regular_text(manager_fd, f"{key_name}.pub", required=True)
        if not public_key:
            return False, None, f"Public key file is empty: {key_name}.pub"

        candidate = _read_regular_text(manager_fd, key_name, required=False) or ""
        private_key = ""
        if candidate and not candidate.startswith(_DUMMY_PRIVATE_KEY_PREFIX):
            private_key = candidate
        return True, (public_key, private_key), None
    except Exception as exc:
        return False, None, f"Cannot read SSH key files: {exc}"
    finally:
        for fd in (manager_fd, ssh_fd, home_fd):
            if fd is not None:
                os.close(fd)
