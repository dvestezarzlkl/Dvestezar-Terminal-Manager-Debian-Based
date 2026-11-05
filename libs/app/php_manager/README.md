# PHP Manager – read-only bootstrap

Project: Redmine #3550, first analysis #3551, inventory #3552.

The initial implementation **only inspects PHP CLI executables**. No package
management, php.ini writes, FPM/service control, ISPConfig DB/API access or
configuration synchronization is implemented.

Usage:

```bash
python3 php_mng.py
python3 php_mng.py --json
python3 -m unittest tests/test_php_manager_discovery.py
```

The discovery intentionally reports a CLI-only scope. PHP CLI modules cannot
be assumed to equal PHP-FPM modules, configured FPM pools or ISPConfig web
assignments. Subsequent work will inventory FPM/CGI separately; discover exact
runtime paths; export YAML; then add explicit dry-run ISPConfig integration
and build/rollback features. No automated updates are permitted in this phase.

Planned design: shared backend in libs/app/php_manager, thin php_mng.py CLI,
optional c_menu app_* frontend. Owned PHP builds will live under /opt/phpsys;
ISPConfig keeps authority over per-website pools. Managed records will use
visible `sys_app PHP 8.2 FPM` names plus durable ownership identities.
