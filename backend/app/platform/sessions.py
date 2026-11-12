from datetime import timedelta

import redis
from flask import Flask
from flask_session import Session


def init_sessions(app: Flask) -> None:
    app.config.update(
        SESSION_TYPE="redis",
        SESSION_REDIS=redis.Redis.from_url(app.config["REDIS_URL"]),
        SESSION_PERMANENT=True,
        SESSION_COOKIE_NAME="crm_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
    )
    Session(app)
