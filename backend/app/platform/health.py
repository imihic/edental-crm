from flask import jsonify
from flask_openapi3 import APIBlueprint

from app.platform.errors import VALIDATION_ERROR_RESPONSES

api = APIBlueprint("health", __name__, abp_responses=VALIDATION_ERROR_RESPONSES)


@api.get("/api/health")
def health():
    return jsonify({"status": "ok"})
