"""Credential management for Wrike API.

Supports cascading credential lookup:
1. Explicit value (passed at runtime)
2. Environment variable (WRIKE_ACCESS_TOKEN)
3. OS keychain (via keyring library)

Wrike uses OAuth 2.0 - you'll need a permanent access token from:
https://www.wrike.com/frontend/apps/index.html#/api
"""

import os
import sys

import click
import keyring

SERVICE_NAME = "mcp-wrike"
ACCOUNT_NAME = "access_token"
ENV_VAR = "WRIKE_ACCESS_TOKEN"


def get_access_token(explicit_token: str | None = None) -> str | None:
    """Get access token from cascading sources.

    Args:
        explicit_token: Explicitly provided token (highest priority)

    Returns:
        Access token if found, None otherwise
    """
    # 1. Explicit value
    if explicit_token:
        return explicit_token

    # 2. Environment variable
    env_token = os.environ.get(ENV_VAR)
    if env_token:
        return env_token

    # 3. OS keychain
    try:
        keychain_token = keyring.get_password(SERVICE_NAME, ACCOUNT_NAME)
        if keychain_token:
            return keychain_token
    except keyring.errors.KeyringError:
        pass  # Keyring not available

    return None


def store_access_token(token: str) -> bool:
    """Store access token in OS keychain.

    Args:
        token: The access token to store

    Returns:
        True if successful, False otherwise
    """
    try:
        keyring.set_password(SERVICE_NAME, ACCOUNT_NAME, token)
        return True
    except keyring.errors.KeyringError as e:
        click.echo(f"Failed to store in keychain: {e}", err=True)
        return False


def delete_access_token() -> bool:
    """Delete access token from OS keychain.

    Returns:
        True if successful, False otherwise
    """
    try:
        keyring.delete_password(SERVICE_NAME, ACCOUNT_NAME)
        return True
    except keyring.errors.PasswordDeleteError:
        return False  # Token didn't exist
    except keyring.errors.KeyringError as e:
        click.echo(f"Failed to delete from keychain: {e}", err=True)
        return False


@click.group()
def cli():
    """Manage Wrike API credentials."""
    pass


@cli.command()
@click.option("--token", prompt="Wrike Access Token", hide_input=True,
              help="Your Wrike permanent access token (from wrike.com/frontend/apps/index.html#/api)")
def store(token: str):
    """Store access token in system keychain."""
    if store_access_token(token):
        click.echo("Access token stored in system keychain.")
    else:
        click.echo("Failed to store token. Set WRIKE_ACCESS_TOKEN env var instead.", err=True)
        sys.exit(1)


@cli.command()
def show():
    """Show where access token is configured (not the token itself)."""
    if os.environ.get(ENV_VAR):
        click.echo(f"Access token found in environment variable: {ENV_VAR}")
    elif keyring.get_password(SERVICE_NAME, ACCOUNT_NAME):
        click.echo("Access token found in system keychain.")
    else:
        click.echo("No access token configured.")
        click.echo(f"\nTo configure, either:")
        click.echo(f"  1. Run: wrike-auth store")
        click.echo(f"  2. Set environment variable: export {ENV_VAR}=your_token")
        click.echo(f"\nGet your token from: https://www.wrike.com/frontend/apps/index.html#/api")
        sys.exit(1)


@cli.command()
def delete():
    """Delete access token from system keychain."""
    if delete_access_token():
        click.echo("Access token deleted from system keychain.")
    else:
        click.echo("No access token found in keychain.")


if __name__ == "__main__":
    cli()
