import sys
from typing import List

import click
from globus_sdk import GlobusError, TransferClient

from timer_cli.auth import get_authorizer_for_scope

TRANSFER_ALL_SCOPE = "urn:globus:auth:scope:transfer.api.globus.org:all"


def endpoints_not_activated(endpoints: List[str]) -> List[str]:
    """
    Filter list of endpoint UUIDs, returning unactivated ones.

    Exit 1 if transfer responds with an error trying to look up endpoints.
    """
    transfer_client = get_transfer_client()
    result = []
    for endpoint in endpoints:
        try:
            if not transfer_client.get_endpoint(endpoint).get("activated"):
                result.append(endpoint)
        except GlobusError as e:
            click.echo(
                f"couldn't get information for endpoint {endpoint}:"
                f" {e.code}, {e.message}",
                err=True,
            )
            sys.exit(1)
    return result


def error_if_not_activated(endpoints: List[str]):
    not_activated = endpoints_not_activated(endpoints)
    if not_activated:
        click.echo(
            f"Requested endpoint is not activated: {', '.join(not_activated)}\n"
            "Open in the web app to activate:\n",
            err=True,
        )
        for endpoint in not_activated:
            click.echo(
                f"    https://app.globus.org/file-manager?origin_id={endpoint}",
                err=True,
            )
        sys.exit(1)


def get_transfer_client():
    transfer_authorizer = get_authorizer_for_scope(TRANSFER_ALL_SCOPE, all_scopes=[])
    return TransferClient(transfer_authorizer)
