import json
from json import JSONDecodeError
import os
import pathlib
import platform
import sys
from typing import Any, Dict, List, NamedTuple, Optional

import click
from globus_sdk import AuthClient, NativeAppAuthClient
from globus_sdk.auth.token_response import OAuthTokenResponse
from globus_sdk.authorizers import GlobusAuthorizer, RefreshTokenAuthorizer
from globus_sdk.exc import AuthAPIError

CLIENT_ID = "bc77d044-1f42-46cc-9702-87f756cd08a6"
CLIENT_NAME = "Globus Timer Command Line Interface"
TIMER_SERVICE_SCOPE = "https://auth.globus.org/scopes/524230d7-ea86-4a52-8312-86065a9e0417/transfer_action"
AUTH_SCOPES = [
    "openid",
    "email",
    "profile",
]
ALL_SCOPES = AUTH_SCOPES + [TIMER_SERVICE_SCOPE]

DEFAULT_TOKEN_FILE = pathlib.Path.home() / pathlib.Path(".globus_timer_tokens.json")


class TokenSet(NamedTuple):
    access_token: str
    refresh_token: Optional[str]
    expiration_time: Optional[int]


class TokenCache:
    def __init__(self, token_store: str):
        self.token_store = token_store
        self.tokens: Dict[str, TokenSet] = {}
        self.modified = False

    def set_tokens(self, scope: str, tokens: TokenSet) -> TokenSet:
        print(f"DEBUG set_tokens (scope, tokens):= {(scope, tokens)}")
        self.tokens[scope] = tokens
        self.modified = True
        return tokens

    def get_tokens(self, scope: str) -> Optional[TokenSet]:
        return self.tokens.get(scope)

    def load_tokens(self):
        try:
            with open(self.token_store) as f:
                self.tokens = {k: TokenSet(**v) for k, v in json.load(f).items()}
        except (FileNotFoundError, JSONDecodeError):
            pass

    def save_tokens(self):
        if self.modified:
            with open(self.token_store, "w") as f:
                json.dump(
                    {k: v._asdict() for k, v in self.tokens.items()},
                    f,
                    indent=2,
                    sort_keys=True,
                    default=lambda s: str(x),
                )
        self.modified = False

    def update_from_oauth_token_response(
        self, token_response: OAuthTokenResponse
    ) -> Dict[str, TokenSet]:
        by_scopes = token_response.by_scopes
        token_sets: Dict[str, TokenSet] = {}
        for scope in by_scopes:
            token_info = by_scopes[scope]
            token_set = TokenSet(
                access_token=token_info.get("access_token"),
                refresh_token=token_info.get("refresh_token"),
                expiration_time=token_info.get("expires_at_seconds"),
            )
            self.set_tokens(scope, token_set)
            token_sets[scope] = token_set
        self.save_tokens()
        return token_sets


def _get_globus_sdk_native_client(
    client_id: str = CLIENT_ID,
    client_name: str = CLIENT_NAME,
):
    return NativeAppAuthClient(client_id, app_name=client_name)


def safeprint(s):
    try:
        print(s)
        sys.stdout.flush()
    except IOError:
        pass


def _do_login_for_scopes(
    native_client: NativeAppAuthClient, scopes: List[str]
) -> OAuthTokenResponse:
    label = CLIENT_NAME
    host = platform.node()
    if host:
        label = label + f" on {host}"
    native_client.oauth2_start_flow(
        requested_scopes=scopes,
        refresh_tokens=True,
        prefill_named_grant=label,
    )
    linkprompt = "Please log into Globus here"
    safeprint(
        "{0}:\n{1}\n{2}\n{1}\n".format(
            linkprompt, "-" * len(linkprompt), native_client.oauth2_get_authorize_url()
        )
    )
    auth_code = click.prompt("Enter the resulting Authorization Code here").strip()
    token_response = native_client.oauth2_exchange_code_for_tokens(auth_code)

    return token_response


def get_authorizers_for_scopes(
    scopes: List[str],
    token_store: Optional[str] = None,
    client_id: str = CLIENT_ID,
    client_name: str = CLIENT_NAME,
    no_login: bool = False,
) -> Dict[str, GlobusAuthorizer]:
    if token_store is None:
        token_store = str(DEFAULT_TOKEN_FILE)
    token_cache = TokenCache(token_store)
    token_cache.load_tokens()
    token_sets: Dict[str, TokenSet] = {}
    needed_scopes: Set[str] = set()
    native_client = _get_globus_sdk_native_client(client_id, client_name)

    for scope in scopes:
        token_set = token_cache.get_tokens(scope)
        if token_set is not None:
            token_sets[scope] = token_set
        else:
            needed_scopes.add(scope)

    if len(needed_scopes) > 0 and not no_login:
        token_response = _do_login_for_scopes(native_client, list(needed_scopes))
        new_tokens = token_cache.update_from_oauth_token_response(token_response)
        token_sets.update(new_tokens)

    authorizers: Dict[str, GlobusAuthorizer] = {}
    for scope, token_set in token_sets.items():
        if token_set is not None:
            if token_set.refresh_token is not None:

                def refresh_handler(
                    grant_response: OAuthTokenResponse, *args, **kwargs
                ):
                    new_tokens = token_cache.update_from_oauth_token_response(
                        grant_response
                    )

                authorizer = RefreshTokenAuthorizer(
                    token_set.refresh_token,
                    native_client,
                    access_token=token_set.access_token,
                    expires_at=token_set.expiration_time,
                    on_refresh=refresh_handler,
                )
                # Force check that the token is not expired
                authorizer.check_expiration_time()
            else:
                authorizer = AccessTokenAuthorizer(token_set.access_token)
            authorizers[scope] = authorizer
    return authorizers


def get_access_tokens_for_scopes(
    scopes: List[str],
    token_store: str = str(DEFAULT_TOKEN_FILE),
    client_id: str = CLIENT_ID,
    client_name: str = CLIENT_NAME,
) -> Dict[str, str]:
    authorizers = get_authorizers_for_scopes(
        scopes, token_store, client_id, client_name
    )
    return {k: v.access_token for k, v in authorizers.items()}


def get_access_token_for_scope(
    token_store: Optional[str] = None,
    token_scope: str = TIMER_SERVICE_SCOPE,
) -> Optional[str]:
    access_tokens = get_access_tokens_for_scopes([token_scope], token_store)
    return access_tokens.get(token_scope)


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
    client = _get_native_client([], token_store=token_store)
    if client:
        client.logout()
    return client is not None


def get_current_user(
    no_login: bool = False, token_store: str = DEFAULT_TOKEN_FILE
) -> Optional[Dict[str, Any]]:
    """
    When `no_login` is set, returns `None` if not logged in.
    """
    # We don't really care which scope from the AUTH_SCOPE list we use here since they
    # all share the same resource server (Auth itself) and therefore an authorizer for
    # any of them grants us access to the same resource server.
    authorizers = get_authorizers_for_scopes(
        AUTH_SCOPES, token_store=token_store, no_login=no_login
    )
    if not authorizers:
        return None
    auth_client = AuthClient(authorizer=authorizers.get("openid"))
    try:
        user_info = auth_client.oauth2_userinfo()
    except AuthAPIError as e:
        click.echo(
            (
                "Couldn't get user information from Auth service\n"
                "(If you rescinded your consents in the Auth service, do `session"
                " logout` and try again)\n"
                f"    Error details: {str(e)}"
            ),
            err=True,
        )
        sys.exit(1)
    return user_info.data
