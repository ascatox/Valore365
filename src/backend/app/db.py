from sqlalchemy import create_engine

from .config import get_settings


settings = get_settings()

engine = create_engine(
    settings.database_url_resolved,
    pool_pre_ping=True,
)
