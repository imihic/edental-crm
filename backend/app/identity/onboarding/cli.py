import click
from flask.cli import with_appcontext

from app.identity.lookup import find_account_for_login
from app.identity.onboarding.handler import create_organization
from app.platform.db import get_session


@click.command("create-organization")
@click.option("--name", required=True, help="Organization name.")
@click.option("--clinic", "clinic_name", required=True, help="Name of its first Clinic.")
@click.option("--manager-email", required=True)
@click.option("--manager-name", required=True)
@with_appcontext
def create_organization_command(name: str, clinic_name: str, manager_email: str, manager_name: str) -> None:
    """Create an Organization, its first Clinic and a Clinic Manager Account."""
    session = get_session()
    password = None
    if find_account_for_login(session, manager_email) is None:
        password = click.prompt("Manager password", hide_input=True, confirmation_prompt=True)
    else:
        click.echo("Reused existing account")
    try:
        org = create_organization(
            session,
            name=name,
            clinic_name=clinic_name,
            manager_email=manager_email,
            manager_name=manager_name,
            manager_password=password,
        )
    except ValueError as e:
        click.echo(f"error: {e}", err=True)
        raise SystemExit(1) from None
    click.echo(str(org.id))
