# Plugin system and self-updater

This document defines the interface between the repository plugin catalog, local plugin state, Git submodules and access-token files.

## Sources of truth

The plugin system intentionally separates four concerns:

| Source | Purpose | Committed |
|---|---|---:|
| `.gitmodules` | Git submodule path and repository URL | yes |
| `pluginy.jsonc` | Plugin metadata and default update policy | yes |
| `/etc/jb_sys_apps/plugins.jsonc` | Local enable/disable state for one installation | no |
| `assets/tokens/<token_id>.cd` | Local Git credentials | no, ignored by Git |

`.gitmodules` is authoritative for the actual submodule path and URL. A plugin entry in `pluginy.jsonc` does not dynamically create an arbitrary repository; its resolved path must also exist in `.gitmodules`.

## `pluginy.jsonc` catalog interface

The root JSONC object is indexed by a stable `plugin_id`. The same ID is used for the token filename and local-state key.

```jsonc
{
    "sys_apps_zlkl_plugin": {
        "adr_name": "app_50_zlkl",
        "git_repo_name": "sys_apps_zlkl_plugin",
        "git_repo_branch": "main",
        "git_repo_user": "dvestezarzlkl",
        "description": "ZLKL Plugin pro správu ZLKL nastavení a služeb",
        "private": true,
        "optional": true,
        "auto_update": true,
        "enabled_by_default": true,
        "licence": "ZLKL licence",
        "access": {
            "type": "token"
        },
        "maintainer": {
            "name": "Jan Zedník",
            "email": "zednik@zlkl.cz",
            "company": "ZLKL, s.r.o."
        }
    }
}
```

### Fields

| Field | Required | Type | Meaning |
|---|---:|---|---|
| object key / `plugin_id` | yes | string | Stable ID; used by local state and `<plugin_id>.cd` token file. |
| `adr_name` | yes | string | Directory name below `libs/app/menus`; the resulting path must exist in `.gitmodules`. |
| `git_repo_name` | metadata | string | Repository name for documentation and future validation. `.gitmodules` remains authoritative. |
| `git_repo_branch` | metadata | string | Intended repository branch, normally `main`. The updater installs the exact gitlink commit recorded by the main repository, not a moving remote head. |
| `git_repo_user` | metadata | string | GitHub owner or organization. |
| `description` | no | string | Human-readable description shown in plugin settings. |
| `private` | no | boolean | Whether the plugin normally requires authenticated access. Default: `false`. |
| `optional` | no | boolean | `true`: failure becomes a warning and core update continues. `false`: failure stops the whole update. Default: `true`. |
| `auto_update` | no | boolean | Whether `Update me` may install/update this plugin. Default: `true`. |
| `enabled_by_default` | no | boolean | Used only when no local override exists. Default: `true`. |
| `access.type` | no | string | Currently supported value: `token`. A private token plugin uses `assets/tokens/<plugin_id>.cd`. |
| `licence` | no | string | Informational license text. |
| `maintainer` | no | object | Informational maintainer contact. |

Unknown metadata fields may be preserved; updater behavior must depend only on documented policy fields.

## Local state: `/etc/jb_sys_apps/plugins.jsonc`

Local state must never be stored in the repository because it differs per installation and would make the Git working tree dirty.

```jsonc
{
    "sys_apps_zlkl_plugin": {
        "enabled": false
    }
}
```

Rules:

- missing plugin key: use `enabled_by_default` from the catalog;
- `enabled: true`: updater may install/update it and the dynamic menu loader may load it;
- `enabled: false`: updater skips it and the dynamic menu loader hides it after application restart;
- local `enabled: false` has higher priority than an existing token;
- uninstall writes `enabled: false`, deinitializes the local submodule and preserves the token.

## Token files

Token files are stored in `assets/tokens/` and are ignored by Git.

```text
assets/tokens/sys_apps_zlkl_plugin.cd
```

Content is one logical line:

```text
username:token
```

A final newline is allowed. The file is written with mode `0600`. Token values are never displayed in menus, logs, diffs or error messages.

Reserved token IDs:

| Token ID | Purpose |
|---|---|
| `sys_apps` | Optional credentials for the main sys_apps repository. |
| `JBLibs-python` | Optional credentials for the mandatory JBLibs repository; falls back to `sys_apps.cd`. |
| `<plugin_id>` | Credentials for one catalog plugin. |

For a private plugin with `access.type: token`:

- enabled + token present: install/update;
- enabled + token absent + not installed: warning for optional plugin, error for required plugin;
- enabled + token absent + already installed: skip authenticated update with warning/error according to `optional`;
- disabled: skip regardless of token presence.

## Update transaction

`Update me` performs these stages in order:

1. reject tracked local changes in the main repository and relevant enabled submodules;
2. update the main repository with `git pull --ff-only` and without recursive submodule processing;
3. synchronize and install the mandatory `libs/JBLibs` gitlink commit;
4. process enabled catalog plugins individually;
5. treat optional-plugin failures as warnings instead of breaking core update;
6. run `setup.sh --no-run` to update system and Python dependencies without starting a nested application instance;
7. print a step/warning/error summary and exit so the next application start loads the new code.

The mandatory JBLibs gitlink is verified after update. A main-repository/JBLibs version mismatch is a fatal update error.

## Plugin settings menu

The plugin settings menu shows a fixed-width table modeled after `app_10_disk`:

```text
Plugin                           | Enabled | Installed |  Token  | Auto
------------------------------------------------------------------------
sys_apps_zlkl_plugin             |   yes   |    yes    |   yes   | yes
```

The plugin detail menu provides:

- enable;
- disable without deleting local files;
- uninstall local submodule while preserving its token;
- set/replace/remove the plugin token;
- status fields for installation, access and update policy.

Repository token settings for `sys_apps` and `JBLibs-python` are available in the same settings area.

## Adding a new plugin

1. Add the submodule to `.gitmodules` under `libs/app/menus/app_<order>_<name>`.
2. Add a matching entry to `pluginy.jsonc`.
3. Ensure `adr_name` exactly matches the directory component from `.gitmodules`.
4. For private access, set `private: true` and `access.type: "token"`.
5. Decide explicitly whether the plugin is `optional` and `enabled_by_default`.
6. Add its token through the plugin settings menu or create `assets/tokens/<plugin_id>.cd` locally.
7. Run `Update me`, restart sys_apps and verify the plugin appears only when enabled.

## Removing a plugin from the product

First disable or uninstall it on affected installations. Then remove its catalog entry and submodule in a coordinated main-repository change. Do not silently reuse an old `plugin_id` for an unrelated plugin because local state and token files are keyed by that ID.
