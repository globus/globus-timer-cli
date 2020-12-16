"""Module for handling Globus Auth dynamic dependency scopes, where
dependent scopes can be added to a scope string for a given resource
server to gain new tokens without statically defining them on the
resource server scope.

This module handles saving and loading Dynamic tokens inside Fair
Research Login (0.1.5 or later).
"""

import logging.config
import os
import re
from configparser import NoSectionError

from fair_research_login import ConfigParserTokenStorage, NativeClient
from fair_research_login.exc import LoadError, LoginException
from globus_sdk.exc import AuthAPIError

log = logging.getLogger(__name__)

CLIENT_ID = "7414f0b4-7d05-4bb6-bb00-076fa3f17cf5"
CONFIG_PATH = "dynamic_dep_test.cfg"

logging.config.dictConfig(
    {
        "version": 1,
        "formatters": {
            "basic": {
                "format": "[%(levelname)s] " "%(name)s::%(funcName)s() %(message)s"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "DEBUG",
                "formatter": "basic",
            }
        },
        "loggers": {
            "__main__": {"level": "DEBUG", "handlers": ["console"]},
        },
    }
)


class DynamicDependencyTokenStorage(ConfigParserTokenStorage):
    """Stores special Globus Auth tokens with dynamic dependencies attached
    to them. For example, scope strings can look like this:

    urn:globus:auth:scope:groups.api.globus.org:view_my_groups_and_memberships[openid]

    The scope above will return a normal token, but when passed to the
    groups.api.globus.org resource server, it will gain the openid
    scoped token when doing a dependent token grant.

    The following LIMITATIONS exist for this storage class:

    * Scopes MUST be passed in a list. No scope strings allowed. For example:

    DynamicDependencyTokenStorage(['myscope[openid]', 'openid'])  # correct
    DynamicDependencyTokenStorage('myscope[openid] openid')  # incorrect
    """

    CONFIG_FILENAME = os.path.expanduser(CONFIG_PATH)
    DEFAULT_SECTION = "tokens"
    DDS_SECTION = "dynamic_dependency_scopes"
    DEPENDENT_SCOPES_MATCHER = re.compile(r"([\w:./\-]+)\[?([\w:./\- ]+)*\]?")

    def __init__(self, filename: str, scopes: list):
        if isinstance(scopes, str):
            raise ValueError(f"Dynamic Dep Scopes must be a list: {scopes}")
        self.scopes = dict(self.split_dynamic_scopes(scopes))
        super().__init__(filename=filename, section="tokens")

    @classmethod
    def split_dynamic_scope(cls, dynamic_scope: str):
        match = cls.DEPENDENT_SCOPES_MATCHER.match(dynamic_scope)
        if not match:
            return dynamic_scope, None
        return match.groups()

    @classmethod
    def split_dynamic_scopes(cls, dynamic_scopes: list):
        return dict([cls.split_dynamic_scope(s) for s in dynamic_scopes])

    def get_section(self, scope: str):
        """

        Get the section for a given scope. If the scope has no dependent
        scopes, it goes into the normal section self.DEFAULT_SECTION.
        Otherwise, it gets put into a special separate section where the
        dependent scopes can be tracked.
        """
        if not self.scopes[scope]:
            return self.DEFAULT_SECTION
        cfg = self.load()
        # Add main DDS Section if it doesn't exist
        if self.DDS_SECTION not in cfg.sections():
            cfg.add_section(self.DDS_SECTION)
        # Check if the given scope and dependencies already exist, and if
        # so return that section instead
        for name, saved_scope_set in cfg.items(self.DDS_SECTION):
            if self.scopes[scope] == saved_scope_set:
                loaded_scopes = [
                    ts["scope"].split()
                    for ts in self.read_tokens_from_section(name).values()
                ]
                flat_scopes = {
                    scope for scope_list in loaded_scopes for scope in scope_list
                }
                if loaded_scopes and {scope}.intersection(flat_scopes):
                    return name

    def generate_section_name(self, scope_name):
        """Generate a human readable section name. This MUST be unique for each
        different scope, and MUST match identical scopes passed in. Otherwise,
        section names can be anything."""
        for s in ["https://auth.globus.org/scopes/", "urn:globus:auth:scope:"]:
            scope_name = scope_name.replace(s, "")
        for s in list(":./-"):
            scope_name = scope_name.replace(s, "_")
        # Ensure name is unique in config
        cfg = self.load()
        try:
            inc = len(cfg.items(self.DDS_SECTION))
        except NoSectionError:
            inc = 0
        candidate = f"{scope_name}_dds_{inc}"
        for candidate in cfg.sections():
            candidate = f"{scope_name}_dds_{inc}"
            inc += 1
        return candidate

    def create_section(self, scope: str):
        cfg = self.load()
        log.debug(f"Creating new section! {scope} -- {self.scopes[scope]}")
        scope_name = self.generate_section_name(scope)
        cfg.add_section(scope_name)

        if not cfg.has_section(self.DDS_SECTION):
            cfg.add_section(self.DDS_SECTION)

        cfg.set(self.DDS_SECTION, scope_name, self.scopes[scope])
        log.debug(f"Configured DDS Section: {scope_name} with " f"{self.scopes[scope]}")
        self.save(cfg)
        return scope_name

    def read_tokens_from_section(self, section):
        self.section = section
        return super().read_tokens()

    def write_tokens_to_section(self, tokens, section):
        self.section = section
        return super().write_tokens(tokens)

    def write_tokens(self, tokens):
        """Write tokens to disk. Saves normal tokens to the default section,
        and saves dynamic tokens to special sections."""
        no_dependency_scopes = {}
        dd_scopes = {s for s, ds in self.scopes.items() if ds}
        for rs, token_group in tokens.items():
            token_scopes = set(token_group["scope"].split())
            dependency_scope = list(dd_scopes.intersection(token_scopes))
            if dependency_scope:
                log.debug(f"Found dependency scope {dependency_scope}")
                section = self.get_section(dependency_scope[0])
                if not section:
                    section = self.create_section(dependency_scope[0])
                self.write_tokens_to_section({rs: token_group}, section)
                log.debug(f"wrote dynamic dependency token group {rs}")
            else:
                no_dependency_scopes[rs] = token_group
        self.write_tokens_to_section(no_dependency_scopes, self.DEFAULT_SECTION)

    def read_tokens(self):
        """Read tokens from disk. Loads all tokens from the default section,
        but replaces any tokens which were configured in self.scopes to have
        dynamic dependencies. Whatever dynamic dependencies were initially
        saved will be loaded."""
        tokens = self.read_tokens_from_section(self.DEFAULT_SECTION)
        for scope, dependencies in self.scopes.items():
            section = self.get_section(scope)
            if dependencies and section:
                # Replace any 'normal' tokens with any special dynamic scopes
                log.debug(
                    f"Loaded Scope: {scope}" f"\n\tDynamic Dependencies: {dependencies}"
                )
                tokens.update(self.read_tokens_from_section(section))
            # Edge case where 'normal' tokens exist, but dynamic tokens were
            # requested. Prevent 'normal' tokens from overriding dynamic ones.
            elif dependencies and not section:
                for tk_group in list(tokens.values()):
                    if {scope}.intersection(set(tk_group["scope"].split())):
                        del tokens[tk_group["resource_server"]]
        return tokens

    def load_all_tokens(self):
        """Returns all saved tokens in a list."""
        cfg = self.load()
        self.section = self.DEFAULT_SECTION
        tokens = [super().read_tokens()]
        for section, _ in cfg.items(self.DDS_SECTION):
            self.section = section
            tokens.append(super().read_tokens())
        return tokens

    def clear_tokens(self):
        self.section = self.DEFAULT_SECTION
        super().clear_tokens()
        cfg = self.load()
        for section, _ in cfg.items(self.DDS_SECTION):
            cfg.remove_section(section)
        cfg.remove_section(self.DDS_SECTION)
        cfg.add_section(self.DDS_SECTION)
        self.save(cfg)


def logout():
    """Revoke ALL tokens ever saved."""
    storage = DynamicDependencyTokenStorage([])
    client = NativeClient(client_id=CLIENT_ID, token_storage=storage)
    token_groups = storage.load_all_tokens()
    for tg in token_groups:
        log.debug(f"Revoking Tokens: {list(tg)}")
        client.revoke_token_set(tg)
    # Call base client logout for extra cleanup.
    client.logout()


if __name__ == "__main__":
    # Basic scopes test
    get_authorizers_for_scope(["openid", "profile", "email"])
    # Basic dynamic scopes test
    get_authorizers_for_scope(
        [
            "urn:globus:auth:scope:groups.api.globus.org:view_my_groups_and_memberships[openid]"
        ]
    )
    get_authorizers_for_scope(
        [
            "urn:globus:auth:scope:groups.api.globus.org:view_my_groups_and_memberships[profile]"
        ]
    )
    get_authorizers_for_scope(
        [
            "urn:globus:auth:scope:groups.api.globus.org:view_my_groups_and_memberships[email]"
        ]
    )
    get_authorizers_for_scope(
        [
            "urn:globus:auth:scope:groups.api.globus.org:view_my_groups_and_memberships[openid profile email]"
        ]
    )
    # # Test scopes with identical dependencies
    get_authorizers_for_scope(
        [
            "https://auth.globus.org/scopes/c7683485-3c3f-454a-94c0-74310c80b32a/https[openid]"
        ]
    )
    # Test passing multiple scopes
    get_authorizers_for_scope(
        [
            "urn:globus:auth:scope:groups.api.globus.org:view_my_groups_and_memberships[openid]",
            "openid",
        ]
    )
    # Test custom Globus App Scopes
    get_authorizers_for_scope(
        [
            "urn:globus:auth:scope:groups.api.globus.org:view_my_groups_and_memberships"
            "[https://auth.globus.org/scopes/c7683485-3c3f-454a-94c0-74310c80b32a/https]"
        ]
    )
    # Test multiple dependent
    get_authorizers_for_scope(
        [
            "urn:globus:auth:scope:groups.api.globus.org:view_my_groups_and_memberships"
            "[https://auth.globus.org/scopes/c7683485-3c3f-454a-94c0-74310c80b32a/https "
            "urn:globus:auth:scope:search.api.globus.org:search]"
        ]
    )
    # Test with custom Globus App scope with dependent scopes
    get_authorizers_for_scope(
        [
            "https://auth.globus.org/scopes/c7683485-3c3f-454a-94c0-74310c80b32a/https"
            "[urn:globus:auth:scope:groups.api.globus.org:view_my_groups_and_memberships "
            "urn:globus:auth:scope:search.api.globus.org:search]"
        ]
    )
    # Test two scopes from the same RS, one with a dependent scope
    get_authorizers_for_scope(
        [
            "openid[https://auth.globus.org/scopes/c7683485-3c3f-454a-94c0-74310c80b32a/https]",
            "profile",
        ]
    )
    # logout()
    print("Finished!")
