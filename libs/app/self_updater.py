from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
from typing import Sequence
from urllib.parse import quote

import json5


MANDATORY_SUBMODULES: tuple[str, ...] = ("libs/JBLibs",)
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
    """Update sys_apps without letting optional private plugins break core."""

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
        proc = subprocess.run(
            list(cmd),
            cwd=str(cwd or self.root),
            env=env or self._base_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
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
        proc = subprocess.run(
            list(cmd),
            cwd=str(cwd or self.root),
            env=env or self._base_env,
            check=False,
        )
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

    def _verify_clean_worktree(self) -> bool:
        code, output = self._capture(
            ["git", "status", "--porcelain", "--untracked-files=no"]
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
        self.report.steps.append("Main repository working tree is clean")
        return True

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

    def _update_mandatory_submodule(self, path: str) -> bool:
        before = self._head(self.root / path)
        if not self._run_live(
            f"Synchronize mandatory submodule {path}",
            ["git", "submodule", "sync", "--recursive", "--", path],
        ):
            self.report.error = f"Failed to synchronize mandatory submodule {path}."
            return False
        if not self._run_live(
            f"Install mandatory submodule {path}",
            [
                "git",
                "submodule",
                "update",
                "--init",
                "--checkout",
                "--recursive",
                "--",
                path,
            ],
        ):
            self.report.error = f"Failed to install mandatory submodule {path}."
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
                f"Optional plugin config {PLUGINS_CONFIG} cannot be read: {exc}"
            )
            return {}
        if not isinstance(data, dict):
            self.report.warnings.append(
                f"Optional plugin config {PLUGINS_CONFIG} is not an object."
            )
            return {}
        return {
            str(plugin_id): value
            for plugin_id, value in data.items()
            if isinstance(value, dict)
        }

    def _read_token(self, plugin_id: str) -> tuple[str, str] | None:
        token_path = self.root / TOKENS_DIR / f"{plugin_id}.cd"
        if not token_path.is_file():
            return None
        try:
            raw = token_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"cannot read token file: {exc}") from exc
        if "\n" in raw or "\r" in raw or raw.count(":") < 1:
            raise ValueError("token file must contain exactly one username:token line")
        username, token = raw.split(":", 1)
        if not username or not token or username.strip() != username or token.strip() != token:
            raise ValueError("token file must contain non-empty username:token without spaces")
        return username, token

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

    def _plugin_path(self, plugin: dict) -> str | None:
        adr_name = plugin.get("adr_name")
        if not isinstance(adr_name, str) or not adr_name.strip():
            return None
        return str(Path("libs/app/menus") / adr_name.strip())

    def _is_initialized_submodule(self, path: str) -> bool:
        return (self.root / path / ".git").exists()

    def _update_optional_plugin(self, plugin_id: str, plugin: dict) -> None:
        path = self._plugin_path(plugin)
        if path is None:
            self.report.warnings.append(
                f"Optional plugin {plugin_id} has no valid adr_name; skipped."
            )
            return

        initialized = self._is_initialized_submodule(path)
        token_path = self.root / TOKENS_DIR / f"{plugin_id}.cd"
        has_token = token_path.is_file()
        if not initialized and not has_token:
            self.report.warnings.append(
                f"Optional private plugin {plugin_id} is not installed and has no token; skipped."
            )
            return

        token: tuple[str, str] | None = None
        if has_token:
            try:
                token = self._read_token(plugin_id)
            except ValueError as exc:
                self.report.warnings.append(
                    f"Optional plugin {plugin_id} has an invalid token file: {exc}; skipped."
                )
                return

        before = self._head(self.root / path) if initialized else None
        credential_file: str | None = None
        try:
            git_cmd = ["git"]
            if token is not None:
                credential_file = self._credential_file(*token)
                git_cmd.extend(
                    ["-c", f"credential.helper=store --file={credential_file}"]
                )

            if not self._run_live(
                f"Synchronize optional plugin {plugin_id}",
                ["git", "submodule", "sync", "--recursive", "--", path],
            ):
                self.report.warnings.append(
                    f"Optional plugin {plugin_id} could not be synchronized; core update continues."
                )
                return

            update_cmd = git_cmd + [
                "submodule",
                "update",
                "--init",
                "--checkout",
                "--recursive",
                "--",
                path,
            ]
            if not self._run_live(
                f"Install optional plugin {plugin_id}",
                update_cmd,
            ):
                self.report.warnings.append(
                    f"Optional plugin {plugin_id} could not be updated; core update continues."
                )
                return

            valid, detail = self._verify_submodule(path)
            if not valid:
                self.report.warnings.append(
                    f"Optional plugin {plugin_id} verification failed: {detail}"
                )
                return
            self.report.steps.append(
                f"Verified optional plugin {plugin_id} at {detail[:12]}"
            )
            after = self._head(self.root / path)
            if before != after:
                self.report.optional_changed = True
        finally:
            if credential_file:
                try:
                    os.unlink(credential_file)
                except OSError:
                    pass

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
        if not self._verify_clean_worktree():
            return self.report

        core_before = self._head()
        if not self._run_live(
            "Update main sys_apps repository",
            ["git", "pull", "--ff-only"],
        ):
            return self._fail("Main repository update failed.")
        core_after = self._head()
        if core_before != core_after:
            self.report.core_changed = True

        for path in MANDATORY_SUBMODULES:
            if not self._update_mandatory_submodule(path):
                return self.report

        for plugin_id, plugin in self._load_plugins().items():
            self._update_optional_plugin(plugin_id, plugin)

        if not self._run_setup():
            return self.report

        self.report.success = True
        return self.report


def update_application(root: str | Path) -> UpdateReport:
    """Run the complete sys_apps update and return its structured result."""

    return ApplicationUpdater(root).run()
