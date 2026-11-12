from flask_openapi3 import Info, OpenAPI

from .identity import init_identity
from .people import init_people
from .platform.config import Config
from .platform.db import init_db
from .platform.errors import ValidationErrorResponse, register_error_handlers, validation_error_response
from .platform.health import api as health_api
from .platform.logging import configure_logging
from .platform.openapi_cli import export_openapi
from .platform.sessions import init_sessions


def create_app(config: type[Config] = Config) -> OpenAPI:
    app = OpenAPI(
        __name__,
        info=Info(title="Dental CRM API", version="0.1.0"),
        validation_error_status=422,
        validation_error_model=ValidationErrorResponse,
        validation_error_callback=validation_error_response,
    )
    app.config.from_object(config)
    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not set. Run python scripts/setup_local.py for local development.")
    if not app.config.get("TESTING") and not app.config.get("TOTP_ENCRYPTION_KEY"):
        raise RuntimeError(
            "TOTP_ENCRYPTION_KEY is not set. Generate a Fernet key with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )
    configure_logging(app)
    init_db(app)
    init_sessions(app)
    register_error_handlers(app)
    init_identity(app)
    init_people(app)
    app.register_api(health_api)
    app.cli.add_command(export_openapi)
    return app
