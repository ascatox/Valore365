"""SQL query loader — reads .sql files from this package directory."""

from pathlib import Path

_SQL_DIR = Path(__file__).parent


def load_sql(name: str) -> str:
    """Load a SQL file by name (without .sql extension).

    Supports nested paths like ``migrations/create_asset_metadata``.
    """
    path = _SQL_DIR / f"{name}.sql"
    return path.read_text(encoding="utf-8").strip()
