from __future__ import annotations

import re
import smtplib
from email.message import EmailMessage
from typing import Iterable, List, Optional, Sequence, Tuple

from libs.JBLibs.helper import getLogger
from libs.app import cfg as app_cfg

log = getLogger("mail_hlp")

_MAIL_RGX = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
)

_SMTP_MODES = {"plain", "starttls", "ssl"}
_SMTP_DEFAULT_PORTS = {
    "plain": 25,
    "starttls": 587,
    "ssl": 465,
}


def is_valid_mail_address(mail: str) -> bool:
    """Return ``True`` if the value looks like a single email address."""
    if not isinstance(mail, str):
        return False
    return bool(_MAIL_RGX.match(mail.strip()))


def _get_str(name: str) -> str:
    value = getattr(app_cfg, name, "")
    if not isinstance(value, str):
        return ""
    return value.strip()


def _get_int(name: str, default: int = 0) -> int:
    value = getattr(app_cfg, name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_smtp_host() -> str:
    return _get_str("MAIL_SMTP_HOST")


def get_smtp_port() -> int:
    return _get_int("MAIL_SMTP_PORT", 0)


def get_smtp_user() -> str:
    return _get_str("MAIL_SMTP_USER")


def get_smtp_password() -> str:
    value = getattr(app_cfg, "MAIL_SMTP_PASSWORD", "")
    return value if isinstance(value, str) else ""


def get_smtp_mode() -> str:
    mode = _get_str("MAIL_SMTP_MODE").lower() or "starttls"
    return mode


def get_default_smtp_port(mode: Optional[str] = None) -> int:
    mode = (mode or get_smtp_mode()).lower()
    return _SMTP_DEFAULT_PORTS.get(mode, 587)


def is_smtp_port_mismatched(mode: Optional[str] = None, port: Optional[int] = None) -> bool:
    mode = (mode or get_smtp_mode()).lower()
    try:
        current_port = int(port if port is not None else get_smtp_port())
    except (TypeError, ValueError):
        return False
    if current_port <= 0:
        return False
    return current_port != get_default_smtp_port(mode)


def get_smtp_port_hint(mode: Optional[str] = None) -> str:
    mode = (mode or get_smtp_mode()).lower() or "starttls"
    lines = [
        "Doporučené SMTP porty:",
        "plain = 25",
        "STARTTLS = 587",
        "SSL = 465",
        "Pozor: port 993 je obvykle IMAPS, ne SMTP.",
        f"Výchozí port pro {mode.upper()} je {get_default_smtp_port(mode)}.",
    ]
    return "\n".join(lines)


def get_mail_from() -> str:
    mail_from = _get_str("MAIL_FROM")
    if mail_from:
        return mail_from
    return get_smtp_user()


def get_fallback_admin_mail() -> str:
    return _get_str("MAIL_FALLBACK_ADMIN")


def set_fallback_admin_mail(mail: str) -> Tuple[bool, Optional[str]]:
    """Store the app-wide fallback admin mail address."""
    if mail and not is_valid_mail_address(mail):
        return False, "Invalid fallback admin mail address."
    app_cfg.MAIL_FALLBACK_ADMIN = mail.strip().lower() if mail else ""
    return True, None


def get_effective_admin_mail(app_admin_mail: Optional[str] = None) -> str:
    """Return the app-specific admin mail or the global fallback one."""
    if isinstance(app_admin_mail, str):
        app_admin_mail = app_admin_mail.strip()
    if app_admin_mail:
        return app_admin_mail
    return get_fallback_admin_mail()


def get_config_status() -> Tuple[bool, str]:
    """Return SMTP configuration status and a human readable reason."""
    host = get_smtp_host()
    if not host:
        return False, "SMTP host is not configured."

    port = get_smtp_port()
    if port <= 0 or port > 65535:
        return False, "SMTP port is not configured."

    mode = get_smtp_mode()
    if mode not in _SMTP_MODES:
        return False, "SMTP mode must be plain, starttls, or ssl."

    user = get_smtp_user()
    pwd = get_smtp_password()
    if not user:
        return False, "SMTP user is not configured."
    if not pwd:
        return False, "SMTP password is not configured."

    mail_from = get_mail_from()
    if not mail_from or not is_valid_mail_address(mail_from):
        return False, "SMTP from address is not configured."

    return True, "SMTP configured."


def isConfigured() -> bool:
    """Return ``True`` if the application has SMTP settings ready."""
    ok, _ = get_config_status()
    return ok


def get_status_text() -> str:
    """Return a short status label for menus."""
    ok, reason = get_config_status()
    if ok:
        status = f"{get_smtp_host()}:{get_smtp_port()} {get_smtp_mode().upper()}"
        if is_smtp_port_mismatched():
            status += " !"
        return status
    return reason


def _unique_addresses(addresses: Iterable[str]) -> List[str]:
    unique: List[str] = []
    for addr in addresses:
        if not isinstance(addr, str):
            continue
        addr = addr.strip()
        if not addr or not is_valid_mail_address(addr):
            continue
        addr = addr.lower()
        if addr not in unique:
            unique.append(addr)
    return unique


def send_mail(
    recipients: Sequence[str],
    subject: str,
    body: str,
    html_body: Optional[str] = None,
    cc: Sequence[str] | None = None,
    bcc: Sequence[str] | None = None,
    reply_to: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Send a plain text email over configured SMTP.

    If ``html_body`` is provided, the message is sent as multipart/alternative
    with both plain text and HTML parts.
    """
    ok, reason = get_config_status()
    if not ok:
        return False, reason

    to_addrs = _unique_addresses(recipients)
    if cc:
        to_addrs.extend([addr for addr in _unique_addresses(cc) if addr not in to_addrs])
    if bcc:
        to_addrs.extend([addr for addr in _unique_addresses(bcc) if addr not in to_addrs])
    if not to_addrs:
        return False, "No mail recipients configured."

    from_addr = get_mail_from()
    msg = EmailMessage()
    msg["From"] = from_addr
    msg["To"] = ", ".join(_unique_addresses(recipients))
    if cc:
        cc_list = _unique_addresses(cc)
        if cc_list:
            msg["Cc"] = ", ".join(cc_list)
    if reply_to and is_valid_mail_address(reply_to):
        msg["Reply-To"] = reply_to.strip().lower()
    msg["Subject"] = subject
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    host = get_smtp_host()
    port = get_smtp_port()
    mode = get_smtp_mode()
    user = get_smtp_user()
    password = get_smtp_password()
    timeout = _get_int("MAIL_TIMEOUT", 20)

    try:
        if mode == "ssl":
            smtp = smtplib.SMTP_SSL(host, port, timeout=timeout)
        else:
            smtp = smtplib.SMTP(host, port, timeout=timeout)

        with smtp:
            smtp.ehlo()
            if mode == "starttls":
                smtp.starttls()
                smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg, from_addr=from_addr, to_addrs=to_addrs)
    except Exception as e:
        err = str(e)
        hint = ""
        if "IMAP4rev1" in err or "Dovecot" in err or "IMAP" in err.upper():
            hint = " The server replied like IMAP; SMTP SSL usually uses port 465 and STARTTLS uses 587."
        elif is_smtp_port_mismatched(mode, port):
            hint = f" The selected port {port} is unusual for {mode.upper()}; expected {get_default_smtp_port(mode)}."
        log.error(f"Failed to send mail via SMTP: {e}")
        return False, f"Failed to send mail via SMTP: {e}{hint}"

    return True, None


def send_test_mail(recipient: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """Send a small test mail to the provided recipient or fallback admin."""
    recipient = recipient or get_fallback_admin_mail()
    if not recipient:
        return False, "Fallback admin mail is not configured."

    subject = f"{getattr(app_cfg, 'SITE_NAME', 'Application')} mail test"
    body = "\n".join([
        "This is a test mail from the application mailing helper.",
        "",
        f"SMTP host: {get_smtp_host()}",
        f"SMTP mode: {get_smtp_mode()}",
        f"From: {get_mail_from()}",
    ])
    return send_mail([recipient], subject, body)
