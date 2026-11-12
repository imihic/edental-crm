from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel

from app.identity.session import csrf_token
from app.platform.errors import VALIDATION_ERROR_RESPONSES

api = APIBlueprint(
    "auth_csrf", __name__, abp_tags=[Tag(name="auth")], abp_responses=VALIDATION_ERROR_RESPONSES
)


class CsrfResponse(BaseModel):
    csrf_token: str


@api.get("/api/auth/csrf", responses={200: CsrfResponse})
def get_csrf():
    return {"csrf_token": csrf_token()}
