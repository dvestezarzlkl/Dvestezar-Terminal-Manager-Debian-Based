# SFTP Manager Notes

- This menu uses `libs/app/menus/app_33_sftpmanagr/sftp_manager_hlp.py` for config and system actions.
- Config root metadata now includes optional `adminMail`.
- Each SFTP user may optionally carry a `mail` field.
- The user key submenu must support:
  - show public key
  - show private key when a stored pair contains it
  - send key by mail
  - delete key or certificate
- Sending mail uses the shared `libs.app.mail_hlp` SMTP transport.
- If the SFTP user admin mail is missing, the global fallback admin mail from `libs.app.mail_hlp` may be used.
- If neither app-specific admin mail nor fallback admin mail exists, mail actions must fail.
- Apply/save flows should keep using `apply_changes(cfg=self.cfg, save=True)` and must restart SSHD through the shared helper.
- Use `c_menu` properties like `choiceBack`, `choiceQuit`, and `ESC_is_quit` for submenu navigation instead of custom back/quit logic.
- Keep changes aligned with the existing `c_menu` patterns and avoid introducing new menu frameworks.
