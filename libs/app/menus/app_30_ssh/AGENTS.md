# SSH Manager instructions

- Key delivery uses the shared `libs.app.mail_hlp` SMTP wrapper and `libs.app.ssh_key_bundle`; do not implement another SMTP client or ZIP writer in this menu.
- The recipient for a system user is stored in the user-owned XDG file `~/.config/jb_sys_apps/contact.jsonc` through `libs.app.user_contact`. Keep the directory mode `0700`, file mode `0600`, and ownership assigned to that system user.
- Contact configuration contains no SMTP credentials and no SSH key material. Key files are read from the current `~/.ssh/sshManager` state only when a mail is sent.
- Imported public-only keys use a dummy private file internally. Never attach that placeholder as a private key; send a public-only ZIP instead.
- Key material must not appear in text/HTML mail bodies or logs. The ZIP README may document default SFTP port 22, Total Commander and WinSCP usage, but must not include a concrete server host.
- WinSCP uses only the private key. Total Commander Secure FTP/SFTP requires both private and public key files. Password remains empty unless delivered separately.
- Samba-backed SFTP sandbox permissions are server-controlled; the README may explain that WinSCP permission warnings are expected and can be disabled.
