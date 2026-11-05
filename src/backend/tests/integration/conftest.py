"""Throwaway PostgreSQL cluster for integration tests that need a real database.

``pg_engine`` (session scope) starts a private cluster with the Postgres 16
binaries (``/usr/lib/postgresql/16/bin`` or ``$PG_BIN``), loads
``database/schema.sql`` and then every file of ``database/migrations`` in
order, and yields a SQLAlchemy engine on it. Tests that use it are skipped
when the binaries are not installed.

The cluster listens only on a Unix socket in a temp dir (no TCP port). When
the tests run as root (containers), ``initdb``/``pg_ctl`` run as the
``postgres`` system user through ``runuser`` because Postgres refuses to run
as root.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
DATABASE_DIR = REPO_ROOT / "database"
PG_BIN = Path(os.environ.get("PG_BIN", "/usr/lib/postgresql/16/bin"))
PG_PORT = int(os.environ.get("PG_TEST_PORT", "55439"))


def _pg_available() -> bool:
    return (PG_BIN / "initdb").exists() and (PG_BIN / "pg_ctl").exists() and shutil.which("psql") is not None


def _as_pg_user(cmd: list[str]) -> list[str]:
    if os.geteuid() != 0:
        return cmd
    if shutil.which("runuser") is None:
        pytest.skip("running as root without runuser: cannot start Postgres")
    return ["runuser", "-u", "postgres", "--", *cmd]


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, capture_output=True, text=True, cwd="/", **kw)


@pytest.fixture(scope="session")
def pg_engine():
    if not _pg_available():
        pytest.skip(f"Postgres binaries not found in {PG_BIN}")
    from sqlalchemy import create_engine

    workdir = Path(tempfile.mkdtemp(prefix="valore365-pg-"))
    data_dir = workdir / "data"
    if os.geteuid() == 0:
        shutil.chown(workdir, user="postgres")
    os.chmod(workdir, 0o755)
    started = False
    try:
        _run(_as_pg_user([str(PG_BIN / "initdb"), "-D", str(data_dir), "-U", "postgres", "-A", "trust", "-E", "UTF8"]))
        _run(_as_pg_user([
            str(PG_BIN / "pg_ctl"), "-D", str(data_dir), "-l", str(workdir / "server.log"), "-w",
            "-o", f"-p {PG_PORT} -k {workdir} -c listen_addresses='' -c fsync=off",
            "start",
        ]))
        started = True
        psql = ["psql", "-q", "-h", str(workdir), "-p", str(PG_PORT), "-U", "postgres", "-v", "ON_ERROR_STOP=1"]
        _run([*psql, "-f", str(DATABASE_DIR / "schema.sql")])
        for migration in sorted((DATABASE_DIR / "migrations").glob("*.sql")):
            _run([*psql, "-f", str(migration)])

        engine = create_engine(
            f"postgresql+psycopg://postgres@/postgres?host={workdir}&port={PG_PORT}",
            pool_size=5,
            max_overflow=5,
        )
        yield engine
        engine.dispose()
    except subprocess.CalledProcessError as exc:  # pragma: no cover - environment specific
        pytest.skip(f"cannot start throwaway Postgres: {exc.stderr or exc.stdout}")
    finally:
        if started:
            subprocess.run(
                _as_pg_user([str(PG_BIN / "pg_ctl"), "-D", str(data_dir), "-m", "immediate", "stop"]),
                capture_output=True, cwd="/",
            )
        shutil.rmtree(workdir, ignore_errors=True)
