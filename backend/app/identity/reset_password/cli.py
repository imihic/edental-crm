import click
from flask.cli import with_appcontext

from app.identity.reset_password.handler import reset_password
from app.platform.db import get_session


@click.command("reset-password")
@click.option("--email", required=True)
@click.option("--reset-totp", is_flag=True, help="Also clear the Account's second factor.")
@with_appcontext
def reset_password_command(email: str, reset_totp: bool) -> None:
    """Set a new password for an Account."""
    password = click.prompt("New password", hide_input=True, confirmation_prompt=True)
    try:
        reset_password(get_session(), email=email, new_password=password, reset_totp=reset_totp)
    except ValueError as e:
        click.echo(f"error: {e}", err=True)
        raise SystemExit(1) from None
    click.echo("Password reset")
