import logging

from flask import Flask, g, jsonify
from pydantic import BaseModel, ValidationError
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)


class ErrorResponse(BaseModel):
    """OpenAPI schema of every JSON error body."""

    error: str


class ValidationErrorResponse(BaseModel):
    error: str
    fields: list[str]


VALIDATION_ERROR_RESPONSES = {422: ValidationErrorResponse}


class ApiError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


def error_response(status: int, code: str, headers=None, **extra):
    response = jsonify({"error": code, **extra})
    response.status_code = status
    for name, value in headers or ():
        if name.lower() != "content-type":
            response.headers.add(name, value)
    return response


def _render(status: int, code: str, headers=None, **extra):
    g.request_failed = True
    return error_response(status, code, headers, **extra)


def validation_error_response(e: ValidationError):
    fields = []
    for err in e.errors(include_input=False, include_url=False):
        path = ".".join(str(part) for part in err["loc"]) or "body"
        if path not in fields:
            fields.append(path)
    return _render(422, "validation_error", fields=fields)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return _render(e.status, e.code)

    @app.errorhandler(404)
    def _not_found(e):
        return _render(404, "not_found", e.get_headers())

    @app.errorhandler(405)
    def _method_not_allowed(e):
        return _render(405, "method_not_allowed", e.get_headers())

    @app.errorhandler(413)
    def _too_large(e):
        return error_response(413, "file_too_large")


    @app.errorhandler(Exception)
    def _internal(e):
        if isinstance(e, HTTPException):
            code = (e.name or "error").lower().replace(" ", "_")
            return _render(e.code or 500, code, e.get_headers())
        log.exception("unhandled error")
        return _render(500, "internal_error")
