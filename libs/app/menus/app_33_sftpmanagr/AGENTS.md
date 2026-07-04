# SFTP Manager Notes

- This menu uses `libs/app/menus/app_33_sftpmanagr/sftp_manager_hlp.py` for config and system actions.
- Config root metadata now includes optional `adminMail`.
- Each SFTP user may optionally carry a `mail` field.
- The user key submenu must support:
  - show public key
  - show private key when a stored pair contains it
  - send key by mail
  - delete key or certificate
- Sending mail relies on the configured admin mail; if it is missing, mail actions must fail.
- Apply/save flows should keep using `apply_changes(cfg=self.cfg, save=True)` and must restart SSHD through the shared helper.
- Use `c_menu` properties like `choiceBack`, `choiceQuit`, and `ESC_is_quit` for submenu navigation instead of custom back/quit logic.
- Keep changes aligned with the existing `c_menu` patterns and avoid introducing new menu frameworks.
