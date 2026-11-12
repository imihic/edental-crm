import json
import logging
import re
import sys
import traceback
from datetime import UTC, datetime
from uuid import uuid4

from flask import Flask, g, has_request_context, request

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_HANDLER_MARK = "_crm_json_handler"


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        in_request = has_request_context()
        org = getattr(g, "organization_id", None) if in_request else None
        staff = getattr(g, "staff_member_id", None) if in_request else None
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(g, "request_id", None) if in_request else None,
            "organization_id": str(org) if org is not None else None,
            "staff_member_id": str(staff) if staff is not None else None,
        }
        if record.exc_info:
            exc_type, _, tb = record.exc_info
            payload["exception"] = exc_type.__name__ if exc_type else None
            payload["traceback"] = [
                f"{f.filename}:{f.lineno} in {f.name}" for f in traceback.extract_tb(tb)
            ]
        return json.dumps(payload)


class _StdoutHandler(logging.StreamHandler):

    def __init__(self) -> None:
        super().__init__(sys.stdout)

    @property
    def stream(self):
        return sys.stdout

    @stream.setter
    def stream(self, value) -> None:
        pass


def configure_logging(app: Flask) -> None:
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, _HANDLER_MARK, False)]:
        root.removeHandler(h)
    handler = _StdoutHandler()
    setattr(handler, _HANDLER_MARK, True)
    handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    @app.before_request
    def _assign_request_id() -> None:
        incoming = request.headers.get("X-Request-ID", "")
        g.request_id = incoming if _REQUEST_ID_RE.fullmatch(incoming) else uuid4().hex

    @app.after_request
    def _echo_request_id(response):
        rid = getattr(g, "request_id", None)
        if rid:
            response.headers["X-Request-ID"] = rid
        return response
