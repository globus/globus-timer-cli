import pathlib
from typing import Optional

import click
from fair_research_login import JSONTokenStorage
from fair_research_login.client import NativeClient


CLIENT_ID = "bc77d044-1f42-46cc-9702-87f756cd08a6"
CLIENT_NAME = "timer_cli"
SCOPES = [
    "https://auth.globus.org/scopes/524230d7-ea86-4a52-8312-86065a9e0417/transfer_action"
]
TOKEN_DIRECTORY = f"{pathlib.Path.home()}/.config/globus"
DEFAULT_TOKEN_FILE = str(
    pathlib.Path(TOKEN_DIRECTORY).joinpath(pathlib.Path("tokens.json"))
)


def create_token_directory():
    pathlib.Path(TOKEN_DIRECTORY).mkdir(parents=True, exist_ok=True)


def get_access_token(token_store: Optional[str] = None):
    # use this rather than the actual default argument so we can chain multiple default
    # arguments (from `get_headers`)
    token_store = token_store or DEFAULT_TOKEN_FILE
    try:
        create_token_directory()
        cli = NativeClient(
            client_id=CLIENT_ID,
            app_name=CLIENT_NAME,
            token_storage=JSONTokenStorage(token_store),
        )
    except FileNotFoundError:
        click.echo(
            (
                f"couldn't access or create file for token storage ({token_store});"
                "make sure the CLI would be allowed to create the directory if it"
                " doesn't exist, and/or open that file inside that directory"
            ),
            err=True
        )
    cli.login(requested_scopes=SCOPES, refresh_tokens=True)
    authorizer = next(iter(cli.get_authorizers().values()))
    return authorizer.access_token
