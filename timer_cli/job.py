import datetime
import json
import sys
from typing import Optional
import urllib
import uuid

import click
import requests

from timer_cli.auth import get_access_token

# how long to wait before giving up on requests to the API
TIMEOUT = 10


def handle_requests_exception(e: Exception):
    click.echo(f"error in request: {e}", err=True)
    sys.exit(1)


def get_headers(token_store: Optional[str] = None) -> dict:
    """
    Assemble any needed headers that should go in all requests to the timer API, such
    as the access token.
    """
    access_token = get_access_token(token_store=token_store)
    return {"Authorization": f"Bearer {access_token}"}


def job_submit(
    name: str,
    start: Optional[click.DateTime],
    interval: int,
    scope: str,
    action_url: urllib.parse.ParseResult,
    action_body: Optional[str],
    action_file: Optional[click.File],
    callback_body: Optional[dict] = None,
):
    if not callback_body:
        try:
            if action_body:
                callback_body = action_body.strip("'").strip('"')
                callback_body = json.loads(action_body)
            else:  # action_file
                callback_body = json.load(action_file)
        except (TypeError, ValueError) as e:
            raise click.BadOptionUsage(
                "action-body",
                f"--action-body must parse into valid JSON; got error: {e}",
            )
    start = start or datetime.datetime.now()
    callback_url: str = action_url.geturl()
    req_json = {
        "name": name,
        "start": start.isoformat(),
        "interval": interval,
        "scope": scope,
        "callback_url": callback_url,
        "callback_body": callback_body,
    }
    headers = get_headers()
    try:
        return requests.post(
            "https://sandbox.timer.automate.globus.org/jobs/",
            json=req_json,
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        handle_requests_exception(e)
        return


def job_list():
    headers = get_headers()
    try:
        return requests.get(
            f"https://sandbox.timer.automate.globus.org/jobs/",
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        handle_requests_exception(e)
        return


def job_status(job_id: uuid.UUID):
    headers = get_headers()
    try:
        return requests.get(
            f"https://sandbox.timer.automate.globus.org/jobs/{job_id}",
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        handle_requests_exception(e)
        return


def job_delete(job_id: uuid.UUID):
    headers = get_headers()
    try:
        return requests.delete(
            f"https://sandbox.timer.automate.globus.org/jobs/{job_id}",
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        handle_requests_exception(e)
        return
