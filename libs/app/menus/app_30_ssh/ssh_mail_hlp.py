from __future__ import annotations

import html
from typing import List, Optional, Tuple

from .lng.default import *
from libs.JBLibs.helper import loadLng

loadLng()

from libs.app import cfg as app_cfg
from libs.app import mail_hlp, ssh_key_bundle


def build_key_mail_payload(
    username: str,
    key_name: str,
    public_key: str,
    private_key: str,
    recipient: str,
) -> Tuple[str, str, str, List[mail_hlp.MailAttachment]]:
    """Build a localized SSH key delivery mail and in-memory ZIP attachment."""
    label = f"{username}_{key_name}"
    names = ssh_key_bundle.build_bundle_names(label, public_key, "ssh_keys")

    if private_key:
        private_line = TXT_SSH_MAIL_README_PRIVATE_LINE.format(
            private_filename=names.private_filename
        )
        private_protection = TXT_SSH_MAIL_PRIVATE_PROTECTION
        client_instructions = TXT_SSH_MAIL_CLIENT_INSTRUCTIONS.format(
            private_usage=names.private_filename,
            public_filename=names.public_filename,
        )
    else:
        private_line = TXT_SSH_MAIL_README_NO_PRIVATE_LINE
        private_protection = ""
        client_instructions = TXT_SSH_MAIL_CLIENT_INSTRUCTIONS_PUBLIC_ONLY

    generated_by = TXT_SSH_MAIL_GENERATED_BY.format(
        version=getattr(app_cfg, "VERSION", "")
    )
    readme = TXT_SSH_MAIL_README.format(
        username=username,
        key_name=key_name,
        access_purpose=TXT_SSH_MAIL_ACCESS_PURPOSE,
        public_filename=names.public_filename,
        private_line=private_line,
        private_protection=private_protection,
        client_instructions=client_instructions.strip(),
        generated_by=generated_by,
    )

    try:
        attachment = ssh_key_bundle.create_key_bundle_attachment(
            names,
            public_key,
            private_key,
            readme,
        )
    except Exception as exc:
        raise ValueError(TXT_SSH_MAIL_ZIP_FAILED.format(error=exc)) from exc

    subject = TXT_SSH_MAIL_SUBJECT.format(username=username, key_name=key_name)
    subject += (
        TXT_SSH_MAIL_SUBJECT_PUBLIC_PRIVATE
        if private_key
        else TXT_SSH_MAIL_SUBJECT_PUBLIC
    )

    body_lines = [
        TXT_SSH_MAIL_EXPORT_FOR.format(username=username, key_name=key_name),
        TXT_SSH_MAIL_ACCESS_PURPOSE,
        TXT_SSH_MAIL_RECIPIENT.format(recipient=recipient),
        "",
        TXT_SSH_MAIL_ARCHIVE_ATTACHED.format(filename=names.archive_filename),
        TXT_SSH_MAIL_PRIVATE_WARNING
        if private_key
        else TXT_SSH_MAIL_NO_PRIVATE_KEY,
        "",
        generated_by,
    ]
    text_body = "\n".join(body_lines)

    html_body = "\n".join([
        "<html>",
        "  <body>",
        "    <p>{}</p>".format(
            html.escape(
                TXT_SSH_MAIL_EXPORT_FOR.format(
                    username=username,
                    key_name=key_name,
                )
            )
        ),
        "    <p>{}</p>".format(html.escape(TXT_SSH_MAIL_ACCESS_PURPOSE)),
        "    <p>{}</p>".format(
            html.escape(TXT_SSH_MAIL_RECIPIENT.format(recipient=recipient))
        ),
        "    <p>{}</p>".format(
            html.escape(
                TXT_SSH_MAIL_ARCHIVE_ATTACHED.format(
                    filename=names.archive_filename
                )
            )
        ),
        "    <p>{}</p>".format(
            html.escape(
                TXT_SSH_MAIL_PRIVATE_WARNING
                if private_key
                else TXT_SSH_MAIL_NO_PRIVATE_KEY
            )
        ),
        "    <p>{}</p>".format(html.escape(generated_by)),
        "  </body>",
        "</html>",
    ])

    return subject, text_body, html_body, [attachment]


def send_managed_key_by_mail(
    username: str,
    key_name: str,
    recipient: str,
) -> Tuple[bool, Optional[str]]:
    if not mail_hlp.is_valid_mail_address(recipient):
        return False, TXT_SSH_MAIL_INVALID_RECIPIENT

    ok, key_pair, error = ssh_key_bundle.read_managed_key_pair(username, key_name)
    if not ok or key_pair is None:
        return False, TXT_SSH_MAIL_KEY_READ_FAILED.format(error=error or "unknown error")

    public_key, private_key = key_pair
    try:
        subject, text_body, html_body, attachments = build_key_mail_payload(
            username,
            key_name,
            public_key,
            private_key,
            recipient,
        )
    except Exception as exc:
        return False, str(exc)

    return mail_hlp.send_mail(
        [recipient],
        subject,
        text_body,
        html_body=html_body,
        attachments=attachments,
    )
