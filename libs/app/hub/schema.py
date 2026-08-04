from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any

from .settings import HubSettings


_MIGRATION_FILE_RE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
_ALLOWED_TABLES = frozenset({
    "schema_migrations",
    "hosts",
    "host_addresses",
    "host_services",
    "sync_sources",
    "node_red_instances",
    "node_red_editor_users",
    "disks",
    "host_disks",
})


@dataclass(frozen=True)
class Migration:
    version: int
    filename: str
    template: str
    checksum: str

    def render(self, prefix: str) -> tuple[str, ...]:
        placeholders = set(_PLACEHOLDER_RE.findall(self.template))
        if placeholders - {"{{PREFIX}}"}:
            raise ValueError(
                f"Migration {self.filename} contains unsupported placeholders."
            )
        rendered = self.template.replace("{{PREFIX}}", prefix)
        return split_migration_statements(rendered)


@dataclass(frozen=True)
class SchemaCheck:
    exists: bool
    current: bool
    current_version: int
    latest_version: int
    error: str = ""


def table_identifier(settings: HubSettings, suffix: str) -> str:
    if suffix not in _ALLOWED_TABLES:
        raise ValueError(f"Unsupported Hub table suffix: {suffix}")
    ok, error = settings.validate()
    if not ok:
        raise ValueError(error)
    return f"`{settings.prefix}{suffix}`"


def split_migration_statements(sql_text: str) -> tuple[str, ...]:
    statements: list[str] = []
    current: list[str] = []
    for line in sql_text.splitlines():
        if line.strip() == "-- statement":
            statement = "\n".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            continue
        if line.lstrip().startswith("--") and not current:
            continue
        current.append(line)
    statement = "\n".join(current).strip()
    if statement:
        statements.append(statement)
    if not statements:
        raise ValueError("Migration does not contain any statements.")
    return tuple(statements)


def load_migrations() -> tuple[Migration, ...]:
    root = Path(__file__).with_name("migrations")
    migrations: list[Migration] = []
    versions: set[int] = set()
    for path in sorted(root.glob("*.sql")):
        match = _MIGRATION_FILE_RE.fullmatch(path.name)
        if not match:
            raise ValueError(f"Invalid migration filename: {path.name}")
        version = int(match.group(1))
        if version in versions:
            raise ValueError(f"Duplicate migration version: {version}")
        versions.add(version)
        template = path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(template.encode("utf-8")).hexdigest()
        migration = Migration(version, path.name, template, checksum)
        migration.render("sysapps_")
        migrations.append(migration)
    if not migrations:
        raise ValueError("No SysApps Hub migrations were found.")
    return tuple(migrations)


class HubSchemaManager:
    def __init__(self, settings: HubSettings):
        self.settings = settings
        self.migrations = load_migrations()

    @property
    def latest_version(self) -> int:
        return self.migrations[-1].version

    def _migration_table_exists(self, cursor: Any) -> bool:
        cursor.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema=%s AND table_name=%s LIMIT 1",
            (self.settings.database, f"{self.settings.prefix}schema_migrations"),
        )
        return cursor.fetchone() is not None

    def check(self, connection: Any) -> SchemaCheck:
        with connection.cursor() as cursor:
            if not self._migration_table_exists(cursor):
                return SchemaCheck(False, False, 0, self.latest_version)
            table = table_identifier(self.settings, "schema_migrations")
            cursor.execute(
                f"SELECT version, checksum_sha256 FROM {table} ORDER BY version"
            )
            applied = {int(row[0]): str(row[1]) for row in cursor.fetchall()}

        current_version = max(applied, default=0)
        for migration in self.migrations:
            applied_checksum = applied.get(migration.version)
            if applied_checksum is None:
                return SchemaCheck(
                    True, False, current_version, self.latest_version
                )
            if applied_checksum != migration.checksum:
                return SchemaCheck(
                    True,
                    False,
                    current_version,
                    self.latest_version,
                    f"Checksum mismatch for migration {migration.filename}.",
                )
        return SchemaCheck(
            True,
            current_version == self.latest_version,
            current_version,
            self.latest_version,
        )

    def apply(self, connection: Any) -> int:
        lock_name = (
            f"sysapps-hub:{self.settings.database}:{self.settings.prefix}:migrate"
        )[:64]
        migration_table = table_identifier(self.settings, "schema_migrations")
        with connection.cursor() as cursor:
            cursor.execute("SELECT GET_LOCK(%s, %s)", (lock_name, 10))
            row = cursor.fetchone()
            if not row or int(row[0]) != 1:
                raise RuntimeError("Cannot acquire SysApps Hub migration lock.")

        try:
            check = self.check(connection)
            if check.error:
                raise RuntimeError(check.error)

            applied_versions: set[int] = set()
            if check.exists:
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT version FROM {migration_table}")
                    applied_versions = {int(row[0]) for row in cursor.fetchall()}

            for migration in self.migrations:
                if migration.version in applied_versions:
                    continue
                with connection.cursor() as cursor:
                    for statement in migration.render(self.settings.prefix):
                        cursor.execute(statement)
                    cursor.execute(
                        f"INSERT INTO {migration_table} "
                        "(version, filename, checksum_sha256, applied_at) "
                        "VALUES (%s, %s, %s, UTC_TIMESTAMP(6))",
                        (
                            migration.version,
                            migration.filename,
                            migration.checksum,
                        ),
                    )
                connection.commit()
            return self.latest_version
        finally:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
            finally:
                connection.commit()
