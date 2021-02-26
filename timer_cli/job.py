import datetime
import json
import os
import sys
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union
import urllib
import uuid

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


def get_headers(token_scope: str = TIMER_SERVICE_SCOPE) -> Dict[str, str]:
    """
    Assemble any needed headers that should go in all requests to the timer API, such
    as the access token.
    """
    token = get_access_token_for_scope(token_scope)
    if not token:
        raise ValueError("couldn't get token")
    return {"Authorization": f"Bearer {token}"}


def job_submit(
    name: str,
    start: Optional[datetime.datetime],
    interval: int,
    scope: Optional[str],
    action_url: urllib.parse.ParseResult,
    action_body: Optional[str] = None,
    action_file: Optional[click.File] = None,
    callback_body: Optional[dict] = None,
    stop_after_date: Optional[datetime.datetime] = None,
    stop_after_runs: Optional[int] = None,
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
    if stop_after_date or stop_after_runs:
        req_json["stop_after"] = dict()
        if stop_after_date:
            req_json["stop_after"]["date"] = stop_after_date
        if stop_after_runs:
            req_json["stop_after"]["n_runs"] = stop_after_runs
    # Ww'll make the job scope dependent on the timer service's job creation scope so we
    # can be sure that we can do a dependent token grant on the token that is sent
    token_scope = f"{TIMER_SERVICE_SCOPE}[{scope}]"
    try:
        headers = get_headers(token_scope=token_scope)
    except (EnvironmentError, ValueError) as e:
        click.echo(str(e), err=True)
        sys.exit(1)
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
    last_result = "RUN COMPLETE"
    job_results = job_json["results"]
    if len(job_results) == 0:
        last_result = "NOT RUN"
    else:
        last_result_status = job_results[0].get("status") or 500
        # this could be better
        if last_result_status >= 400:
            last_result = "FAILURE"
    return last_result


def _job_prop_name_map(
    job_json: Dict, prop_map: List[Tuple[str, Union[str, Callable]]]
) -> List[Tuple[str, str]]:
    """
    Map the job json (or any dict) from some unfriendly names to more friendly names on
    the keys. The input is the dict, and a list of friendly names, followed by
    unfriendly names or a callable which will generate the desired value for the
    friendly name.

    The return is a list of friendly name, value tuples
    """
    ret_map: List[Tuple[str, str]] = []
    for prop_name, prop_mapper in prop_map:
        value = job_json.get(prop_mapper)
        if prop_mapper not in job_json and callable(prop_mapper):
            value = prop_mapper(job_json)
        ret_map.append((prop_name, value))
    return ret_map


def show_job(response: requests.Response, verbose: bool, was_deleted: bool = False):
    if response.status_code >= 300:
        try:
            msg = response.json().get("error", dict()).get("detail")
        except ValueError:
            msg = None
        finally:
            if msg:
                msg = f": {msg}"
            else:
                msg = ""
        click.echo(
            f"Unable to retrieve job{msg}\n"
            f"    Response status:  {response.status_code}\n"
            f"    Response body:    {response.text}"
        )
        return
    if verbose:
        return show_response(response)
    try:
        job_json = response.json()
    except ValueError as e:
        # TODO: this could return status---maybe add module with error hierarchy
        click.echo(f"couldn't parse json from job response: {e}", err=True)
        return
    show_job_json(job_json, was_deleted=was_deleted)


def show_job_json(job_json: dict, was_deleted: bool = False):
    try:
        job_friendly_to_field_map = [
            ("Name", "name"),
            ("Job ID", "job_id"),
            ("Status", "status"),
            ("Start", "start"),
            ("Interval", lambda d: str(datetime.timedelta(seconds=d["interval"]))),
        ]
        if not was_deleted:
            job_friendly_to_field_map.append(("Next Run At", "next_run"))
            job_friendly_to_field_map.append(("Last Run Result", _get_job_result))
    except (IndexError, KeyError) as e:
        click.echo(f"failed to read info for job: {str(e)}", err=True)
        return
    job_info = _job_prop_name_map(job_json, job_friendly_to_field_map)
    key_width = max(len(k) for k, _ in job_info) + 2
    output = "\n".join([f"{k}: ".ljust(key_width) + str(v) for k, v in job_info])
    click.echo(output)


def show_job_list(
    response: requests.Response,
    verbose: bool = False,
    as_table: bool = True,
) -> None:
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

    if not as_table:
        if "jobs" not in job_json:
            click.echo(f"failed to read info for job list: {e}", err=True)
            sys.exit(1)
        first = True
        for job in job_json["jobs"]:  # are we semantically satiated yet?
            # print empty separating line for each job after the first
            if not first:
                click.echo("")
            show_job_json(job)
            first = False
        return

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
