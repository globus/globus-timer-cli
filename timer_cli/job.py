import datetime
import json
import os
import sys
import urllib
import uuid
from typing import Optional

import click
import requests
from timer_cli.auth import get_access_token_for_scope
from timer_cli.output import make_table, show_response

# how long to wait before giving up on requests to the API
TIMEOUT = 10


_DEFAULT_TIMER_SERVICE_URL = "https://sandbox.timer.automate.globus.org"

TIMER_SERVICE_URL = os.environ.get("TIMER_SERVICE_URL", _DEFAULT_TIMER_SERVICE_URL)

_TIMER_JOBS_URL = f"{TIMER_SERVICE_URL}/jobs"


def handle_requests_exception(e: Exception):
    click.echo(f"error in request: {e}", err=True)
    sys.exit(1)


def get_headers(token_store: Optional[str] = None) -> dict:
    """
    Assemble any needed headers that should go in all requests to the timer API, such
    as the access token.
    """
    access_token = get_access_token_for_scope(token_store=token_store)
    return {"Authorization": f"Bearer {access_token}"}


def job_submit(
    name: str,
    start: Optional[datetime.datetime],
    interval: int,
    scope: str,
    action_url: urllib.parse.ParseResult,
    action_body: Optional[str],
    action_file: Optional[click.File],
    callback_body: Optional[dict] = None,
) -> requests.Response:
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
    start_with_tz = start
    if start_with_tz.tzinfo is None:
        start_with_tz = start.astimezone()
    callback_url: str = action_url.geturl()
    req_json = {
        "name": name,
        "start": start_with_tz.isoformat(),
        "interval": interval,
        "scope": scope,
        "callback_url": callback_url,
        "callback_body": callback_body,
    }
    headers = get_headers()
    try:
        return requests.post(
            _TIMER_JOBS_URL,
            json=req_json,
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        handle_requests_exception(e)


def job_list(show_deleted: bool = False) -> requests.Response:
    headers = get_headers()
    params = dict()
    if show_deleted:
        params["show_deleted"] = True
    try:
        return requests.get(
            f"{_TIMER_JOBS_URL}",
            params=params,
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        handle_requests_exception(e)


def job_status(job_id: uuid.UUID, show_deleted: bool = False) -> requests.Response:
    headers = get_headers()
    params = dict()
    if show_deleted:
        params["show_deleted"] = True
    try:
        return requests.get(
            f"{_TIMER_JOBS_URL}/{job_id}",
            params=params,
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        handle_requests_exception(e)


def job_delete(job_id: uuid.UUID) -> requests.Response:
    headers = get_headers()
    try:
        return requests.delete(
            f"{_TIMER_JOBS_URL}/{job_id}",
            headers=headers,
            timeout=TIMEOUT,
        )
    except requests.RequestException as e:
        handle_requests_exception(e)


def _get_job_result(job_json: dict) -> str:
    last_result = "SUCCESS"
    job_results = job_json["results"]
    if len(job_results) == 0:
        last_result = "NOT RUN"
    else:
        last_result_status = job_results[0]["status"]
        # this could be better
        if last_result_status >= 400:
            last_result = "FAILURE"
    return last_result


def show_job(response: requests.Response, verbose: bool):
    if response.status_code >= 300:
        click.echo(
            f"Unable to retrieve job, request status {response.status_code} "
            f"body: {response.text}"
        )
        return
    if verbose:
        return show_response(response)
    try:
        job_json = response.json()
    except ValueError as e:
        # TODO: bad exit, do errors
        click.echo(f"couldn't parse json from job response: {e}", err=True)
        sys.exit(1)
    try:
        last_result = _get_job_result(job_json)
        job_info = [
            ("Name", job_json["name"]),
            ("Job ID", job_json["job_id"]),
            ("Status", job_json["status"]),
            ("Start", job_json["start"]),
            ("Interval", job_json["interval"]),
            ("Next Run At", job_json["next_run"]),
            ("Last Run Result", last_result),
        ]
    except (IndexError, KeyError) as e:
        # TODO: bad exit, do errors
        click.echo(f"failed to read info for job: {e}", err=True)
        sys.exit(1)
    key_width = max(len(k) for k, _ in job_info) + 2
    output = "\n".join([f"{k}: ".ljust(key_width) + str(v) for k, v in job_info])
    click.echo(output)


def show_job_list(response: requests.Response, verbose: bool):
    # TODO: absorb this chunk into shared function
    if verbose:
        return show_response(response)
    try:
        job_json = response.json()
    except ValueError as e:
        # TODO: bad exit, do errors
        click.echo(f"couldn't parse json from job response: {e}", err=True)
        sys.exit(1)
    headers = ["Name", "Job ID", "Status", "Last Result"]
    try:
        rows = [
            [job["name"], job["job_id"], job["status"], _get_job_result(job)]
            for job in job_json["jobs"]
        ]
    except (IndexError, KeyError) as e:
        # TODO: bad exit, do errors
        click.echo(f"failed to read info for job: {e}", err=True)
        sys.exit(1)
    table = make_table(headers, rows)
    click.echo(table)
