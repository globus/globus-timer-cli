import os
import pathlib
from typing import Any, Dict, List, Optional

import click
from fair_research_login import JSONTokenStorage
from fair_research_login.client import NativeClient
from fair_research_login.exc import LocalServerError
from globus_sdk import AuthClient, RefreshTokenAuthorizer
from globus_sdk.exc import AuthAPIError

CLIENT_ID = "bc77d044-1f42-46cc-9702-87f756cd08a6"
CLIENT_NAME = "Globus Timer Service Command Line"
TIMER_SERVICE_SCOPE = "https://auth.globus.org/scopes/524230d7-ea86-4a52-8312-86065a9e0417/transfer_action"
AUTH_SCOPES = [
    "openid",
    "email",
    "profile",
]
ALL_SCOPES = AUTH_SCOPES + [TIMER_SERVICE_SCOPE]
TOKEN_DIRECTORY = f"{pathlib.Path.home()}/.config/globus"
DEFAULT_TOKEN_FILE = str(
    pathlib.Path(TOKEN_DIRECTORY).joinpath(pathlib.Path("tokens.json"))
)


def _create_token_directory():
    pathlib.Path(TOKEN_DIRECTORY).mkdir(parents=True, exist_ok=True)


def _get_native_client(
    token_store: Optional[str] = None,
    client_id: str = CLIENT_ID,
    client_name: str = CLIENT_NAME,
) -> Optional[NativeClient]:
    # use this rather than the actual default argument so we can chain multiple default
    # arguments (from `get_headers`)
    token_store = token_store or DEFAULT_TOKEN_FILE
    try:
        _create_token_directory()
        return NativeClient(
            client_id=CLIENT_ID,
            app_name=CLIENT_NAME,
            token_storage=JSONTokenStorage(token_store),
        )
    except FileNotFoundError:
        click.echo(
            (
                f"Unable to access or create file for token storage ({token_store});"
                "make sure the CLI would be allowed to create the directory if it"
                " doesn't exist, and/or open that file inside that directory"
            ),
            err=True,
        )
        return None


def _get_authorizer_for_scope(
    scope: str,
    all_scopes: List[str] = ALL_SCOPES,
    token_store: Optional[str] = None,
    client_id: str = CLIENT_ID,
    client_name: str = CLIENT_NAME,
) -> Optional[RefreshTokenAuthorizer]:
    client = _get_native_client(
        token_store=token_store, client_id=client_id, client_name=client_name
    )
    if client is not None:
        ssh_active = "SSH_CLIENT" in os.environ or "SSH_CONNECTION" in os.environ
        try:
            client.login(
                requested_scopes=all_scopes,
                refresh_tokens=True,
                no_browser=ssh_active,
                no_local_server=ssh_active,
            )
            authorizers = client.get_authorizers_by_scope(requested_scopes=all_scopes)
            return authorizers[scope]
        except (LocalServerError, AuthAPIError) as e:
            click.echo(f"Login Unsuccessful: {str(e)}", err=True)
            return None
    return None


def get_access_token_for_scope(
    token_store: Optional[str] = None, token_scope: str = TIMER_SERVICE_SCOPE
) -> Optional[str]:
    authorizer = _get_authorizer_for_scope(token_scope, token_store=token_store)
    if authorizer is not None:
        return authorizer.access_token
    else:
        return None


def logout(token_store: Optional[str] = None) -> bool:
    client = _get_native_client(token_store=token_store)
    if client:
        client.logout()
    return client is not None


def get_current_user(token_store: Optional[str] = None) -> Dict[str, Any]:
    authorizer = _get_authorizer_for_scope(
        AUTH_SCOPES[0],
        token_store=token_store,
    )
    auth_client = AuthClient(authorizer=authorizer)
    user_info = auth_client.oauth2_userinfo()
    return user_info.data
