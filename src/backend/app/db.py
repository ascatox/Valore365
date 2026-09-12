from sqlalchemy import create_engine, event

from .config import get_settings


settings = get_settings()

engine = create_engine(
    settings.database_url_resolved,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    pool_recycle=settings.db_pool_recycle,
)


@event.listens_for(engine, "connect")
def _set_connection_options(dbapi_connection, connection_record):
    """Disable prepared statements for PgBouncer/Supabase compatibility."""
    dbapi_connection.prepare_threshold = None
