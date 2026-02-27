from sqlalchemy import create_engine, event

from .config import get_settings


settings = get_settings()

engine = create_engine(
    settings.database_url_resolved,
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _set_connection_options(dbapi_connection, connection_record):
    """Disable prepared statements for PgBouncer/Supabase compatibility."""
    dbapi_connection.prepare_threshold = 0
