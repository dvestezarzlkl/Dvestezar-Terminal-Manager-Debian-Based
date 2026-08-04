# Node-RED Manager instructions

- A Node-RED handover mail is an operational identification protocol, not a password-delivery channel. Never include plaintext passwords, bcrypt hashes, credential secrets, SMTP credentials, or private keys in its data model, text body, HTML body, attachments, or logs.
- Passwords are delivered through a separate channel. The protocol must say this explicitly.
- Build the instance URL from global `cfg.SERVER_URL` and the actual instance port. Use HTTPS only when the selected instance has configured or self-signed HTTPS.
- Read the Node-RED version from the selected instance package and the Node.js version in the selected system user's execution context; do not substitute the root/global shell version blindly.
- Node-RED projects are stored under the selected user's `.node-red` directory. Read `.config.projects.json` as that user, validate `activeProject` as a single safe path component, and inspect `projects/<activeProject>` as that user.
- Git remotes in mail are identification data only. Strip embedded URL credentials, query strings, and fragments before rendering or logging them.
- Device identity must reuse the existing application model: `cfg.machineInfo` plus the system disk PUUID and custom disk/image name from `libs.app.disk_hlp.disk_settings`. Do not introduce a parallel hardware-ID mechanism.
- One Node-RED instance maps to one system user. Store its delivery contact through the existing user-owned XDG file `~/.config/jb_sys_apps/contact.jsonc` and the hardened `libs.app.user_contact` helper.
- The protocol should contain service state, Node-RED and Node.js versions, system user, configured Node-RED admin users with RW/R access, optional dashboard user, active project, sanitized Git remote, hostname/FQDN, machine-id, system disk identity, generated timestamp, and SysApp version.
- Menu text belongs in `lng/default.py` and `lng/cs-CZ.py`. Keep the implementation in a testable helper and the menu callbacks thin.
