import pathlib
from typing import Optional

from fair_research_login import JSONTokenStorage
from fair_research_login.client import NativeClient


CLIENT_ID = "bc77d044-1f42-46cc-9702-87f756cd08a6"
CLIENT_NAME = "timer_cli"
SCOPES = [
    "https://auth.globus.org/scopes/524230d7-ea86-4a52-8312-86065a9e0417/transfer_action"
]


def get_access_token(token_store: Optional[str] = None):
    # use this rather than the actual default argument so we can chain multiple default
    # arguments (from `get_headers`)
    token_store = token_store or f"{pathlib.Path.home()}/.config/globus/tokens.json"
    cli = NativeClient(
        client_id=CLIENT_ID,
        app_name=CLIENT_NAME,
        token_storage=JSONTokenStorage(token_store),
    )
    cli.login(requested_scopes=SCOPES, refresh_tokens=True)
    authorizer = next(iter(cli.get_authorizers().values()))
    return authorizer.access_token
