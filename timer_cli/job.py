import datetime
import json
import os
import sys
import urllib
import uuid
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union

import click
import requests

from timer_cli.auth import TIMER_SERVICE_SCOPE, get_access_token_for_scope
from timer_cli.output import make_table, show_response

# how long to wait before giving up on requests to the API
TIMEOUT = 10


_DEFAULT_TIMER_SERVICE_URL = "https://timer.automate.globus.org"

TIMER_SERVICE_URL = os.environ.get("TIMER_SERVICE_URL", _DEFAULT_TIMER_SERVICE_URL)

_TIMER_JOBS_URL = f"{TIMER_SERVICE_URL}/jobs"


def handle_requests_exception(e: Exception):
    click.echo(f"error in request: {e}", err=True)
    sys.exit(1)


def get_headers(
    token_store: Optional[str] = None, token_scope=TIMER_SERVICE_SCOPE
) -> Dict[str, str]:
    """
    Assemble any needed headers that should go in all requests to the timer API, such
    as the access token.
    """
    access_token = get_access_token_for_scope(
        token_store=token_store, token_scope=token_scope
    )
    return {"Authorization": f"Bearer {access_token}"}


def job_submit(
    name: str,
    start: Optional[datetime.datetime],
    interval: int,
    scope: str,
    action_url: urllib.parse.ParseResult,
    action_body: Optional[str] = None,
    action_file: Optional[click.File] = None,
    callback_body: Optional[dict] = None,
) -> requests.Response:
    if not callback_body:
        try:
            if action_body:
                action_body = action_body.strip("'").strip('"')
                callback_body = json.loads(action_body)
            elif action_file is not None:  # action_file
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
    # If there is a dependent scope on the job's scope, we trim that off as server-side
    # doesn't really understand that.
    send_job_scope = scope.split("[", 1)[0]
    req_json = {
        "name": name,
        "start": start_with_tz.isoformat(),
        "interval": interval,
        "scope": send_job_scope,
        "callback_url": callback_url,
        "callback_body": callback_body,
    }
    # Ww'll make the job scope dependent on the timer service's job creation scope so we
    # can be sure that we can do a dependent token grant on the token that is sent
    token_scope = f"{TIMER_SERVICE_SCOPE}[{scope}]"
    headers = get_headers(token_scope=token_scope)
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


def _get_job_result(job_json: dict) -> Optional[str]:
    if "results" not in job_json:
        return None
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


def _job_prop_name_map(
    job_json: Dict, prop_map: List[Tuple[str, Union[str, Callable]]]
) -> List[Tuple[str, str]]:
    """Map the job json (or any dict) from some unfriendly names to more friendly names on
    the keys. The input is the dict, and a list of friendly names, followed by unfriendly
    names or a callable which will generate the desired value for the friendly name.

    The return is a list of friendly name, value tuples
    """
    ret_map: list[tuple[str, str]] = []
    for prop_map_entry in prop_map:
        prop_val = job_json.get(prop_map_entry[1])
        if prop_val is not None:
            if callable(prop_val):
                prop_val = prop_val(job_json)
            ret_map.append((prop_map_entry[0], prop_val))
    return ret_map


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
        click.echo(
            f"couldn't parse json from job response: {e}: service response: {response.text}",
            err=True,
        )
        sys.exit(1)

    job_friendly_to_field_map = [
        ("Name", "name"),
        ("Job ID", "job_id"),
        ("Status", "status"),
        ("Start", "start"),
        ("Interval", "interval"),
        ("Next Run At", "next_run"),
        ("Last Run Result", _get_job_result),
    ]
    job_info = _job_prop_name_map(job_json, job_friendly_to_field_map)

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
        click.echo(
            f"couldn't parse json from job response: {e}: service response: {response.text}",
            err=True,
        )
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
