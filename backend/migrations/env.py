import os

from alembic import context

from app.platform.config import Config
from app.platform.db import make_engine


def _url() -> str:
    return (
        context.config.get_main_option("sqlalchemy.url")
        or os.environ.get("DATABASE_OWNER_URL")
        or Config.DATABASE_OWNER_URL
    )


def run_migrations_online() -> None:
    engine = make_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("offline migrations are not supported")
run_migrations_online()
