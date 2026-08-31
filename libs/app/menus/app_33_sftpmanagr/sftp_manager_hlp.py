from __future__ import annotations

from .helper_lng import *

import base64
import html

import json5
import os
import binascii
import re
from typing import Dict, List, Optional, Tuple
import tempfile
import time

from libs.JBLibs.helper import getLogger
from libs.JBLibs.sftp.parser import check_config_exists, check_config_valid, uninstallAllUsers as unInstAll, createUserFromJson, getDefaultEtcConfigPath,uninstallUnwantedUsers
from libs.JBLibs.sftp.mountpoint_templates import effective_mountpoint_records, resolve_mountpoint_records
from libs.JBLibs.sftp.sambaPoint import smbHelp, ManagedCIFSTargetNotEmptyError
from libs.JBLibs.sftp.ssh import restart_sshd
from libs.JBLibs.term import text_color, en_color
from libs.JBLibs.archive_backup import get_backup_stats
from libs.app import cfg as app_cfg
from libs.app import mail_hlp

log = getLogger("sftpprs")

_SFTP_BACKUP_DIRNAME = "sftpusers"

def _get_sftp_backup_root(create: bool = False) -> str:
    """Return the secure root used for automatic SFTP user backups."""
    base = app_cfg.BACKUP_DIRECTORY
    if not isinstance(base, str) or not os.path.isabs(base):
        raise RuntimeError(f"Invalid BACKUP_DIRECTORY for SFTP backups: {base!r}")
    root = os.path.join(base, _SFTP_BACKUP_DIRNAME)
    if create:
        os.makedirs(root, mode=0o700, exist_ok=True)
        os.chown(root, 0, 0)
        os.chmod(root, 0o700)
    return root

def get_sftp_backup_stats() -> Tuple[int, int]:
    """Return count and total archive bytes for SFTP user backups."""
    try:
        stats = get_backup_stats(_get_sftp_backup_root(create=False))
        return stats.count, stats.size_bytes
    except Exception as e:
        log.warning(f"Cannot read SFTP backup statistics: {e}")
        return 0, 0

def cifs_exists() -> bool:
    """Return True when the mount.cifs helper is available."""
    return smbHelp.checkCIFSInstalled()

def config_requires_cifs(cfg: Dict) -> bool:
    """Return True when an enabled effective mount belongs to a Samba vault user."""
    users = cfg.get("users", []) if isinstance(cfg, dict) else []
    for user in users:
        if not isinstance(user, dict) or user.get("sambaVault") is not True:
            continue
        records, errors = resolve_mountpoint_records(cfg, user)
        if errors:
            continue
        if effective_mountpoint_records(records):
            return True
    return False

def load_config(path: Optional[str] = None) -> Tuple[bool,Optional[str],Optional[Dict]]:
    """Load and parse the SFTP manager configuration.

    Args:
        path: Optional alternative path to a configuration file.  If not
            provided, :data:`CONFIG_PATH` is used.

    Returns:
        A tuple ``(success, error_message, config)`` where ``success`` is
        ``True`` if the configuration was loaded successfully, otherwise ``False``.
        If ``success`` is ``False``, ``error_message`` contains a descriptive error message;
        if ``success`` is ``True``, ``error_message`` is ``None``. 
        The ``config`` is a dictionary representing the decoded JSON configuration if loading was successful,
        otherwise ``None``.  If the file does not exist or cannot be parsed, a minimal configuration containing
        an empty ``users`` list is returned and ``success`` is ``True``.
    """
    
    cfg_path = path or getDefaultEtcConfigPath()
    if not os.path.isfile(cfg_path):
        # Return a minimal configuration if no file exists yet.
        return True, None, {"users": []}
    try:
        with open(cfg_path, "r") as fh:
            data = json5.load(fh)        
        if not isinstance(data, dict):
            return True, None, {"users": []}
        # Ensure there is always a users list.
        data.setdefault("users", [])
        return True, None, data
    except Exception as e:
        log.error(f"Error loading config from {cfg_path}: {e}")
        # In the face of any parsing error return an empty config.
        return False, TXT_SFTP_HLP_LOAD_CONFIG_FAILED.format(error=e), {"users": []}


def save_config(cfg: Dict, path: Optional[str] = None) -> None:
    """Write a configuration dictionary back to disk.

    Args:
        cfg: Configuration dictionary to serialise.
        path: Optional override for the file path.

    The configuration is serialised to JSON using an indentation of
    four spaces.  Comments are not preserved; subsequent calls to
    :func:`load_config` will therefore return a comment‑free structure.
    """
    cfg_path = path or getDefaultEtcConfigPath()
    cfg_dir = os.path.dirname(cfg_path)
    os.makedirs(cfg_dir, exist_ok=True)
    
    # Write to temporary file first
    temp_fd, temp_path = tempfile.mkstemp(dir=cfg_dir, text=True)
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as fh:
            json5.dump(cfg, fh, indent=4)
        
        # If original exists, create backup with timestamp
        if os.path.isfile(cfg_path):
            timestamp = int(time.time())
            backup_path = f"{cfg_path}.bak.{timestamp}"
            os.rename(cfg_path, backup_path)
            
            # Clean up old backups (keep last 10)
            backups = sorted([
                f for f in os.listdir(cfg_dir)
                if f.startswith(os.path.basename(cfg_path) + ".bak.")
            ])
            for old_backup in backups[:-9]:
                try:
                    os.remove(os.path.join(cfg_dir, old_backup))
                except OSError:
                    pass
        
        # Atomic rename: move temp file to final location
        os.rename(temp_path, cfg_path)
    except Exception as e:
        log.error(f"Error saving config to {cfg_path}: {e}")
        # Clean up temp file if something went wrong
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def is_valid_mail_address(mail: str) -> bool:
    """Return ``True`` if the value looks like a single email address."""
    return mail_hlp.is_valid_mail_address(mail)


def get_admin_mail(cfg: Dict) -> Optional[str]:
    """Return the configured admin email address, if any."""
    mail = cfg.get("adminMail")
    if not isinstance(mail, str):
        return None
    mail = mail.strip()
    return mail or None


def set_admin_mail(cfg: Dict, mail: str) -> Tuple[bool, Optional[str]]:
    """Store the admin email address in the configuration."""
    if not is_valid_mail_address(mail):
        return False, TXT_SFTP_HLP_INVALID_ADMIN_MAIL
    cfg["adminMail"] = mail.strip().lower()
    return True, None


def get_user_mail(cfg: Dict, username: str) -> Optional[str]:
    """Return the optional mail address configured for a user."""
    usr = find_user(cfg, username)
    if not usr:
        return None
    mail = usr.get("mail")
    if not isinstance(mail, str):
        return None
    mail = mail.strip()
    return mail or None


def set_user_mail(cfg: Dict, username: str, mail: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Store or clear the optional mail address for a user."""
    usr = find_user(cfg, username)
    if not usr:
        return False, TXT_SFTP_HLP_USER_NOT_FOUND

    if mail is None or not str(mail).strip():
        usr.pop("mail", None)
        return True, None

    mail = str(mail).strip()
    if not is_valid_mail_address(mail):
        return False, TXT_SFTP_HLP_INVALID_USER_MAIL

    usr["mail"] = mail.lower()
    return True, None


def _safe_key_export_name(value: str) -> str:
    """Return a short filesystem-safe component for exported key files."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value)).strip("._")
    return safe or "sftp_user"


def _key_file_stem(public_key: str) -> str:
    """Map an OpenSSH public-key type to a familiar private-key filename."""
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


def build_key_mail_payload(
    username: str,
    public_key: str,
    private_key: str,
    recipients: List[str],
) -> Tuple[str, str, str, List[mail_hlp.MailAttachment]]:
    """Build localized SFTP key mail bodies and an in-memory ZIP attachment."""
    safe_username = _safe_key_export_name(username)
    key_stem = _key_file_stem(public_key)
    public_filename = f"{safe_username}_{key_stem}.pub"
    private_filename = f"{safe_username}_{key_stem}"
    readme_filename = f"{safe_username}_README.txt"
    archive_filename = f"{safe_username}_sftp_keys.zip"

    if private_key:
        private_line = TXT_SFTP_HLP_MAIL_README_PRIVATE_LINE.format(
            private_filename=private_filename
        )
        private_usage = private_filename
    else:
        private_line = TXT_SFTP_HLP_MAIL_README_NO_PRIVATE_LINE
        private_usage = TXT_SFTP_HLP_MAIL_README_PRIVATE_NOT_AVAILABLE

    generated_by = TXT_SFTP_HLP_MAIL_GENERATED_BY.format(
        version=getattr(app_cfg, "VERSION", "")
    )
    readme = TXT_SFTP_HLP_MAIL_README.format(
        username=username,
        access_purpose=TXT_SFTP_HLP_MAIL_ACCESS_PURPOSE,
        public_filename=public_filename,
        private_line=private_line,
        private_usage=private_usage,
        generated_by=generated_by,
    )

    zip_items = [
        mail_hlp.ZipItem(
            public_filename,
            (public_key.rstrip() + "\n").encode("utf-8"),
        ),
    ]
    if private_key:
        zip_items.insert(
            0,
            mail_hlp.ZipItem(
                private_filename,
                (private_key.rstrip() + "\n").encode("utf-8"),
            ),
        )
    zip_items.append(
        mail_hlp.ZipItem(readme_filename, readme.encode("utf-8"))
    )

    try:
        attachment = mail_hlp.create_zip_attachment(archive_filename, zip_items)
    except Exception as e:
        raise ValueError(TXT_SFTP_HLP_MAIL_ZIP_FAILED.format(error=e)) from e

    subject = TXT_SFTP_HLP_MAIL_SUBJECT.format(username=username)
    subject += (
        TXT_SFTP_HLP_MAIL_SUBJECT_PUBLIC_PRIVATE
        if private_key
        else TXT_SFTP_HLP_MAIL_SUBJECT_PUBLIC
    )

    body_lines = [
        TXT_SFTP_HLP_MAIL_EXPORT_FOR.format(username=username),
        TXT_SFTP_HLP_MAIL_ACCESS_PURPOSE,
        TXT_SFTP_HLP_MAIL_RECIPIENTS.format(recipients=', '.join(recipients)),
        "",
        TXT_SFTP_HLP_MAIL_ARCHIVE_ATTACHED.format(filename=archive_filename),
        TXT_SFTP_HLP_MAIL_PRIVATE_WARNING
        if private_key
        else TXT_SFTP_HLP_MAIL_NO_PRIVATE_KEY,
        "",
        generated_by,
    ]
    text_body = "\n".join(body_lines)

    html_lines = [
        "<html>",
        "  <body>",
        "    <p>{}<br>".format(
            html.escape(TXT_SFTP_HLP_MAIL_EXPORT_FOR.format(username=username))
        ),
        "       {}</p>".format(
            html.escape(
                TXT_SFTP_HLP_MAIL_RECIPIENTS.format(
                    recipients=', '.join(recipients)
                )
            )
        ),
        "    <p>{}</p>".format(
            html.escape(TXT_SFTP_HLP_MAIL_ACCESS_PURPOSE)
        ),
        "    <p>{}</p>".format(
            html.escape(
                TXT_SFTP_HLP_MAIL_ARCHIVE_ATTACHED.format(
                    filename=archive_filename
                )
            )
        ),
        "    <p>{}</p>".format(
            html.escape(
                TXT_SFTP_HLP_MAIL_PRIVATE_WARNING
                if private_key
                else TXT_SFTP_HLP_MAIL_NO_PRIVATE_KEY
            )
        ),
        "    <p>{}</p>".format(html.escape(generated_by)),
        "  </body>",
        "</html>",
    ]
    html_body = "\n".join(html_lines)

    return subject, text_body, html_body, [attachment]


def send_key_by_mail(cfg: Dict, username: str, key: str) -> Tuple[bool, Optional[str]]:
    """Send a restricted SFTP access key as a ZIP attachment."""
    admin_mail = get_admin_mail(cfg) or mail_hlp.get_fallback_admin_mail()
    if not admin_mail:
        return False, TXT_SFTP_HLP_ADMIN_MAIL_NOT_CONFIGURED

    user_mail = get_user_mail(cfg, username)
    if user_mail is not None and not is_valid_mail_address(user_mail):
        return False, TXT_SFTP_HLP_USER_MAIL_INVALID.format(username=username)

    print(TXT_SFTP_HLP_MAIL_GENERATING, flush=True)
    ok, printable = get_printable_keys(key)
    if not ok:
        return False, TXT_SFTP_HLP_KEY_PARSE_FAILED.format(error=printable)

    public_key, private_key = printable
    recipients = [admin_mail]
    if user_mail and user_mail not in recipients:
        recipients.append(user_mail)

    try:
        subject, text_body, html_body, attachments = build_key_mail_payload(
            username,
            public_key,
            private_key,
            recipients,
        )
    except Exception as e:
        return False, str(e)

    return mail_hlp.send_mail(
        recipients,
        subject,
        text_body,
        html_body=html_body,
        attachments=attachments,
    )


def list_users(cfg: Optional[Dict] = None) -> List[Dict]:
    """Return a shallow list of SFTP user objects.

    Each user object is the raw dictionary from the configuration and
    contains keys such as ``sftpuser``, ``sambaVault``, ``sftpmounts``
    and ``sftpcerts``.
    """
    cfg = cfg or load_config()
    return cfg.get("users", [])


def find_user(cfg: Dict, username: str) -> Optional[Dict]:
    """Locate a user dictionary by name.

    Args:
        cfg: The configuration dictionary to search.
        username: The ``sftpuser`` value to look for.

    Returns:
        The user dictionary if found, otherwise ``None``.
    """
    for usr in cfg.get("users", []):
        if usr.get("sftpuser") == username:
            return usr
    return None


def add_user(cfg: Dict, username: str) -> bool:
    """Append a new user to the configuration.

    Args:
        cfg: The configuration dictionary to modify.
        username: Name of the new SFTP user.

    Returns:
        ``True`` if the user was added; ``False`` if a user with the
        same name already exists.
    """
    if find_user(cfg, username):
        return False
    cfg.setdefault("users", []).append({
        "sftpuser": username,
        "sambaVault": True,
        "sftpmounts": {},
        "sftpcerts": [],
    })
    return True


def delete_user(cfg: Dict, username: str) -> bool:
    """Remove a user from the configuration.

    Args:
        cfg: Configuration dictionary to mutate.
        username: Name of the user to remove.

    Returns:
        ``True`` if a user was removed; ``False`` otherwise.
    """
    users = cfg.get("users", [])
    for idx, usr in enumerate(users):
        if usr.get("sftpuser") == username:
            del users[idx]
            return True
    return False


def list_mountpoints(cfg: Dict, username: str) -> List[Tuple[str, str]]:
    """List all mountpoints for a given user.

    Returns:
        A list of tuples ``(label, target_path)``.  If the user does not
        exist, an empty list is returned.
    """
    usr = find_user(cfg, username)
    if not usr:
        return []
    mounts = usr.get("sftpmounts", {})
    return list(mounts.items())

def checkMountpointExists(cfg: Dict, username: str, label: str) -> bool:
    """Check if a mountpoint with the given label exists for the user.
    
    Parameters:
        cfg: Configuration dictionary to search.
        username: Name of the user to check.
        label: The mountpoint label (alias) to look for.
        
    Returns:
        bool: True if a mountpoint with the specified label exists for the user; False otherwise.        
    
    """
    usr = find_user(cfg, username)
    if not usr:
        return False
    mounts = usr.get("sftpmounts", {})
    return label in mounts

def checkMountPointPathExists(cfg: Dict, username: str, target_path: str) -> Optional[str]:
    """Check if a mountpoint with the given target path exists for the user.
    
    Parameters:
        cfg: Configuration dictionary to search.
        username: Name of the user to check.
        target_path: The absolute path that the mountpoint points to.
        
    Returns:
        Optional[str]: None pokud nenalezeno, jinak vrací label (alias) mountpointu, který již používá zadanou cestu jako cílovou.
    
    """
    usr = find_user(cfg, username)
    if not usr:
        return None
    mounts = usr.get("sftpmounts", {})
    for label, path in mounts.items():
        if path == target_path:
            return label
    return None

def add_mountpoint(cfg: Dict, username: str, label: str, path: str, readOnly:bool) -> bool:
    """Add or replace a mountpoint for the given user.

    Returns:
        ``True`` if the mountpoint was added/updated; ``False`` if the
        user does not exist.
    """
    usr = find_user(cfg, username)
    if not usr:
        return False
    mounts = usr.setdefault("sftpmounts", {})
    mounts[label] = path
    
    pointSet = usr.setdefault("pointsSet", {})
    pointSet[label] = {"rw": not readOnly}
    
    return True

def set_mountpoint_path(cfg: Dict, username: str, label: str, path: str) -> bool:
    """Update only the configured real path of an existing mountpoint.

    Apply detects the changed real path against the active mountpoint, removes
    the old system/Samba/CIFS definition and then ensures the same alias from
    the new path.
    """
    usr = find_user(cfg, username)
    if not usr:
        return False
    mounts = usr.get("sftpmounts", {})
    if label not in mounts:
        return False
    mounts[label] = path
    return True

def set_mountpoint_readonly(cfg: Dict, username: str, label: str, readOnly: bool) -> bool:
    """Set the read-only status of an existing mountpoint.

    Returns:
        ``True`` if the mountpoint was updated; ``False`` if the
        user or mountpoint does not exist.
    """
    usr = find_user(cfg, username)
    if not usr:
        return False
    pointSet = usr.setdefault("pointsSet", {})
    if label not in pointSet:
        pointSet[label] = {"rw": not readOnly}
    else:
        pointSet[label]["rw"] = not readOnly
    return True

def get_mountpointReadOnlyStatus(cfg: Dict, username: str, label: str) -> Optional[bool]:
    """Get the read-only status of an existing mountpoint.

    Returns:
        ``True`` if the mountpoint is read-only, ``False`` if it is read-write, or ``None`` if the user or mountpoint does not exist.
    """
    usr = find_user(cfg, username)
    if not usr:
        return None
    pointSet = usr.get("pointsSet", {})
    if label not in pointSet:
        return None
    # pokud neexistuje tak je default RW
    return not pointSet[label].get("rw", True)

def delete_mountpoint(cfg: Dict, username: str, label: str) -> bool:
    """Remove a mountpoint from the given user.

    Returns:
        ``True`` if a mountpoint was removed; ``False`` if not found or
        if the user does not exist.
    """
    usr = find_user(cfg, username)
    if not usr:
        return False
    mounts = usr.get("sftpmounts", {})
    pointSet = usr.get("pointsSet", {})
    if label in mounts:
        del mounts[label]
        if label in pointSet:
            del pointSet[label]
        return True
    return False

def crc32(s: str) -> str:
    """Calculate a CRC32 checksum of the given string and return it as an 8-character hexadecimal string."""
    import zlib
    return f"{zlib.crc32(s.encode('utf-8')) & 0xffffffff:08x}"

def list_keys(cfg: Dict, username: str) -> List[Tuple[str,str,bool]]:
    """List public keys (and raw certificates) for the given user.
    vrací seznam tuple (název a celý key - záznam, jak je) název je část na konci certifikátu
    na konci vrací jestli má záznam i privátní část
    
    """
    usr = find_user(cfg, username)
    if not usr:
        return []
    x = list(usr.get("sftpcerts", []))
    o=[]
    for k in x:
        has_pk = False
        org=k
        # pokud začíná 'b64:' tak dekódujeme        
        if k.startswith("b64:"):
            # otestuejem na pk, ta je oddělena "-pk:" a je na konci, pokud tam je tak ji odstraníme a použijeme pouze veřejnou část certifikátu pro zobrazení
            try:

                has_pk = "-pk:" in k
                if has_pk:
                    pk_index = k.find("-pk:")
                    cert_part = k[4:pk_index]
                else:
                    cert_part = k[4:] # odstraníme prefix
            
                k = base64.b64decode(cert_part).decode("utf-8")
            except Exception as e:
                log.error(f"Failed to decode base64 key: {e}")
                # pokud se nepodaří dekódovat, použijeme původní řetězec bez 'b64:' prefixu
                k = org
        
        # název je část za poslední mezerou, pokud tam není mezera tak celý záznam
        if " " in k:
            name = k.rsplit(" ", 1)[-1]
        else:
            name = k
        name=name.strip()
        
        # přidám na konec název + 6 znaků z CRC32 pro odlišení klíčů se stejným názvem
        # taky přidáme tak PK pokud tam je, aby bylo vidět že se jedná o záznam s privátní částí
        name= f"{name}  {crc32(k)[:6]}"
        if has_pk:
            name += " " + text_color(TXT_SFTP_HLP_WITH_PRIVATE_KEY, en_color.BRIGHT_MAGENTA)
        o.append((name,org, has_pk))
    return o

from typing import Tuple
import base64
import binascii


def check_ssh_pub_key(key: str, outAsB64ForMng: bool = True) -> Tuple[bool, str] | Tuple[bool, Tuple[str, str]]:
    """Validuje SSH veřejný klíč a volitelně extrahuje privátní část z formátu b64:<base64>-pk:<base64>.
    
    Args:
        key: Řetězec obsahující veřejný klíč ve formátu OpenSSH (např. "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIB3... user@host") nebo ve formátu
        "b64:<base64>" případně "b64:<base64>-pk:<base64>" pro záznamy obsahující i privátní část.
        outAsB64ForMng: Pokud je True, výstupní klíč bude ve formátu "b64:<base64>" pro konzistenci s interním uložením v konfiguraci.  Pokud je False, výstup bude ve formátu OpenSSH (typ + base64 + komentář).

    Returns:
        Při outAsB64ForMng=True: Tuple[bool, str] kde první prvek je:
            - True pokud je klíč validní a je ve formátu "b64:<base64>" popř s privátní částí "-pk:<base64>", připravený pro uložení do konfigurace.
            - False Druhý prvek je chybová zpráva pokud klíč není validní, jinak None.
        Při outAsB64ForMng=False: Tuple[bool, str, str] kde první prvek je:
            - True pokud je klíč validní, druhý prvek je dekódovaný klíč ve formátu OpenSSH (typ + base64 + komentář)
                a třetí prvek je privátní část pokud existuje, jinak prázdný řetězec.
            - False Druhý prvek je chybová zpráva pokud klíč není validní, třetí prvek je None.
    """
    
    k = key.strip()
    pk= ""

    if k.startswith("b64:"):
        try:
            # pokud obsahuje PK, tak extrahujeme
            has_pk = "-pk:" in k
            if has_pk:
                pk_index = k.find("-pk:")
                cert_part = k[4:pk_index]                
                pk= k[pk_index+4:] # získáme část s privátní částí
            else:
                cert_part = k[4:] # odstraníme prefix
            
            k = base64.b64decode(cert_part).decode("utf-8")
        except Exception:
            return False, TXT_SFTP_HLP_BASE64_DECODE_FAILED

    parts = k.split()

    if len(parts) < 2:
        return False, TXT_SFTP_HLP_INVALID_PUBLIC_FORMAT

    key_type = parts[0].strip()
    key_b64 = parts[1].strip()    

    try:
        key_bytes = base64.b64decode(key_b64, validate=True)
    except (binascii.Error, ValueError):
        return False, TXT_SFTP_HLP_INVALID_PUBLIC_BASE64

    try:
        from paramiko.pkey import PKey, UnknownKeyType
        from paramiko.ssh_exception import SSHException

        pkey = PKey.from_type_string(key_type, key_bytes)

        # kontrola typu
        if pkey.get_name() != key_type:
            return False, TXT_SFTP_HLP_KEY_TYPE_MISMATCH.format(declared=key_type, parsed=pkey.get_name())

        # velmi důležitá kontrola integrity:
        # canonical base64 po parsování musí sedět přesně na vstup
        if pkey.get_base64() != key_b64:
            return False, TXT_SFTP_HLP_PUBLIC_ROUNDTRIP_FAILED

    except UnknownKeyType:
        return False, TXT_SFTP_HLP_UNSUPPORTED_KEY_TYPE.format(key_type=key_type)
    except SSHException as e:
        return False, TXT_SFTP_HLP_INVALID_PUBLIC_KEY.format(error=e)
    except ImportError as e:
        return False, TXT_SFTP_HLP_PARAMIKO_MISSING.format(error=e)

    if pk:
        try:
            pk_decoded = base64.b64decode(pk).decode("utf-8")
        except Exception:
            return False, TXT_SFTP_HLP_PRIVATE_DECODE_FAILED

        # --- pokus 1: Paramiko ---
        try:
            from io import StringIO
            from paramiko import RSAKey, ECDSAKey, Ed25519Key
            from paramiko.ssh_exception import SSHException, PasswordRequiredException

            key_file = StringIO(pk_decoded)
            priv_key = None

            for cls in (RSAKey, ECDSAKey, Ed25519Key):
                key_file.seek(0)
                try:
                    priv_key = cls.from_private_key(key_file)
                    break
                except PasswordRequiredException:
                    return False, TXT_SFTP_HLP_PRIVATE_ENCRYPTED
                except Exception:
                    pass

            if priv_key:
                # porovnání public části
                if priv_key.get_name() != key_type:
                    return False, TXT_SFTP_HLP_PRIVATE_TYPE_MISMATCH

                if priv_key.get_base64() != key_b64:
                    return False, TXT_SFTP_HLP_PRIVATE_KEY_MISMATCH

            else:
                raise Exception("Paramiko could not parse private key")

        except Exception:
            # --- fallback: cryptography ---
            try:
                from cryptography.hazmat.primitives import serialization

                private_key = serialization.load_ssh_private_key(
                    pk_decoded.encode("utf-8"),
                    password=None
                )

                public_key_bytes = private_key.public_key().public_bytes(
                    encoding=serialization.Encoding.OpenSSH,
                    format=serialization.PublicFormat.OpenSSH
                ).decode("utf-8")

                # rozparsujeme public z private
                parts_priv = public_key_bytes.split()
                if len(parts_priv) < 2:
                    return False, TXT_SFTP_HLP_EXTRACT_PUBLIC_FAILED

                if parts_priv[0] != key_type:
                    return False, TXT_SFTP_HLP_PRIVATE_TYPE_MISMATCH

                if parts_priv[1] != key_b64:
                    return False, TXT_SFTP_HLP_PRIVATE_KEY_MISMATCH

            except Exception as e:
                return False, TXT_SFTP_HLP_INVALID_PRIVATE_KEY.format(error=e)


    # pokud chceš komentář povinně, nech to jako vlastní business pravidlo:
    # if not key_comment:
    #     return False, "Public key is missing a comment (username or identifier)."

    if outAsB64ForMng:
        out = "b64:" + base64.b64encode(k.encode("utf-8")).decode("utf-8") if outAsB64ForMng else k
        if pk:
            out += "-pk:" + pk
        return True, out
    else:
        # decode pk
        priv = ""
        if pk:
            try:
                priv = base64.b64decode(pk).decode("utf-8")
            except Exception as e:
                log.error(f"Failed to decode private key part: {e}")
                priv = ""
        return True, (k, priv)
        

def add_key(cfg: Dict, username: str, key: str) -> Tuple[bool, Optional[str]]:
    """Append a new public key or certificate to a user.

    Returns:
        ``True`` if the key was added; ``False`` if the user does not
        exist.
    """
    
    ok,keyOrMsg = check_ssh_pub_key(key)
    if not ok:
        log.error(f"Key validation failed: {keyOrMsg}")
        return False, keyOrMsg
    else:
        key = keyOrMsg
    
    usr = find_user(cfg, username)
    if not usr:
        return False, TXT_SFTP_HLP_USER_NOT_FOUND
    
    #test jestli tam už není
    keys = usr.get("sftpcerts", [])
    if key in keys:
        return False, TXT_SFTP_HLP_KEY_ALREADY_EXISTS
    
    usr.setdefault("sftpcerts", []).append(key)
    return True, None

def generate_ssh_ed25519_keypair(usrname: str) -> Tuple[bool, Optional[Tuple[str, str]], Optional[str]]:
    """Genereruje pár, do komentu dá username a hostname, vrací tuple (success, (private_key, public_key), error_message)"""

    # "YmdHis"
    timestamp = time.strftime("%Y%m%d%H%M%S")
    comment= f"{timestamp}_{usrname}@{os.uname().nodename}"
    import libs.JBLibs.sftp.ssh as ssh
    try:
        ok, keys = ssh.generate_ssh_ed25519_keypair(comment=comment)
        if not ok:
            return False, None, TXT_SFTP_HLP_KEY_GENERATE_FAILED.format(error=keys)
    except Exception as e:
        return False, None, TXT_SFTP_HLP_KEY_GENERATE_EXCEPTION.format(error=e)
    return True, keys, None


def add_new_key_pair(cfg: Dict, username: str) -> Tuple[bool, Optional[str]]:
    """Generates a new SSH Ed25519 key pair and adds the public key to the user's configuration.

    Returns:
        Tuple[bool, Optional[str]]: A tuple where the first element is True if the key pair was successfully generated and added, otherwise False. The second element is an error message if the operation failed, or None if it succeeded.
    """
    ok, keys, err = generate_ssh_ed25519_keypair(username)
    if not ok:
        return False, TXT_SFTP_HLP_KEY_PAIR_GENERATION_FAILED.format(error=err)
    
    # sestavíme key
    private_key = base64.b64encode(keys[0].encode('utf-8')).decode('utf-8')
    public_key = base64.b64encode(keys[1].encode('utf-8')).decode('utf-8')
    key_entry = f"b64:{public_key}-pk:{private_key}"
    add_ok, add_err = add_key(cfg, username, key_entry)
    if not add_ok:
        return False, TXT_SFTP_HLP_ADD_GENERATED_KEY_FAILED.format(error=add_err)
    
    # Optionally, you could return the private key here or handle it as needed.
    return True, None

def get_printable_keys(b64key:str) -> Tuple[bool,Tuple[str,str], Optional[str]]:
    """Získá z b64 zakódovaného klíče tuple (název, (pub,priv))
    
    Args:
        b64key: Klíč ve formátu "b64:<base64>-pk:<base64>" nebo "b64:<base64>"
    
    Returns:
        Tuple[bool, Tuple[str, str], Optional[str]]: První prvek je True pokud se klíč úspěšně zpracoval, jinak False. Druhý prvek je tuple (název, (pub, priv)) kde název je část za poslední mezerou v dekódovaném klíči a pub/priv jsou veřejná a privátní část klíče. Třetí prvek je chybová zpráva pokud se klíč nepodařilo zpracovat, jinak None.
    """
    try:
        ok, prm = check_ssh_pub_key(b64key, outAsB64ForMng=False)
        if not ok:
            return False, TXT_SFTP_HLP_KEY_VALIDATION_FAILED.format(error=prm)
        
        pub, priv = prm
                
        return True, (pub.strip(), priv.strip())
    except Exception as e:
        return False, TXT_SFTP_HLP_KEY_PROCESSING_EXCEPTION.format(error=e)
    

def delete_key(cfg: Dict, username: str, key: str) -> bool:
    """Remove a key from a user.  Keys are compared as exact strings.

    Returns:
        ``True`` if the key was removed; ``False`` otherwise.
    """
    usr = find_user(cfg, username)
    if not usr:
        return False
    keys = usr.get("sftpcerts", [])
    try:
        keys.remove(key)
        return True
    except ValueError:
        return False



def apply_changes(cfg: Optional[Dict] = None, save: bool = False) -> Tuple[bool, Optional[str]]:
    """Apply the SFTP configuration and optionally persist it after success.

    Args:
        cfg: Configuration dictionary to validate and apply.
        save: If True, persist ``cfg`` to the default configuration path only after
            successful system reconciliation and sshd restart. If False, an existing
            configuration file is required.

    Returns:
        Tuple[bool, Optional[str]]: ``(True, None)`` on success, otherwise
        ``(False, error_message)``.
    """
    log.info("Applying configuration changes via sftpmanager ...")

    if cfg is None:
        return False, TXT_SFTP_HLP_NO_CONFIG

    log.info("Checking configuration validity before applying...")
    ok, msg = check_config_valid(cfg)
    if not ok:
        return False, TXT_SFTP_HLP_CONFIG_VALIDATION_FAILED.format(error=msg)

    cfg_path = getDefaultEtcConfigPath()
    if not save:
        exists, cfg_path = check_config_exists()
        if not exists:
            return False, TXT_SFTP_HLP_CONFIG_PATH_FAILED.format(path=cfg_path)

    if config_requires_cifs(cfg) and not cifs_exists():
        return False, TXT_SFTP_HLP_CIFS_MISSING

    apply_error: Optional[str] = None
    transaction_ok = True

    smbHelp.beginBatch()
    try:
        log.info("Applying configuration via sftpmanager lib from in-memory desired state.")
        create_errors: List[str] = []
        created_users = createUserFromJson(cfg=cfg, errors_out=create_errors)
        expected_users = len(cfg.get("users", []))
        if not created_users:
            detail = create_errors[-1] if create_errors else TXT_SFTP_HLP_NO_USERS_PROCESSED
            apply_error = TXT_SFTP_HLP_NO_USERS_PROCESSED_DETAIL.format(error=detail)
        elif len(created_users) != expected_users:
            detail = create_errors[-1] if create_errors else TXT_SFTP_HLP_NO_USERS_PROCESSED
            apply_error = TXT_SFTP_HLP_USERS_PARTIAL_DETAIL.format(
                created=len(created_users),
                expected=expected_users,
                error=detail,
            )

    except Exception as e:
        apply_error = TXT_SFTP_HLP_APPLY_FAILED.format(error=e)
    finally:
        transaction_ok = smbHelp.endBatch()

    if not transaction_ok:
        transaction_error = smbHelp.lastError
        if isinstance(transaction_error, ManagedCIFSTargetNotEmptyError):
            return False, TXT_SFTP_HLP_SAMBA_TARGET_NOT_EMPTY.format(
                path=transaction_error.target
            )
        if transaction_error is not None:
            return False, TXT_SFTP_HLP_SAMBA_TRANSACTION_FAILED_DETAIL.format(
                error=transaction_error
            )
        return False, TXT_SFTP_HLP_SAMBA_TRANSACTION_FAILED
    if apply_error is not None:
        return False, apply_error

    # Destructive user cleanup runs after the Samba/CIFS batch is physically
    # finalized. The complete local home is then mount-free and can be archived
    # without pulling data from the real mounted source directories into backup.
    try:
        backup_root = _get_sftp_backup_root(create=True)
        log.info("Uninstalling unwanted users with pre-delete home backups...")
        if not uninstallUnwantedUsers(cfg=cfg, backup_root=backup_root):
            return False, TXT_SFTP_HLP_UNINSTALL_UNWANTED_FAILED
    except Exception as e:
        return False, TXT_SFTP_HLP_APPLY_FAILED.format(error=e)

    log.info("Restarting sshd after SFTP configuration changes...")
    if not restart_sshd():
        return False, TXT_SFTP_HLP_SSHD_RESTART_FAILED

    if save:
        try:
            save_config(cfg, cfg_path)
        except Exception as e:
            return False, TXT_SFTP_HLP_SAVE_CONFIG_FAILED.format(error=e)

    return True, None

def uninstall_all_users(user:str=None) -> Tuple[bool, Optional[str]]:
    """Uninstall all users by invoking ``sftpmanager.py uninstall`` config není potřeba, ani žádné přepínače, automaticky je to all
    
    Args:
        user: Optional username to uninstall.  If not provided, all users will be uninstalled.
            Pokud je použit user tak se používá argument --user pro sftpmanager.py

    Returns:
        Tuple[bool, Optional[str]]: První prvek je True pokud se změny úspěšně aplikovaly, jinak False. Druhý prvek je chybová zpráva pokud se změny nepodařilo aplikovat, jinak None.
        
    """
    # Potential locations for the sftpmanager.py script.  Adjust these
    # paths if you have installed the script elsewhere.
    
    try:
        backup_root = _get_sftp_backup_root(create=True)
        if unInstAll(backup_root=backup_root):
            return True, None
        else:
            return False, TXT_SFTP_HLP_UNINSTALL_USERS_FAILED
                
    except Exception as e:
        log.error(f"Failed to uninstall SFTP users: {e}")
        log.exception(e)
        return False, TXT_SFTP_HLP_UNINSTALL_USERS_EXCEPTION.format(error=e)
