from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from libs.JBLibs.fs_utils import lsblkDiskInfo, normalizeDiskPath
from libs.JBLibs.helper import getLogger
from libs.app.disk_hlp import disk_settings


log = getLogger("disk_ptuuid")

STATE_DIR = Path("/etc/jb_sys_apps/ptuuid-change")
PENDING_JSON = STATE_DIR / "pending.json"
PENDING_ENV = STATE_DIR / "pending.env"
GPT_BACKUP = STATE_DIR / "layout-before-change.gpt"
LAST_RESULT_JSON = STATE_DIR / "last-result.json"

INITRAMFS_HOOK = Path("/etc/initramfs-tools/hooks/sysapps-ptuuid")
INITRAMFS_SCRIPT = Path(
    "/etc/initramfs-tools/scripts/local-premount/sysapps-ptuuid"
)
FINALIZE_SERVICE = Path("/etc/systemd/system/sysapps-ptuuid-finalize.service")
FINALIZE_SERVICE_NAME = FINALIZE_SERVICE.name

_INITRAMFS_PENDING_ENTRY = "conf/sysapps-ptuuid/pending.env"
_INITRAMFS_SCRIPT_ENTRY = "scripts/local-premount/sysapps-ptuuid"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _normalize_uuid(value: str | None) -> str:
    return str(value or "").strip().lower()


def _sudo(command: list[str]) -> list[str]:
    if os.geteuid() == 0:
        return command
    return ["sudo", *command]


def _run(
    command: list[str],
    *,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=capture,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(
            f"Příkaz selhal ({result.returncode}): {' '.join(command)}"
            + (f"\n{detail}" if detail else "")
        )
    return result


def _require_command(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"Chybí požadovaný systémový příkaz: {name}")
    return path


def _install_text(path: Path, content: str, mode: int) -> None:
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        delete=False,
    ) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    try:
        _run(
            _sudo(
                [
                    "install",
                    "-D",
                    "-m",
                    f"{mode:o}",
                    str(temp_path),
                    str(path),
                ]
            )
        )
    finally:
        temp_path.unlink(missing_ok=True)


def _remove_privileged(path: Path) -> None:
    _run(_sudo(["rm", "-f", str(path)]))


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    if not isinstance(data, dict):
        raise ValueError(f"Soubor {path} neobsahuje JSON objekt.")
    return data


def _read_ptuuid(device: str) -> str:
    result = _run(["lsblk", "-ndo", "PTUUID", device])
    return _normalize_uuid(result.stdout)


def _read_size_bytes(device: str) -> int:
    result = _run(["blockdev", "--getsize64", device])
    try:
        return int(result.stdout.strip())
    except ValueError as exc:
        raise RuntimeError(f"Nelze zjistit velikost zařízení {device}.") from exc


def _read_partuuids(device: str) -> dict[str, str]:
    result = _run(["lsblk", "-nrpo", "NAME,TYPE,PARTUUID", device])
    partitions: dict[str, str] = {}
    for raw_line in result.stdout.splitlines():
        fields = raw_line.split()
        if len(fields) < 2 or fields[1] != "part":
            continue
        partitions[fields[0]] = _normalize_uuid(
            fields[2] if len(fields) > 2 else ""
        )
    return partitions


def _verify_gpt(device: str) -> None:
    _run(_sudo(["sgdisk", "--verify", device]))


def _active_initramfs_path() -> Path:
    kernel = _run(["uname", "-r"]).stdout.strip()
    if not kernel:
        raise RuntimeError("Nelze zjistit verzi právě běžícího kernelu.")
    path = Path(f"/boot/initrd.img-{kernel}")
    if not path.is_file():
        raise RuntimeError(
            f"Pro právě běžící kernel nebyl nalezen initramfs {path}."
        )
    return path


def _verify_initramfs_payload(*, expect_pending: bool) -> None:
    initramfs = _active_initramfs_path()
    listing = _run(_sudo(["lsinitramfs", str(initramfs)])).stdout.splitlines()
    entries = {line.strip().lstrip("./") for line in listing if line.strip()}

    if _INITRAMFS_SCRIPT_ENTRY not in entries:
        raise RuntimeError(
            f"Initramfs {initramfs} neobsahuje SysApps PTUUID boot script."
        )
    has_pending = _INITRAMFS_PENDING_ENTRY in entries
    if has_pending != expect_pending:
        expected = "obsahovat" if expect_pending else "neobsahovat"
        raise RuntimeError(
            f"Initramfs {initramfs} má {expected} připravený PTUUID stav."
        )


def get_pending_change(device_name: str | None = None) -> dict[str, Any] | None:
    state = _read_json(PENDING_JSON)
    if state is None:
        return None
    if device_name is None:
        return state
    expected = normalizeDiskPath(device_name, False)
    if state.get("device") != expected:
        return None
    return state


def build_initramfs_hook() -> str:
    return """#!/bin/sh
PREREQ=""
prereqs()
{
    echo "$PREREQ"
}
case "$1" in
prereqs)
    prereqs
    exit 0
    ;;
esac

. /usr/share/initramfs-tools/hook-functions

STATE=/etc/jb_sys_apps/ptuuid-change/pending.env
[ -r "$STATE" ] || exit 0

mkdir -p "${DESTDIR}/conf/sysapps-ptuuid"
cp "$STATE" "${DESTDIR}/conf/sysapps-ptuuid/pending.env"
chmod 0600 "${DESTDIR}/conf/sysapps-ptuuid/pending.env"

for command_name in sgdisk blkid blockdev tr; do
    command_path="$(command -v "$command_name" || true)"
    if [ -z "$command_path" ]; then
        echo "sysapps-ptuuid: missing command $command_name" >&2
        exit 1
    fi
    copy_exec "$command_path"
done

exit 0
"""


def build_initramfs_boot_script() -> str:
    return """#!/bin/sh
PREREQ=""
prereqs()
{
    echo "$PREREQ"
}
case "$1" in
prereqs)
    prereqs
    exit 0
    ;;
esac

. /scripts/functions

PATH=/usr/sbin:/usr/bin:/sbin:/bin
STATE=/conf/sysapps-ptuuid/pending.env
[ -r "$STATE" ] || exit 0
. "$STATE"

[ "${ENABLED:-0}" = "1" ] || exit 0

verify_partuuids()
{
    index=1
    [ "${PART_COUNT:-0}" -gt 0 ] 2>/dev/null || return 1
    while [ "$index" -le "$PART_COUNT" ]; do
        eval "PART_DEVICE=\${PART_${index}_DEVICE:-}"
        eval "EXPECTED_PARTUUID=\${PART_${index}_UUID:-}"
        [ -n "$PART_DEVICE" ] || return 1
        [ -n "$EXPECTED_PARTUUID" ] || return 1
        [ -b "$PART_DEVICE" ] || return 1
        CURRENT_PARTUUID="$(blkid -p -s PARTUUID -o value "$PART_DEVICE" 2>/dev/null | tr '[:upper:]' '[:lower:]')"
        [ "$CURRENT_PARTUUID" = "$EXPECTED_PARTUUID" ] || return 1
        index=$((index + 1))
    done
    return 0
}

if [ ! -b "$DEVICE" ]; then
    log_warning_msg "SysApps PTUUID: zařízení $DEVICE neexistuje; změna přeskočena."
    exit 0
fi

CURRENT_PTUUID="$(blkid -p -s PTUUID -o value "$DEVICE" 2>/dev/null | tr '[:upper:]' '[:lower:]')"
if [ "$CURRENT_PTUUID" = "$NEW_PTUUID" ]; then
    log_begin_msg "SysApps PTUUID: disk už používá připravené PTUUID"
    log_end_msg 0
    exit 0
fi
if [ "$CURRENT_PTUUID" != "$OLD_PTUUID" ]; then
    log_warning_msg "SysApps PTUUID: původní PTUUID nesouhlasí; změna přeskočena."
    exit 0
fi

CURRENT_SIZE="$(blockdev --getsize64 "$DEVICE" 2>/dev/null || true)"
if [ "$CURRENT_SIZE" != "$SIZE_BYTES" ]; then
    log_warning_msg "SysApps PTUUID: velikost disku nesouhlasí; změna přeskočena."
    exit 0
fi

if ! verify_partuuids; then
    log_warning_msg "SysApps PTUUID: PARTUUID před změnou nesouhlasí; změna přeskočena."
    exit 0
fi

if ! sgdisk --verify "$DEVICE" >/dev/null 2>&1; then
    log_warning_msg "SysApps PTUUID: GPT před změnou neprošla kontrolou; změna přeskočena."
    exit 0
fi

log_begin_msg "SysApps PTUUID: měním pouze GPT disk GUID na $NEW_PTUUID"
if ! sgdisk --disk-guid="$NEW_PTUUID" "$DEVICE" >/dev/null 2>&1; then
    log_failure_msg "SysApps PTUUID: zápis nového disk GUID selhal."
    exit 0
fi

sync
blockdev --rereadpt "$DEVICE" >/dev/null 2>&1 || true

if ! sgdisk --verify "$DEVICE" >/dev/null 2>&1; then
    log_warning_msg "SysApps PTUUID: GPT po změně neprošla kontrolou. Boot pokračuje."
    exit 0
fi
if ! verify_partuuids; then
    log_warning_msg "SysApps PTUUID: PARTUUID se po změně liší. Boot pokračuje."
    exit 0
fi

log_end_msg 0
exit 0
"""


def _systemd_quote(value: str | Path) -> str:
    text = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def build_finalize_service(
    app_root: Path,
    python_executable: Path,
) -> str:
    return f"""[Unit]
Description=Finalize SysApps one-shot PTUUID change
After=local-fs.target
ConditionPathExists={PENDING_JSON}

[Service]
Type=oneshot
WorkingDirectory={_systemd_quote(app_root)}
ExecStart={_systemd_quote(python_executable)} -m libs.app.menus.app_10_disk.ptuuid_repair --finalize

[Install]
WantedBy=multi-user.target
"""


def _pending_env(state: dict[str, Any], enabled: bool = True) -> str:
    partuuids = dict(state.get("partuuids", {}))
    values: dict[str, str] = {
        "ENABLED": "1" if enabled else "0",
        "DEVICE": str(state["device"]),
        "OLD_PTUUID": str(state["old_ptuuid"]),
        "NEW_PTUUID": str(state["new_ptuuid"]),
        "SIZE_BYTES": str(state["size_bytes"]),
        "PART_COUNT": str(len(partuuids)),
    }
    for index, (device, partuuid) in enumerate(
        sorted(partuuids.items()),
        start=1,
    ):
        values[f"PART_{index}_DEVICE"] = str(device)
        values[f"PART_{index}_UUID"] = str(partuuid)
    return "".join(
        f"{key}={shlex.quote(value)}\n" for key, value in values.items()
    )


def _rebuild_initramfs(*, expect_pending: bool) -> None:
    _run(_sudo(["update-initramfs", "-u"]), capture=False)
    _verify_initramfs_payload(expect_pending=expect_pending)


def _disarm_and_clean_pending_state(
    state: dict[str, Any],
    *,
    remove_json: bool,
) -> None:
    _install_text(PENDING_ENV, _pending_env(state, enabled=False), 0o600)
    _rebuild_initramfs(expect_pending=True)
    _remove_privileged(PENDING_ENV)
    _rebuild_initramfs(expect_pending=False)
    if remove_json:
        _remove_privileged(PENDING_JSON)
    _run(
        _sudo(["systemctl", "disable", FINALIZE_SERVICE_NAME]),
        check=False,
    )


def prepare_system_disk_change(
    disk: lsblkDiskInfo,
    new_ptuuid: str,
    *,
    app_root: Path | None = None,
    python_executable: Path | None = None,
) -> dict[str, Any]:
    if disk is None or not disk.isSystemDisk:
        raise ValueError("One-shot PTUUID lze připravit pouze pro systémový disk.")
    if disk.type != "disk":
        raise ValueError("Vybrané systémové zařízení není disk.")
    if get_pending_change() is not None:
        raise RuntimeError("Jiná změna PTUUID už čeká na restart.")

    for command in (
        "sgdisk",
        "update-initramfs",
        "lsinitramfs",
        "systemctl",
        "blkid",
        "blockdev",
    ):
        _require_command(command)
    if not Path("/usr/share/initramfs-tools/hook-functions").is_file():
        raise RuntimeError("initramfs-tools hook-functions nejsou dostupné.")

    device = normalizeDiskPath(disk.name, False)
    old_ptuuid = _normalize_uuid(disk.ptuuid)
    new_ptuuid = _normalize_uuid(new_ptuuid)
    try:
        old_ptuuid = str(uuid.UUID(old_ptuuid))
        new_ptuuid = str(uuid.UUID(new_ptuuid))
    except ValueError as exc:
        raise ValueError("Zdrojové i nové PTUUID musí být platné GPT UUID.") from exc
    if old_ptuuid == new_ptuuid:
        raise ValueError("Nové PTUUID je stejné jako původní.")

    current_ptuuid = _read_ptuuid(device)
    if current_ptuuid != old_ptuuid:
        raise RuntimeError(
            f"Aktuální PTUUID {current_ptuuid or '-'} neodpovídá očekávanému {old_ptuuid}."
        )

    size_bytes = _read_size_bytes(device)
    partuuids = _read_partuuids(device)
    if not partuuids or any(not value for value in partuuids.values()):
        raise RuntimeError(
            "Na systémovém GPT disku nebyla zjištěna platná PARTUUID všech partition."
        )
    _verify_gpt(device)
    _active_initramfs_path()

    state: dict[str, Any] = {
        "version": 1,
        "status": "pending",
        "created_at": _utc_now(),
        "device": device,
        "device_name": disk.name,
        "old_ptuuid": old_ptuuid,
        "new_ptuuid": new_ptuuid,
        "size_bytes": size_bytes,
        "partuuids": partuuids,
    }

    if app_root is None:
        app_root = Path(__file__).resolve().parents[4]
    if python_executable is None:
        python_executable = Path(sys.executable).absolute()

    _run(_sudo(["install", "-d", "-m", "0755", str(STATE_DIR)]))
    _run(_sudo(["sgdisk", f"--backup={GPT_BACKUP}", device]))

    try:
        # Infrastruktura se instaluje dříve než pending stav. Chyba v této
        # fázi proto ještě nemůže vložit aktivní payload do initramfs.
        _install_text(INITRAMFS_HOOK, build_initramfs_hook(), 0o755)
        _install_text(INITRAMFS_SCRIPT, build_initramfs_boot_script(), 0o755)
        _install_text(
            FINALIZE_SERVICE,
            build_finalize_service(app_root, python_executable),
            0o644,
        )
        _run(_sudo(["systemctl", "daemon-reload"]))
        _install_text(
            PENDING_JSON,
            json.dumps(state, indent=2, sort_keys=True) + "\n",
            0o644,
        )
        _install_text(PENDING_ENV, _pending_env(state, enabled=False), 0o600)

        # Nejprve se ověří, že lze sestavit initramfs s deaktivovaným stavem.
        _rebuild_initramfs(expect_pending=True)

        # Finalizer se zapne ještě před armingem. I při výpadku uprostřed
        # přípravy tak další boot buď nic nezmění, nebo výsledek ověří.
        _run(_sudo(["systemctl", "enable", FINALIZE_SERVICE_NAME]))

        # Teprve druhý atomický rebuild vloží do initramfs aktivní payload.
        _install_text(PENDING_ENV, _pending_env(state, enabled=True), 0o600)
        _rebuild_initramfs(expect_pending=True)
    except Exception as exc:
        try:
            if PENDING_ENV.exists():
                _disarm_and_clean_pending_state(state, remove_json=True)
            else:
                _remove_privileged(PENDING_JSON)
                _run(
                    _sudo(["systemctl", "disable", FINALIZE_SERVICE_NAME]),
                    check=False,
                )
        except Exception as disarm_exc:
            raise RuntimeError(
                "Příprava změny PTUUID selhala a nepodařilo se bezpečně "
                "deaktivovat initramfs payload. NERESTARTUJTE zařízení, dokud "
                "nebude stav ručně zkontrolován. "
                f"Původní chyba: {exc}; chyba deaktivace: {disarm_exc}"
            ) from exc
        raise

    return state


def cancel_pending_change(device_name: str | None = None) -> dict[str, Any]:
    state = get_pending_change(device_name)
    if state is None:
        raise RuntimeError("Pro vybraný disk není připravená změna PTUUID.")

    _disarm_and_clean_pending_state(state, remove_json=False)

    result = dict(state)
    result.update(
        {
            "status": "cancelled",
            "finished_at": _utc_now(),
            "message": "Připravená změna PTUUID byla zrušena před restartem.",
        }
    )
    _install_text(
        LAST_RESULT_JSON,
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        0o644,
    )
    _remove_privileged(PENDING_JSON)
    return result


def _transfer_local_disk_name(old_ptuuid: str, new_ptuuid: str) -> None:
    disk_settings.init()
    old_key = disk_settings.normalize_ptuuid(old_ptuuid)
    new_key = disk_settings.normalize_ptuuid(new_ptuuid)
    if old_key not in disk_settings.diskNames:
        return

    old_name = disk_settings.diskNames[old_key]
    old_updated = disk_settings.diskNameUpdatedAt.get(old_key)
    disk_settings.set_disk_name(
        new_key,
        old_name,
        updated_at=old_updated,
        save=False,
    )
    disk_settings.diskNames.pop(old_key, None)
    disk_settings.diskNameUpdatedAt.pop(old_key, None)
    disk_settings.save()


def finalize_pending_change() -> int:
    state = get_pending_change()
    if state is None:
        return 0

    device = str(state["device"])
    expected_new = _normalize_uuid(state["new_ptuuid"])
    expected_old = _normalize_uuid(state["old_ptuuid"])
    expected_size = int(state["size_bytes"])
    expected_partuuids = {
        str(name): _normalize_uuid(value)
        for name, value in dict(state.get("partuuids", {})).items()
    }

    errors: list[str] = []
    warnings: list[str] = []
    current_ptuuid = ""
    current_partuuids: dict[str, str] = {}
    try:
        current_ptuuid = _read_ptuuid(device)
        if current_ptuuid != expected_new:
            errors.append(
                "PTUUID po bootu neodpovídá připravené hodnotě "
                f"({current_ptuuid or '-'} != {expected_new})."
            )
        if _read_size_bytes(device) != expected_size:
            errors.append("Velikost systémového disku se změnila.")
        current_partuuids = _read_partuuids(device)
        if current_partuuids != expected_partuuids:
            errors.append("PARTUUID partition se proti stavu před restartem změnila.")
        try:
            _verify_gpt(device)
        except Exception as exc:
            errors.append(f"GPT po bootu neprošla kontrolou: {exc}")
    except Exception as exc:
        errors.append(str(exc))

    success = not errors

    if success:
        try:
            _transfer_local_disk_name(expected_old, expected_new)
        except Exception as exc:
            warnings.append(f"Přenos lokálního názvu disku selhal: {exc}")

    try:
        PENDING_ENV.unlink(missing_ok=True)
        _run(["update-initramfs", "-u"], capture=False)
        _verify_initramfs_payload(expect_pending=False)
    except Exception as exc:
        warnings.append(f"Odstranění pending payloadu z initramfs selhalo: {exc}")

    try:
        _run(["systemctl", "disable", FINALIZE_SERVICE_NAME], check=False)
    except Exception as exc:
        warnings.append(f"Deaktivace finalizační služby selhala: {exc}")

    result = dict(state)
    result.update(
        {
            "status": "success" if success else "failed",
            "finished_at": _utc_now(),
            "current_ptuuid": current_ptuuid,
            "current_partuuids": current_partuuids,
            "errors": errors,
            "warnings": warnings,
        }
    )

    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LAST_RESULT_JSON.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    PENDING_JSON.unlink(missing_ok=True)
    PENDING_ENV.unlink(missing_ok=True)

    if success:
        try:
            from libs.app.hub.runtime import hub_runtime

            hub_runtime.sync_provider_best_effort("disks")
        except Exception:
            log.warning("SysApps Hub sync failed after PTUUID change", exc_info=True)

    return 0 if success else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args(argv)
    if args.finalize:
        return finalize_pending_change()
    parser.error("Je vyžadován parametr --finalize.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
