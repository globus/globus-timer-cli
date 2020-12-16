import os
import pathlib
from typing import Any, Dict, List, Optional

import click
from fair_research_login.client import NativeClient
from fair_research_login.exc import LoadError, LoginException
from globus_sdk import AuthClient
from globus_sdk.authorizers import GlobusAuthorizer
from globus_sdk.exc import AuthAPIError

from timer_cli.dynamic_dep_storage import DynamicDependencyTokenStorage

CLIENT_ID = "bc77d044-1f42-46cc-9702-87f756cd08a6"
CLIENT_NAME = "Globus Timer Command Line Interface"
TIMER_SERVICE_SCOPE = "https://auth.globus.org/scopes/524230d7-ea86-4a52-8312-86065a9e0417/transfer_action"
AUTH_SCOPES = [
    "openid",
    "email",
    "profile",
]
ALL_SCOPES = AUTH_SCOPES + [TIMER_SERVICE_SCOPE]

DEFAULT_TOKEN_FILE = pathlib.Path.home() / pathlib.Path(".globus_timer_tokens.cfg")


def _get_native_client(
    scopes: List[str],
    token_store: Optional[str] = None,
    client_id: str = CLIENT_ID,
    client_name: str = CLIENT_NAME,
) -> Optional[NativeClient]:
    # use this rather than the actual default argument so we can chain multiple default
    # arguments (from `get_headers`)
    token_store = token_store or DEFAULT_TOKEN_FILE
    try:
        return NativeClient(
            client_id=CLIENT_ID,
            app_name=CLIENT_NAME,
            token_storage=DynamicDependencyTokenStorage(token_store, scopes),
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


def get_authorizers_for_scope(
    scopes: List[str],
    token_store: Optional[str] = None,
    client_id: str = CLIENT_ID,
    client_name: str = CLIENT_NAME,
    no_login: bool = False,
) -> Optional[Dict[str, GlobusAuthorizer]]:
    client = _get_native_client(
        scopes, token_store=token_store, client_id=client_id, client_name=client_name
    )
    if no_login:
        try:
            client.load_tokens(requested_scopes=ALL_SCOPES)
        except LoadError:
            return None
    try:
        dd_scopes = DynamicDependencyTokenStorage.split_dynamic_scopes(scopes)
        base_scopes = list(dd_scopes)
        try:
            # This first attempt will load tokens without logging in. Note that
            # only base_scopes are passed to the client. FRL currently can't
            # handle dynamic scopes, so storage will automatically determine
            # the correct scopes to load based on the scopes passed in above.
            return client.get_authorizers_by_scope(requested_scopes=base_scopes)
        except (LoadError, KeyError):
            client.login(
                # Loading tokens failed, so a login is initiated. Note that
                # the full dynamic dependencies are passed here. Since these
                # are automatically passed to Globus Auth, FRL doesn't notice
                # they are scopes with dynamic dependencies.
                requested_scopes=scopes,
                refresh_tokens=True,
            )
            return client.get_authorizers_by_scope(requested_scopes=base_scopes)
    except (LoginException, AuthAPIError) as e:
        print(f"Login Unsuccessful: {str(e)}")
        raise SystemExit


def get_authorizer_for_scope(
    scope: str,
    all_scopes: List[str] = ALL_SCOPES,
    token_store: Optional[str] = None,
    client_id: str = CLIENT_ID,
    client_name: str = CLIENT_NAME,
    no_login: bool = False,
) -> Optional[GlobusAuthorizer]:
    authorizers = get_authorizers_for_scope(
        [scope] + all_scopes,
        token_store=token_store,
        client_id=client_id,
        client_name=client_name,
        no_login=no_login,
    )
    if not authorizers:
        return None
    base_scope = scope.split("[", 1)[0]
    authorizer = authorizers.get(base_scope)
    return authorizer


def get_access_token_for_scope(
    token_store: Optional[str] = None,
    token_scope: str = TIMER_SERVICE_SCOPE,
) -> Optional[str]:
    authorizer = get_authorizer_for_scope(token_scope, token_store=token_store)
    if authorizer is not None:
        return authorizer.access_token
    else:
        return None


def logout(token_store: str = DEFAULT_TOKEN_FILE) -> bool:
    try:
        os.remove(token_store)
        return True
    except OSError:
        return False


def revoke_login(token_store: str = DEFAULT_TOKEN_FILE) -> bool:
    """
    This calls the fair research login function logout on the client. This has two side
    effects:

    1. It revokes the tokens that it has been issued. This means that any place those
    tokens (including refresh tokens) are in use, they will no longer be valid tokens.
    This can be a problem for services like timer that refresh and re-use tokens over a
    long period of time.

    2. It removes the token store file. This is good as it essentially causes the user
    to re-login on next use.
    """
    client = _get_native_client(token_store=token_store)
    if client:
        client.logout()
    return client is not None


def get_current_user(
    token_store: Optional[str] = None,
    no_login: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    When `no_login` is set, returns `None` if not logged in.
    """
    # We don't really care which scope from the AUTH_SCOPE list we use here since they
    # all share the same resource server (Auth itself) and therefore an authorizer for
    # any of them grants us access to the same resource server.
    authorizer = get_authorizer_for_scope(
        AUTH_SCOPES[0],
        token_store=token_store,
        no_login=no_login,
    )
    if not authorizer:
        return None
    auth_client = AuthClient(authorizer=authorizer)
    user_info = auth_client.oauth2_userinfo()
    return user_info.data
