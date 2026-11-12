from flask_openapi3 import APIBlueprint
from flask_openapi3.utils import parse_rule

_METHODS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")


def register_slices(parent: APIBlueprint, slices) -> None:
    merged: dict[str, dict] = {}
    for slice_api in slices:
        for path_url, item in slice_api.paths.items():
            uri = parse_rule(path_url, url_prefix=parent.url_prefix)
            target = merged.setdefault(uri, {})
            for method in _METHODS:
                operation = getattr(item, method, None)
                if operation is None:
                    continue
                if method in target:
                    raise ValueError(f"duplicate OpenAPI operation {method.upper()} {uri} from two slices")
                target[method] = operation
        parent.register_api(slice_api)
    for uri, operations in merged.items():
        item = parent.paths[uri].model_copy()
        for method, operation in operations.items():
            setattr(item, method, operation)
        parent.paths[uri] = item
