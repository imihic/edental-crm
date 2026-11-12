from uuid import UUID

from flask import Flask, current_app, g
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def sqlalchemy_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def make_engine(url: str) -> Engine:
    return create_engine(sqlalchemy_url(url), pool_pre_ping=True)


def init_db(app: Flask) -> None:
    engine = make_engine(app.config["DATABASE_URL"])
    app.extensions["db_engine"] = engine
    app.extensions["db_sessionmaker"] = sessionmaker(engine, expire_on_commit=False)
    app.teardown_appcontext(_close_session)


def get_session() -> Session:
    if "db_session" not in g:
        g.db_session = current_app.extensions["db_sessionmaker"]()
    return g.db_session


def _close_session(exc: BaseException | None) -> None:
    session: Session | None = g.pop("db_session", None)
    failed = exc is not None or g.pop("request_failed", False)
    if session is None:
        return
    try:
        if failed:
            session.rollback()
        else:
            session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def set_tenant_context(
    session: Session, *, organization_id: UUID | None, account_id: UUID | None
) -> None:
    session.execute(
        text(
            "SELECT set_config('app.current_org', :org, true), "
            "set_config('app.current_account', :acc, true)"
        ),
        {
            "org": str(organization_id) if organization_id else "",
            "acc": str(account_id) if account_id else "",
        },
    )
