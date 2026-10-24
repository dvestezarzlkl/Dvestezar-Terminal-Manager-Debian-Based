"""Guarded, manual UFW mutation for Firewall Manager.

This is the only module in app_40_firewall allowed to write /etc/ufw or invoke
live UFW enable/reload/disable commands. Hub collectors must never import it.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import tempfile
from typing import Callable
from uuid import uuid4

from .compiler import (
    CandidateResult,
    CompiledFirewall,
    DesiredBlock,
    build_candidate,
    compile_firewall,
    managed_digest,
)
from .config import FirewallConfig, normalize_config
from .hub_provider import inspect_ufw_service
from .policy import FirewallPolicyError


class FirewallApplyError(RuntimeError):
    pass


@dataclass(frozen=True)
class ApplyPaths:
    before4: Path = Path("/etc/ufw/before.rules")
    before6: Path = Path("/etc/ufw/before6.rules")
    state: Path = Path("/var/lib/jb_sys_apps/firewall/state.json")
    backups: Path = Path("/var/lib/jb_sys_apps/firewall/backups")


@dataclass(frozen=True)
class ApplyPlan:
    compiled: CompiledFirewall
    ipv4: CandidateResult
    ipv6: CandidateResult | None

    @property
    def changed(self) -> bool:
        return self.ipv4.changed or bool(self.ipv6 and self.ipv6.changed)


@dataclass(frozen=True)
class ApplyResult:
    status: str
    changed_files: bool
    activated: bool
    backup_dir: str = ""


Runner = Callable[..., subprocess.CompletedProcess[str]]
Acknowledge = Callable[[int], bool]


def _run(
    args: list[str],
    *,
    input_text: str | None = None,
    check: bool = True,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            input=input_text,
            text=True,
            capture_output=True,
            check=check,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = (exc.stderr or exc.stdout or "").strip()
        raise FirewallApplyError(
            f"Command failed: {args[0]}" + (f": {detail}" if detail else "")
        ) from exc


def _binary(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise FirewallApplyError(f"Required command is not available: {name}")
    return found


def _read_regular(path: Path, *, required: bool) -> str | None:
    if not path.exists():
        if required:
            raise FirewallApplyError(f"Required UFW file is missing: {path}")
        return None
    if path.is_symlink() or not path.is_file():
        raise FirewallApplyError(f"UFW path must be a regular file: {path}")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FirewallApplyError(f"Cannot read UFW file: {path}") from exc


def build_apply_plan(
    config: FirewallConfig,
    *,
    before4: str,
    before6: str | None,
) -> ApplyPlan:
    compiled = compile_firewall(config)
    ipv4 = build_candidate(before4, compiled.ipv4, allow_openvpn=True)
    ipv6: CandidateResult | None = None
    if before6 is not None:
        ipv6 = build_candidate(before6, compiled.ipv6, allow_openvpn=False)
    elif compiled.explicit_ipv6:
        raise FirewallPolicyError(
            "IPv6 firewall rule exists but /etc/ufw/before6.rules is unavailable."
        )
    return ApplyPlan(compiled, ipv4, ipv6)


def _validation_payload(blocks: tuple[DesiredBlock, ...]) -> str:
    actions = [rule for block in blocks for rule in block.rules]
    lines = [
        "*filter",
        ":ufw-before-input - [0:0]",
        ":ufw-before-output - [0:0]",
        ":ufw-before-forward - [0:0]",
    ]
    lines.extend(" ".join(rule) for rule in actions)
    lines.append("COMMIT")
    return "\n".join(lines) + "\n"


def _validate_managed_actions(
    plan: ApplyPlan,
    *,
    runner: Runner,
) -> None:
    iptables_restore = _binary("iptables-restore")
    runner(
        [iptables_restore, "--test"],
        input_text=_validation_payload(plan.compiled.ipv4),
        check=True,
        timeout=20,
    )
    if plan.ipv6 is not None:
        ip6tables_restore = _binary("ip6tables-restore")
        runner(
            [ip6tables_restore, "--test"],
            input_text=_validation_payload(plan.compiled.ipv6),
            check=True,
            timeout=20,
        )


def _atomic_replace(path: Path, content: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise FirewallApplyError(f"Refusing non-regular UFW file: {path}")
    info = path.stat()
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, stat.S_IMODE(info.st_mode))
        try:
            os.fchown(fd, info.st_uid, info.st_gid)
        except PermissionError as exc:
            raise FirewallApplyError(f"Cannot preserve ownership of {path}") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        directory_fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if tmp.exists():
            tmp.unlink()


def _backup_file(path: Path, target: Path) -> bool:
    if not path.exists():
        return False
    if path.is_symlink() or not path.is_file():
        raise FirewallApplyError(f"Refusing backup of non-regular path: {path}")
    shutil.copy2(path, target)
    return True


def _create_backup(paths: ApplyPaths, *, was_active: bool) -> tuple[Path, dict[str, bool]]:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    backup = paths.backups / f"{stamp}-{uuid4().hex[:8]}"
    try:
        backup.mkdir(parents=True, mode=0o700, exist_ok=False)
        os.chmod(backup, 0o700)
        existed = {
            "before4": _backup_file(paths.before4, backup / "before.rules"),
            "before6": _backup_file(paths.before6, backup / "before6.rules"),
        }
        metadata = {
            "created_at": datetime.now().astimezone().isoformat(),
            "was_active": was_active,
            "files": existed,
        }
        (backup / "metadata.json").write_text(
            json.dumps(metadata, indent=2) + "\n",
            encoding="utf-8",
        )
        os.chmod(backup / "metadata.json", 0o600)
        return backup, existed
    except OSError as exc:
        raise FirewallApplyError("Cannot create firewall rollback backup.") from exc


def _rollback_script(
    paths: ApplyPaths,
    backup: Path,
    existed: dict[str, bool],
    touched: dict[str, bool],
    *,
    ufw: str,
    was_active: bool,
) -> str:
    commands = ["set -eu"]
    pairs = (
        ("before4", backup / "before.rules", paths.before4),
        ("before6", backup / "before6.rules", paths.before6),
    )
    for key, source, target in pairs:
        if not touched[key]:
            continue
        if existed[key]:
            commands.append(
                "cp -p -- " + shlex.quote(str(source)) + " " + shlex.quote(str(target))
            )
        else:
            commands.append("rm -f -- " + shlex.quote(str(target)))
    commands.append(
        shlex.quote(ufw) + (" reload" if was_active else " disable")
    )
    return "; ".join(commands)


def _arm_rollback(
    paths: ApplyPaths,
    backup: Path,
    existed: dict[str, bool],
    touched: dict[str, bool],
    *,
    ufw: str,
    was_active: bool,
    seconds: int,
    runner: Runner,
) -> str:
    if not 15 <= seconds <= 600:
        raise FirewallApplyError("Rollback timeout must be 15..600 seconds.")
    systemd_run = _binary("systemd-run")
    unit = "jb-sys-apps-ufw-rollback-" + uuid4().hex[:12]
    runner(
        [
            systemd_run,
            "--quiet",
            "--unit", unit,
            "--on-active", f"{seconds}s",
            "--timer-property=AccuracySec=1s",
            "/bin/bash", "-c",
            _rollback_script(
                paths, backup, existed, touched,
                ufw=ufw, was_active=was_active
            ),
        ],
        check=True,
        timeout=20,
    )
    return unit


def _cancel_rollback(unit: str, *, runner: Runner) -> None:
    systemctl = _binary("systemctl")
    runner(
        [systemctl, "stop", f"{unit}.timer"],
        check=False,
        timeout=15,
    )
    runner(
        [systemctl, "reset-failed", f"{unit}.service"],
        check=False,
        timeout=15,
    )


def _restore_backup(
    paths: ApplyPaths,
    backup: Path,
    existed: dict[str, bool],
    touched: dict[str, bool],
    *,
    ufw: str,
    was_active: bool,
    runner: Runner,
) -> None:
    pairs = (
        ("before4", backup / "before.rules", paths.before4),
        ("before6", backup / "before6.rules", paths.before6),
    )
    for key, source, target in pairs:
        if not touched[key]:
            continue
        try:
            if existed[key]:
                shutil.copy2(source, target)
            elif target.exists():
                target.unlink()
        except OSError as exc:
            raise FirewallApplyError(
                f"Rollback could not restore {target}."
            ) from exc
    runner(
        [ufw, "reload"] if was_active else [ufw, "disable"],
        check=False,
        timeout=30,
    )


def _assert_source_unchanged(path: Path, expected: str) -> None:
    current = _read_regular(path, required=True)
    if current != expected:
        raise FirewallApplyError(
            f"UFW file changed concurrently; refusing to overwrite: {path}"
        )


def _file_hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _config_hash(config: FirewallConfig) -> str:
    payload = json.dumps(
        asdict(normalize_config(config)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _save_state(
    paths: ApplyPaths,
    config: FirewallConfig,
    plan: ApplyPlan,
    *,
    backup: Path,
) -> None:
    target = paths.state
    target.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if target.exists() and target.is_symlink():
        raise FirewallApplyError("Firewall apply state must not be a symlink.")
    state = {
        "version": 1,
        "last_applied_at": datetime.now().astimezone().isoformat(),
        "config_hash": _config_hash(config),
        "ipv4_managed_hash": plan.ipv4.desired_hash,
        "ipv6_managed_hash": (
            plan.ipv6.desired_hash if plan.ipv6 is not None else ""
        ),
        "backup_dir": str(backup),
    }
    fd, tmp_name = tempfile.mkstemp(
        prefix=target.name + ".", suffix=".tmp", dir=target.parent
    )
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(state, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    finally:
        if tmp.exists():
            tmp.unlink()


def _candidate_still_live(paths: ApplyPaths, plan: ApplyPlan) -> bool:
    if _file_hash(paths.before4) != sha256(plan.ipv4.content.encode("utf-8")).hexdigest():
        return False
    if plan.ipv6 is not None:
        if not paths.before6.is_file():
            return False
        if _file_hash(paths.before6) != sha256(
            plan.ipv6.content.encode("utf-8")
        ).hexdigest():
            return False
    return inspect_ufw_service().status == "active"


def apply_local_config(
    config: FirewallConfig,
    *,
    acknowledge: Acknowledge,
    rollback_seconds: int = 90,
    paths: ApplyPaths = ApplyPaths(),
    runner: Runner = _run,
) -> ApplyResult:
    """Apply local config with pre-armed rollback and explicit live acknowledgement."""
    status = inspect_ufw_service()
    if not status.detected:
        raise FirewallApplyError("UFW is not installed.")
    if status.status not in {"active", "inactive"}:
        raise FirewallApplyError(f"UFW status is not safe to mutate: {status.status}")
    was_active = status.status == "active"

    before4 = _read_regular(paths.before4, required=True)
    before6 = _read_regular(paths.before6, required=False)
    assert before4 is not None
    try:
        plan = build_apply_plan(config, before4=before4, before6=before6)
    except FirewallPolicyError as exc:
        raise FirewallApplyError(str(exc)) from exc

    if was_active and not plan.changed:
        return ApplyResult("NO_CHANGE", False, False)

    _validate_managed_actions(plan, runner=runner)
    ufw = _binary("ufw")
    backup, existed = _create_backup(paths, was_active=was_active)
    _assert_source_unchanged(paths.before4, before4)
    if before6 is not None:
        _assert_source_unchanged(paths.before6, before6)

    touched = {
        "before4": plan.ipv4.changed,
        "before6": bool(plan.ipv6 is not None and plan.ipv6.changed),
    }
    unit = _arm_rollback(
        paths,
        backup,
        existed,
        touched,
        ufw=ufw,
        was_active=was_active,
        seconds=rollback_seconds,
        runner=runner,
    )

    mutation_started = False
    try:
        # Recheck after arming the timer: another administrator/process may
        # have touched UFW while the rollback unit was being created.
        _assert_source_unchanged(paths.before4, before4)
        if before6 is not None:
            _assert_source_unchanged(paths.before6, before6)

        if plan.ipv4.changed:
            mutation_started = True
            _atomic_replace(paths.before4, plan.ipv4.content)
        if plan.ipv6 is not None and plan.ipv6.changed:
            mutation_started = True
            _atomic_replace(paths.before6, plan.ipv6.content)

        runner(
            [ufw, "--dry-run", "reload"]
            if was_active
            else [ufw, "--dry-run", "enable"],
            check=True,
            timeout=30,
        )
        mutation_started = True
        runner(
            [ufw, "reload"] if was_active else [ufw, "--force", "enable"],
            check=True,
            timeout=30,
        )
        if inspect_ufw_service().status != "active":
            raise FirewallApplyError("UFW did not become/remain active after Apply.")

        accepted = bool(acknowledge(rollback_seconds))
        if not accepted:
            _cancel_rollback(unit, runner=runner)
            _restore_backup(
                paths,
                backup,
                existed,
                touched,
                ufw=ufw,
                was_active=was_active,
                runner=runner,
            )
            return ApplyResult("ROLLED_BACK", plan.changed, not was_active, str(backup))

        _cancel_rollback(unit, runner=runner)
        if not _candidate_still_live(paths, plan):
            _restore_backup(
                paths,
                backup,
                existed,
                touched,
                ufw=ufw,
                was_active=was_active,
                runner=runner,
            )
            raise FirewallApplyError(
                "Rollback fired or live UFW state changed before confirmation."
            )

        _save_state(paths, config, plan, backup=backup)
        return ApplyResult("APPLIED", plan.changed, not was_active, str(backup))
    except Exception:
        _cancel_rollback(unit, runner=runner)
        if mutation_started:
            try:
                _restore_backup(
                    paths,
                    backup,
                    existed,
                    touched,
                    ufw=ufw,
                    was_active=was_active,
                    runner=runner,
                )
            except Exception:
                pass
        raise


def disable_ufw(*, runner: Runner = _run) -> None:
    status = inspect_ufw_service()
    if not status.detected:
        raise FirewallApplyError("UFW is not installed.")
    if status.status == "inactive":
        return
    if status.status != "active":
        raise FirewallApplyError(f"UFW status is not safe to mutate: {status.status}")
    ufw = _binary("ufw")
    runner([ufw, "disable"], check=True, timeout=30)
    if inspect_ufw_service().status != "inactive":
        raise FirewallApplyError("UFW disable command did not result in inactive state.")
