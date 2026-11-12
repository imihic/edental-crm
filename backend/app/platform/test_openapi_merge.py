import pytest
from flask_openapi3 import APIBlueprint

from app.platform.openapi_merge import register_slices


def _slice(name: str, method: str) -> APIBlueprint:
    api = APIBlueprint(name, __name__)
    getattr(api, method)("/api/things")(lambda: "ok")
    return api


def test_same_path_different_methods_are_merged():
    parent = APIBlueprint("parent", __name__)
    register_slices(parent, [_slice("a", "get"), _slice("b", "post")])
    item = parent.paths["/api/things"]
    assert item.get is not None and item.post is not None


def test_duplicate_operation_raises():
    parent = APIBlueprint("parent", __name__)
    with pytest.raises(ValueError, match="duplicate OpenAPI operation GET /api/things"):
        register_slices(parent, [_slice("a", "get"), _slice("b", "get")])
