from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from typing import Iterator, Sequence
from urllib.parse import quote

import json5


CORE_TOKEN_ID = "sys_apps"
MANDATORY_SUBMODULES: dict[str, str] = {
    "libs/JBLibs": "JBLibs-python",
}
PLUGINS_CONFIG = "pluginy.jsonc"
TOKENS_DIR = Path("assets/tokens")


@dataclass
class UpdateReport:
    """Result of one complete application update attempt."""

    success: bool = False
    core_changed: bool = False
    mandatory_changed: bool = False
    optional_changed: bool = False
    steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def changed(self) -> bool:
        return self.core_changed or self.mandatory_changed or self.optional_changed

    def print_summary(self) -> None:
        print("\n" + "=" * 72)
        print("Update summary")
        print("=" * 72)
        for step in self.steps:
            print(f"  OK   {step}")
        for warning in self.warnings:
            print(f"  WARN {warning}")
        if self.error:
            print(f"  FAIL {self.error}")
        elif self.success:
            state = "changes installed" if self.changed else "already up to date"
            print(f"  DONE Update completed: {state}.")
            print("       Restart sys_apps to load the installed code.")
        print("=" * 72)


class ApplicationUpdater:
    """Update sys_apps without letting optional plugins break core."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.report = UpdateReport()
        self._base_env = os.environ.copy()
        self._base_env["GIT_TERMINAL_PROMPT"] = "0"

    def _capture(
        self,
        cmd: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> tuple[int, str]:
        try:
            proc = subprocess.run(
                list(cmd),
                cwd=str(cwd or self.root),
                env=env or self._base_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        except OSError as exc:
            return 127, str(exc)
        return proc.returncode, proc.stdout.strip()

    def _run_live(
        self,
        label: str,
        cmd: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> bool:
        print(f"\n--- {label} ---")
        print("$ " + shlex.join(list(cmd)))
        try:
            proc = subprocess.run(
                list(cmd),
                cwd=str(cwd or self.root),
                env=env or self._base_env,
                check=False,
            )
        except OSError as exc:
            print(f"Command failed to start: {exc}")
            return False
        if proc.returncode == 0:
            self.report.steps.append(label)
            return True
        return False

    def _fail(self, message: str) -> UpdateReport:
        self.report.error = message
        self.report.success = False
        return self.report

    def _head(self, path: Path | None = None) -> str | None:
        cwd = path or self.root
        code, output = self._capture(["git", "rev-parse", "HEAD"], cwd=cwd)
        return output if code == 0 and output else None

    def _configured_submodule_paths(self) -> set[str]:
        code, output = self._capture(
            [
                "git",
                "config",
                "--file",
                ".gitmodules",
                "--get-regexp",
                r"^submodule\..*\.path$",
            ]
        )
        if code != 0 or not output:
            return set()
        paths: set[str] = set()
        for line in output.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                paths.add(parts[1].strip())
        return paths

    def _is_initialized_submodule(self, path: str) -> bool:
        return (self.root / path / ".git").exists()

    def _verify_clean_worktrees(self) -> bool:
        code, output = self._capture(
            [
                "git",
                "status",
                "--porcelain",
                "--untracked-files=no",
                "--ignore-submodules=all",
            ]
        )
        if code != 0:
            self.report.error = "Cannot read the main repository working tree state."
            return False
        if output:
            self.report.error = (
                "The main repository contains tracked local changes. "
                "Commit or revert them before updating:\n" + output
            )
            return False

        for path in sorted(self._configured_submodule_paths()):
            if not self._is_initialized_submodule(path):
                continue
            code, sub_output = self._capture(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=self.root / path,
            )
            if code != 0:
                self.report.error = f"Cannot read working tree state for {path}."
                return False
            if sub_output:
                self.report.error = (
                    f"Submodule {path} contains tracked local changes. "
                    "Commit or revert them before updating:\n" + sub_output
                )
                return False

        self.report.steps.append("Main and initialized submodule worktrees are clean")
        return True

    def _token_path(self, token_id: str) -> Path:
        return self.root / TOKENS_DIR / f"{token_id}.cd"

    def _read_token(self, token_id: str) -> tuple[str, str] | None:
        token_path = self._token_path(token_id)
        if not token_path.is_file():
            return None
        try:
            raw = token_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"cannot read token file: {exc}") from exc

        lines = raw.splitlines()
        if len(lines) != 1 or ":" not in lines[0]:
            raise ValueError("token file must contain exactly one username:token line")
        username, token = lines[0].split(":", 1)
        if not username or not token or username.strip() != username or token.strip() != token:
            raise ValueError("token file must contain non-empty username:token without spaces")
        return username, token

    def _resolve_token(self, token_ids: Sequence[str]) -> tuple[str, str] | None:
        for token_id in token_ids:
            if self._token_path(token_id).is_file():
                return self._read_token(token_id)
        return None

    def _credential_file(self, username: str, token: str) -> str:
        fd, path = tempfile.mkstemp(prefix="sys_apps_git_credential_")
        try:
            os.fchmod(fd, 0o600)
            credential = (
                "https://"
                + quote(username, safe="")
                + ":"
                + quote(token, safe="")
                + "@github.com\n"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(credential)
        except Exception:
            try:
                os.close(fd)
            except OSError:
                pass
            try:
                os.unlink(path)
            except OSError:
                pass
            raise
        return path

    @contextmanager
    def _git_prefix(self, token_ids: Sequence[str] = ()) -> Iterator[list[str]]:
        credential_file: str | None = None
        try:
            token = self._resolve_token(token_ids)
            prefix = ["git"]
            if token is not None:
                credential_file = self._credential_file(*token)
                prefix.extend(
                    [
                        "-c",
                        "credential.helper=",
                        "-c",
                        f"credential.helper=store --file={credential_file}",
                    ]
                )
            yield prefix
        finally:
            if credential_file:
                try:
                    os.unlink(credential_file)
                except OSError:
                    pass

    def _verify_submodule(self, path: str) -> tuple[bool, str]:
        code_expected, expected = self._capture(
            ["git", "rev-parse", f"HEAD:{path}"]
        )
        code_actual, actual = self._capture(
            ["git", "-C", path, "rev-parse", "HEAD"]
        )
        if code_expected != 0 or not expected:
            return False, f"Cannot resolve expected gitlink for {path}."
        if code_actual != 0 or not actual:
            return False, f"Cannot resolve installed commit for {path}."
        if expected != actual:
            return False, (
                f"{path} commit mismatch: expected {expected[:12]}, "
                f"installed {actual[:12]}."
            )
        return True, expected

    def _update_main_repository(self) -> bool:
        before = self._head()
        try:
            with self._git_prefix((CORE_TOKEN_ID,)) as git_cmd:
                cmd = git_cmd + [
                    "-c",
                    "submodule.recurse=false",
                    "pull",
                    "--ff-only",
                ]
                if not self._run_live("Update main sys_apps repository", cmd):
                    self.report.error = "Main repository update failed."
                    return False
        except ValueError as exc:
            self.report.error = f"Core token {CORE_TOKEN_ID}.cd is invalid: {exc}"
            return False

        after = self._head()
        if before != after:
            self.report.core_changed = True
        return True

    def _update_mandatory_submodule(self, path: str, token_id: str) -> bool:
        if path not in self._configured_submodule_paths():
            self.report.error = f"Mandatory submodule {path} is missing from .gitmodules."
            return False

        before = self._head(self.root / path)
        if not self._run_live(
            f"Synchronize mandatory submodule {path}",
            ["git", "submodule", "sync", "--recursive", "--", path],
        ):
            self.report.error = f"Failed to synchronize mandatory submodule {path}."
            return False

        try:
            with self._git_prefix((token_id, CORE_TOKEN_ID)) as git_cmd:
                cmd = git_cmd + [
                    "submodule",
                    "update",
                    "--init",
                    "--checkout",
                    "--recursive",
                    "--",
                    path,
                ]
                if not self._run_live(f"Install mandatory submodule {path}", cmd):
                    self.report.error = f"Failed to install mandatory submodule {path}."
                    return False
        except ValueError as exc:
            self.report.error = f"Token for mandatory submodule {path} is invalid: {exc}"
            return False

        valid, detail = self._verify_submodule(path)
        if not valid:
            self.report.error = detail
            return False
        self.report.steps.append(f"Verified mandatory submodule {path} at {detail[:12]}")
        after = self._head(self.root / path)
        if before != after:
            self.report.mandatory_changed = True
        return True

    def _load_plugins(self) -> dict[str, dict]:
        config_path = self.root / PLUGINS_CONFIG
        if not config_path.is_file():
            return {}
        try:
            data = json5.loads(config_path.read_text(encoding="utf-8"))
        except Exception as exc:
            self.report.warnings.append(
                f"Plugin config {PLUGINS_CONFIG} cannot be read: {exc}"
            )
            return {}
        if not isinstance(data, dict):
            self.report.warnings.append(
                f"Plugin config {PLUGINS_CONFIG} is not an object."
            )
            return {}
        return {
            str(plugin_id): value
            for plugin_id, value in data.items()
            if isinstance(value, dict)
        }

    def _plugin_path(self, plugin: dict) -> str | None:
        adr_name = plugin.get("adr_name")
        if not isinstance(adr_name, str) or not adr_name.strip():
            return None
        return str(Path("libs/app/menus") / adr_name.strip())

    def _plugin_failure(self, plugin_id: str, optional: bool, message: str) -> bool:
        full_message = f"Plugin {plugin_id}: {message}"
        if optional:
            self.report.warnings.append(full_message + " Core update continues.")
            return True
        self.report.error = full_message
        return False

    def _update_plugin(self, plugin_id: str, plugin: dict) -> bool:
        auto_update = bool(plugin.get("auto_update", True))
        optional = bool(plugin.get("optional", True))
        private = bool(plugin.get("private", False))

        if not auto_update:
            self.report.warnings.append(
                f"Plugin {plugin_id} auto-update is disabled by {PLUGINS_CONFIG}; skipped."
            )
            return True

        path = self._plugin_path(plugin)
        if path is None:
            return self._plugin_failure(
                plugin_id,
                optional,
                "has no valid adr_name and was skipped.",
            )
        if path not in self._configured_submodule_paths():
            return self._plugin_failure(
                plugin_id,
                optional,
                f"path {path} is missing from .gitmodules.",
            )

        initialized = self._is_initialized_submodule(path)
        has_token = self._token_path(plugin_id).is_file()
        access = plugin.get("access")
        access_type = access.get("type") if isinstance(access, dict) else None
        requires_token = private and access_type == "token"

        if requires_token and not initialized and not has_token:
            return self._plugin_failure(
                plugin_id,
                optional,
                f"is private, not installed and has no {plugin_id}.cd token; skipped.",
            )

        before = self._head(self.root / path) if initialized else None
        if not self._run_live(
            f"Synchronize plugin {plugin_id}",
            ["git", "submodule", "sync", "--recursive", "--", path],
        ):
            return self._plugin_failure(plugin_id, optional, "synchronization failed.")

        token_ids = (plugin_id,) if has_token else ()
        try:
            with self._git_prefix(token_ids) as git_cmd:
                cmd = git_cmd + [
                    "submodule",
                    "update",
                    "--init",
                    "--checkout",
                    "--recursive",
                    "--",
                    path,
                ]
                if not self._run_live(f"Install/update plugin {plugin_id}", cmd):
                    return self._plugin_failure(plugin_id, optional, "update failed.")
        except ValueError as exc:
            return self._plugin_failure(plugin_id, optional, f"token file is invalid: {exc}")

        valid, detail = self._verify_submodule(path)
        if not valid:
            return self._plugin_failure(plugin_id, optional, detail)
        self.report.steps.append(f"Verified plugin {plugin_id} at {detail[:12]}")
        after = self._head(self.root / path)
        if before != after:
            self.report.optional_changed = True
        return True

    def _run_setup(self) -> bool:
        setup_path = self.root / "setup.sh"
        if not setup_path.is_file():
            self.report.error = "setup.sh is missing after the repository update."
            return False
        env = self._base_env.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        if not self._run_live(
            "Install/update runtime dependencies",
            ["bash", "setup.sh", "--no-run"],
            env=env,
        ):
            self.report.error = "setup.sh --no-run failed."
            return False
        return True

    def run(self) -> UpdateReport:
        if not (self.root / ".git").exists():
            return self._fail(f"{self.root} is not a Git working tree.")
        if not self._verify_clean_worktrees():
            return self.report
        if not self._update_main_repository():
            return self.report

        for path, token_id in MANDATORY_SUBMODULES.items():
            if not self._update_mandatory_submodule(path, token_id):
                return self.report

        for plugin_id, plugin in self._load_plugins().items():
            if not self._update_plugin(plugin_id, plugin):
                return self.report

        if not self._run_setup():
            return self.report

        self.report.success = True
        return self.report


def update_application(root: str | Path) -> UpdateReport:
    """Run the complete sys_apps update and return its structured result."""

    return ApplicationUpdater(root).run()
