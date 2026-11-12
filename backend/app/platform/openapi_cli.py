from pathlib import Path

import click
from flask import Flask, current_app
from flask.cli import with_appcontext


def render_openapi(app: Flask) -> str:
    return app.json.dumps(app.api_doc)


@click.command("export-openapi")
@click.argument("path", type=click.Path(dir_okay=False, path_type=Path))
@with_appcontext
def export_openapi(path: Path) -> None:
    """Write the OpenAPI document to PATH (committed as openapi.json at the repo root)."""
    path.write_text(render_openapi(current_app), encoding="utf-8", newline="\n")
    click.echo(f"wrote {path}")
