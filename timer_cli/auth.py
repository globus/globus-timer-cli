from collections import defaultdict
import json
from json import JSONDecodeError
import os
import pathlib
import platform
import sys
from typing import Any, Dict, List, NamedTuple, Optional, Set

import click
from globus_sdk import AuthClient, NativeAppAuthClient
from globus_sdk.auth.token_response import OAuthTokenResponse
from globus_sdk.authorizers import GlobusAuthorizer, RefreshTokenAuthorizer
from globus_sdk.exc import AuthAPIError

CLIENT_ID = "bc77d044-1f42-46cc-9702-87f756cd08a6"
CLIENT_NAME = "Globus Timer Command Line Interface"
TIMER_SERVICE_SCOPE = "https://auth.globus.org/scopes/524230d7-ea86-4a52-8312-86065a9e0417/timer"
AUTH_SCOPES = [
    "openid",
    "email",
    "profile",
]
ALL_SCOPES = AUTH_SCOPES + [TIMER_SERVICE_SCOPE]

DEFAULT_TOKEN_FILE = pathlib.Path.home() / pathlib.Path(".globus_timer_tokens.json")


def _get_base_scope(scope: str):
    if "[" in scope:
        return scope.split("[")[0]
    return scope


class TokenSet(NamedTuple):
    """
    Might want to check out this as a replacement:
    https://www.attrs.org/en/stable/why.html#namedtuples
    """

    access_token: str
    refresh_token: Optional[str]
    expiration_time: Optional[int]
    # Keep track of scopes associated with these tokens with the dependencies still
    # included. If we need to get a token where tokens for the base scope exist but
    # there isn't a matching dependent scope, that means we need to prompt for consent
    # again. If there is a matching full-scope-string in `dependent_scopes`, then we're
    # OK to use the token from looking up that base scope.
    dependent_scopes: Set[str]


class TokenCache:
    def __init__(self, token_store: str):
        self.token_store = token_store
        self.tokens: Dict[str, TokenSet] = {}
        self.modified = False
        self._fix_file_permissions()

    def _fix_file_permissions(self):
        """
        Make sure that the tokens file is set to read/write for user only.
        """
        if os.path.exists(self.token_store) and (os.stat(self.token_store).st_mode & 0o77) > 0:
                os.chmod(self.token_store, 0o600)

    def set_tokens(self, scope: str, tokens: TokenSet) -> TokenSet:
        if scope in self.tokens:
            dependent_scopes = set(tokens.dependent_scopes).union(
                set(self.tokens[scope].dependent_scopes)
            )
            new_token_set = TokenSet(
                access_token=tokens.access_token,
                refresh_token=tokens.refresh_token,
                expiration_time=tokens.expiration_time,
                dependent_scopes=dependent_scopes,
            )
            self.tokens[scope] = new_token_set
        else:
            self.tokens[scope] = tokens
        self.modified = True
        return tokens

    def get_tokens(self, scope: str) -> Optional[TokenSet]:
        if "[" in scope:
            # If the full scope string is in our mapping already, we can just return
            # the tokens. If not, even if we have a token for the base scope, we
            # shouldn't return that because it won't work for the new scope.
            base_scope = scope.split("[")[0]
            tokens = self.tokens.get(base_scope)
            if not tokens or scope not in getattr(tokens, "dependent_scopes", set()):
                return None
            else:
                return tokens
        return self.tokens.get(scope)

    def load_tokens(self):
        """
        May raise an EnvironmentError if the cache file exists but can't be read.
        """
        try:
            with open(self.token_store) as f:
                contents = json.load(f)
                self.tokens = {k: TokenSet(**v) for k, v in contents.items()}
        except FileNotFoundError:
            pass
        except JSONDecodeError:
            raise EnvironmentError(
                "Token cache for Timer CLI is corrupted; please run a `session revoke`"
                " and try again"
            )

    def save_tokens(self):
        def default(x):
            if isinstance(x, set):
                return list(x)
            return str(x)

        if self.modified:
            # disable permissions other than user read/write
            original_umask = os.umask(0o177)
            try:
                fd = os.open(self.token_store, os.O_WRONLY | os.O_CREAT, 0o600)
                with os.fdopen(fd, "w") as f:
                    json.dump(
                        {k: v._asdict() for k, v in self.tokens.items()},
                        f,
                        indent=2,
                        sort_keys=True,
                        default=default,
                    )
            finally:
                os.umask(original_umask)
        self.modified = False

    def update_from_oauth_token_response(
        self, token_response: OAuthTokenResponse, original_scopes: Set[str]
    ) -> Dict[str, TokenSet]:
        by_scopes = token_response.by_scopes
        token_sets: Dict[str, TokenSet] = {}
        for scope in by_scopes:
            token_info = by_scopes[scope]
            dependent_scopes = set(s for s in original_scopes if "[" in s)
            token_set = TokenSet(
                access_token=token_info.get("access_token"),
                refresh_token=token_info.get("refresh_token"),
                expiration_time=token_info.get("expires_at_seconds"),
                dependent_scopes=dependent_scopes,
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
    return native_client.oauth2_exchange_code_for_tokens(auth_code)


def get_authorizers_for_scopes(
    scopes: List[str],
    token_store: Optional[str] = None,
    client_id: str = CLIENT_ID,
    client_name: str = CLIENT_NAME,
    no_login: bool = False,
) -> Dict[str, GlobusAuthorizer]:
    token_store = token_store or str(DEFAULT_TOKEN_FILE)
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
        new_tokens = token_cache.update_from_oauth_token_response(
            token_response, set(scopes)
        )
        token_sets.update(new_tokens)

    authorizers: Dict[str, GlobusAuthorizer] = {}
    for scope, token_set in token_sets.items():
        if token_set is not None:
            if token_set.refresh_token is not None:

                def refresh_handler(
                    grant_response: OAuthTokenResponse, *args, **kwargs
                ):
                    new_tokens = token_cache.update_from_oauth_token_response(
                        grant_response, set([scope])
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
            authorizers[_get_base_scope(scope)] = authorizer
    return authorizers


def get_access_token_for_scope(scope: str) -> Optional[str]:
    authorizer = get_authorizers_for_scopes([scope]).get(_get_base_scope(scope))
    if not authorizer:
        click.echo(f"couldn't obtain authorizer for scope: {scope}", err=True)
        return None
    token = getattr(authorizer, "access_token", None)
    if not token:
        click.echo("authorizer failed to get token from Globus Auth")
        return None
    return token


def logout(token_store: str = DEFAULT_TOKEN_FILE) -> bool:
    try:
        os.remove(token_store)
    except OSError:
        click.echo("couldn't remove token cache file", err=True)
        return False
    return True


def revoke_login(token_store: str = DEFAULT_TOKEN_FILE) -> bool:
    client = _get_globus_sdk_native_client(CLIENT_ID, CLIENT_NAME)
    if not client:
        click.echo("failed to get auth client", err=True)
        return False
    cache = TokenCache(token_store)
    for token_set in cache.tokens.values():
        client.oauth2_revoke_token(token_set.access_token)
        client.oauth2_revoke_token(token_set.refresh_token)
    if not logout(token_store):
        return False
    return True


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
