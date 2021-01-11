import sys
from typing import List

import click
from globus_sdk import GlobusError, TransferClient

from timer_cli.auth import get_authorizer_for_scope

TRANSFER_ALL_SCOPE = "urn:globus:auth:scope:transfer.api.globus.org:all"


def endpoints_not_activated(
    transfer_client: TransferClient, endpoints: List[str]
) -> List[str]:
    """
    Filter list of endpoint UUIDs, returning unactivated ones.

    Exit 1 if transfer responds with an error trying to look up endpoints.
    """
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


def error_if_not_activated(endpoints: List[str], reactivate_if_expires_in=86400):
    transfer_client = get_transfer_client()
    not_activated = endpoints_not_activated(transfer_client, endpoints)
    still_not_activated = []
    for endpoint in not_activated:
        response = transfer_client.endpoint_autoactivate(
            endpoint, if_expires_in=reactivate_if_expires_in
        )
        if response.get("code") == "AutoActivationFailed":
            still_not_activated.append(endpoint)
    if still_not_activated:
        click.echo(
            f"Error: requested endpoint is not activated: {', '.join(not_activated)}\n"
            "Open in the web app to activate:",
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
