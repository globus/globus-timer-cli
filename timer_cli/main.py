"""
TODO:
    - look into https://github.com/click-contrib/click-help-colors
"""

from csv import DictReader
import datetime
from distutils.util import strtobool
import json
import re
import sys
from typing import Dict, Generator, Iterable, List, Optional, Tuple, Union
import urllib.parse
import uuid

import click
from globus_sdk import TransferClient

from timer_cli.auth import get_current_user
from timer_cli.auth import logout as auth_logout
from timer_cli.auth import revoke_login
from timer_cli.job import (
    job_delete,
    job_list,
    job_status,
    job_submit,
    show_job,
    show_job_list,
)
from timer_cli.output import make_table
from timer_cli.transfer import (
    TRANSFER_ALL_SCOPE,
    error_if_not_activated,
    get_transfer_client,
)

# List of datetime formats accepted as input. (`%z` means timezone.)
DATETIME_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S%z",
]


# TODO: make configurable/environment/maybe even check terminal width?
MAX_CONTENT_WIDTH = 100


timedelta_regex = re.compile(
    r"\s*((?P<weeks>\d+)w)?"
    r"\s*((?P<days>\d+)d)?"
    r"\s*((?P<hours>\d+)h)?"
    r"\s*((?P<minutes>\d+)m)?"
    r"\s*((?P<seconds>\d+)s?)?"
)


INTERVAL_HELP = (
    "Interval at which the job should run. Use 'w', 'd', 'h', 'm', and 's' as suffixes"
    " to specify weeks, days, hours, minutes, and seconds. Examples: '1h 30m', '500s',"
    " '24h', '1d 12h', '2w', etc. Must be in order: hours -> minutes -> seconds. You"
    " should either use quotes ('1d 2h') or write without spaces (1d2h)."
)


def _parse_timedelta(s: str) -> datetime.timedelta:
    groups = {k: int(v) for k, v in timedelta_regex.match(s).groupdict(0).items()}
    # timedelta accepts kwargs for units up through days, have to convert weeks
    groups["days"] += groups.pop("weeks", 0) * 7
    return datetime.timedelta(**groups)


def _un_parse_opt(opt: str):
    return "--" + opt.replace("_", "-")


def _read_csv(
    file_name: str,
    fieldnames=["source_path", "destination_path", "recursive"],
    comment_char: str = "#",
) -> Generator[Dict[str, Union[str, bool]], None, None]:
    def decomment(f):
        for row in f:
            if not row.startswith(comment_char):
                yield row

    def transform_val(k: str, v: str) -> Union[str, bool]:
        v = v.strip()
        # Was hoping to make this a bit more generic, but spent enough time on it so,
        # handling the case we actually need here
        if k == "recursive":
            try:
                return bool(strtobool(v))
            except ValueError:
                # "invalid truth value"
                click.echo(f"In file {file_name}: couldn't parse {v} as a truth value")
                sys.exit(1)
        else:
            return v

    with open(file_name, "r") as f:
        reader = DictReader(decomment(f), fieldnames=fieldnames)
        for row_dict in reader:
            yield {k: transform_val(k, v) for k, v in row_dict.items()}


def _get_required_data_access_scopes(
    tc: TransferClient,
    collection_ids: Iterable[str],
) -> List[str]:
    data_access_scopes: List[str] = []
    for collection_id in collection_ids:
        collection_id_info = tc.get_endpoint(collection_id)
        if collection_id_info["DATA_TYPE"] == "endpoint":
            gcs_version = collection_id_info.get("gcs_version")
            if gcs_version is None:
                continue
            gcs_version_parts = [int(x) for x in gcs_version.split(".")]
            requires_data_access = all(
                [
                    gcs_version_parts[0] > 5
                    or gcs_version_parts[0] == 5
                    and gcs_version_parts[1] >= 4,
                    (collection_id_info.get("high_assurance", True) is False),
                    collection_id_info.get("host_endpoint", True) is None,
                ]
            )
            if requires_data_access:
                data_access_scopes.append(
                    f"https://auth.globus.org/scopes/{collection_id}/data_access"
                )
    return data_access_scopes


def show_usage(cmd: click.Command):
    """
    Show the relevant usage and exit.

    The actual usage message is also specific to incomplete commands, thanks to using
    the click context.
    """
    ctx = click.get_current_context()
    # TODO: disabling this next line for the time being because of inconsistent
    # behavior between this function and calling --help directly, which would produce
    # different output. still have to figure that out
    # ctx.max_content_width = MAX_CONTENT_WIDTH
    formatter = ctx.make_formatter()
    cmd.format_help_text(ctx, formatter)
    cmd.format_options(ctx, formatter)
    cmd.format_epilog(ctx, formatter)
    click.echo(formatter.getvalue().rstrip("\n"))
    ctx.exit(2)


class Command(click.Command):
    """
    Subclass click.Command to show help message if a command is missing arguments.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def make_context(self, *args, **kwargs):
        """
        This is a semi-internal method on Commands that starts the parsing to create a
        new context. We hook into that here to catch any immediate parsing errors
        (missing arguments etc.) to exit and show our usage message.
        """
        try:
            return super().make_context(*args, **kwargs)
        except (
            click.BadArgumentUsage,
            click.BadOptionUsage,
            click.BadParameter,
            click.MissingParameter,
        ) as e:
            e.cmd = None
            e.show()
            click.echo()
            show_usage(self)


class MutuallyExclusive(click.Option):
    """
    Based on the answer for: https://stackoverflow.com/q/44247099
    """

    def __init__(self, *args, **kwargs):
        self.mutually_exclusive = kwargs.pop("mutually_exclusive")
        assert self.mutually_exclusive, "'mutually_exclusive' parameter required"
        super().__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        self_exists = self.name in opts
        mutually_exclusive_exists = self.mutually_exclusive in opts
        if self_exists and mutually_exclusive_exists:
            raise click.UsageError(
                f"Illegal usage: `{self.name}` is mutually exclusive with"
                f" `{self.mutually_exclusive}`"
            )
        if not (self_exists or mutually_exclusive_exists):
            full_options_names = ", ".join(
                [
                    "/".join(opt.opts)
                    for opt in ctx.command.params
                    if opt.name in self.mutually_exclusive or opt == self
                ]
            )
            raise click.UsageError(
                "Illegal usage: one of the following options is required:"
                f" {full_options_names}"
            )
        return super().handle_parse_result(ctx, opts, args)


def _get_options_flags(options: Iterable[click.Option]):
    """
    Given a list of options, produce a list of formatted option flags, like
    "--verbose/-v".
    """
    return ", ".join(["/".join(opt.opts) for opt in options])


class JointlyExhaustive(click.Option):
    """
    "Jointly exhaustive", meaning that at least one must occur.
    """

    def __init__(self, *args, **kwargs):
        self.jointly_exhaustive: List[str] = kwargs.pop("jointly_exhaustive")
        assert self.jointly_exhaustive, "'jointly_exhaustive' parameter required"
        super().__init__(*args, **kwargs)

    def handle_parse_result(self, ctx, opts, args):
        options_exist = [opt in opts for opt in self.jointly_exhaustive]
        options_exist.append(self.name in opts)
        if not any(options_exist):
            ctx = click.get_current_context()
            full_options_names = ", ".join(
                [
                    "/".join(opt.opts)
                    for opt in ctx.command.params
                    if opt.name in self.jointly_exhaustive or opt == self
                ]
            )
            raise click.UsageError(
                "Must provide at least one of the following options:"
                f" {full_options_names}"
            )
        return super().handle_parse_result(ctx, opts, args)


class URL(click.ParamType):
    """Click param type for a URL."""

    name = "url"

    def convert(self, value, param, ctx):
        if not isinstance(value, tuple):
            value = urllib.parse.urlparse(value)
            if not value.netloc:
                self.fail("incomplete URL")
            if value.scheme not in ("http", "https"):
                self.fail(
                    f"invalid URL scheme ({value.scheme}). Only HTTP URLs are allowed",
                    param,
                    ctx,
                )
        return value


cli = click.Group()


@cli.group(help="Commands for managing periodic Globus Transfer jobs.")
def job():
    pass


@job.command(cls=Command)
@click.option(
    "--name",
    required=True,
    type=str,
    help="Name to identify this job in the timer service (not necessarily unique)",
)
@click.option(
    "--start",
    required=False,
    type=click.DateTime(formats=DATETIME_FORMATS),
    help=(
        "Start time for the job. Defaults to current time. (The example above shows the"
        " allowed formats using Python's datetime formatters; see:"
        " https://docs.python.org/3/library/datetime.html"
        "#strftime-and-strptime-format-codes"
    ),
)
@click.option(
    "--interval",
    required=True,
    type=str,
    help=INTERVAL_HELP,
)
@click.option(
    "--scope",
    required=True,
    type=str,
    help="Globus Auth scope needed for this action",
)
@click.option(
    "--action-url",
    required=True,
    type=URL(),
    help=(
        "The URL for the action to run, e.g. "
        "https://actions.automate.globus.org/transfer/transfer/run"
    ),
)
@click.option(
    "--action-body",
    required=False,
    type=str,
    help=(
        "request JSON body to send to the action provider on job execution (NOTE:"
        " mutually exclusive with --action-file)"
    ),
    cls=MutuallyExclusive,
    mutually_exclusive="action_file",
)
@click.option(
    "--action-file",
    required=False,
    type=click.File("r"),
    help=(
        "path to a file containing JSON to send to the action provider on job"
        " execution (NOTE: mutually exclusive with --action-body)"
    ),
    cls=MutuallyExclusive,
    mutually_exclusive="action_body",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show full JSON output",
)
def submit(
    name: str,
    start: Optional[datetime.datetime],
    interval: str,
    scope: str,
    action_url: urllib.parse.ParseResult,
    action_body: Optional[str],
    action_file: Optional[click.File],
    verbose: bool,
):
    """
    Submit a job.
    """
    interval_seconds = _parse_timedelta(interval).total_seconds()
    if not interval_seconds:
        raise click.UsageError(f"Couldn't parse interval: {interval}")
    if interval_seconds < 60:
        raise click.UsageError(f"Interval is too short, minimum is 1 minute")
    response = job_submit(
        name,
        start,
        interval_seconds,
        scope,
        action_url,
        action_body,
        action_file,
    )
    show_job(response, verbose=verbose)


@job.command(cls=Command)
@click.option(
    "--show-deleted",
    required=False,
    is_flag=True,
    help="Whether to include deleted jobs in the output",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show full JSON output",
)
def list(show_deleted: bool, verbose: bool):
    """
    List submitted jobs.

    Note that, in the non-verbose output, `Last Result` is reporting according to
    whether Automate could successfully submit the job. It's possible for Transfer
    to run into errors attempting to run your submission, which timer/Automate are not
    aware of.

    CHECK THE --verbose OUTPUT TO BE CERTAIN YOUR TRANSFERS ARE WORKING.
    """
    response = job_list(show_deleted=show_deleted)
    show_job_list(response, verbose=verbose)


@job.command(cls=Command)
@click.option(
    "--all",
    "-a",
    "show_all",
    is_flag=True,
    help="Show status for all jobs",
)
@click.option(
    "--show-deleted",
    required=False,
    is_flag=True,
    help="Whether to include deleted jobs in the output",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show full JSON output",
)
@click.argument("job_id", type=uuid.UUID, required=False)
def status(
    job_id: Optional[uuid.UUID], show_deleted: bool, verbose: bool, show_all: bool
):
    """
    Return the status of the job with the given ID.

    Note that, in the non-verbose output, `Last Result` is reporting according to
    whether Automate could successfully submit the job. It's possible for Transfer
    to run into errors attempting to run your submission, which timer/Automate are not
    aware of.

    CHECK THE --verbose OUTPUT TO BE CERTAIN YOUR TRANSFERS ARE WORKING.
    """
    if not job_id and not show_all:
        click.echo(
            "Error: must provide either a job ID or the --all option\n", err=True
        )
        show_usage(click.get_current_context().command)
    if show_all:
        show_job_list(job_list(), as_table=False, verbose=verbose)
    else:
        show_job(job_status(job_id, show_deleted=show_deleted), verbose=verbose)


@job.command(cls=Command)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show full JSON output",
)
@click.argument("job_ids", type=uuid.UUID, nargs=-1)
def delete(job_ids: Iterable[uuid.UUID], verbose: bool):
    start = True
    for job_id in job_ids:
        if not start:
            click.echo("")
        show_job(job_delete(job_id), verbose=verbose, was_deleted=True)
        start = False


@job.command(cls=Command)
@click.option(
    "--name",
    required=True,
    type=str,
    help="Name to identify this job in the timer service (not necessarily unique)",
)
@click.option(
    "--start",
    required=False,
    type=click.DateTime(formats=DATETIME_FORMATS),
    help=("Start time for the job (defaults to current time)"),
)
@click.option(
    "--interval",
    required=True,
    type=str,
    help=INTERVAL_HELP,
)
@click.option(
    "--source-endpoint",
    required=True,
    type=str,
    help="ID for the source transfer endpoint",
)
@click.option(
    "--dest-endpoint",
    required=True,
    type=str,
    help="ID for the destination transfer endpoint",
)
@click.option(
    "--label",
    required=False,
    type=str,
    help=(
        "An optional label for the transfer operation, up to 128 characters long. Must"
        " contain only letters/numbers/spaces, and the following characters: - _ ,"
    ),
)
@click.option(
    "--stop-after-date",
    required=False,
    type=click.DateTime(formats=DATETIME_FORMATS),
    help=("Stop running the transfer after this date"),
)
@click.option(
    "--stop-after-runs",
    required=False,
    type=int,
    help=("Stop running the transfer after this number of runs have happened"),
)
@click.option(
    "--sync-level",
    required=False,
    type=int,
    help=(
        "Specify that only new or modified files should be transferred. The behavior"
        " depends on the value of this parameter, which must be a value 0--3, as"
        " defined in the transfer API: 0. Copy files that do not exist at the"
        " destination. 1. Copy files if the size of the destination does not match the"
        " size of the source. 2. Copy files if the timestamp of the destination is"
        " older than the timestamp of the source. 3. Copy files if checksums of the"
        " source and destination do not match."
    ),
)
@click.option(
    "--encrypt-data",
    is_flag=True,
    default=False,
    help="Whether Transfer should encrypt data sent through the network using TLS",
)
@click.option(
    "--verify-checksum",
    is_flag=True,
    default=False,
    help=(
        "Whether Transfer should verify file checksums and retry if the source and"
        " destination don't match"
    ),
)
@click.option(
    "--preserve-timestamp",
    is_flag=True,
    default=False,
    help=(
        "Whether Transfer should set file timestamps on the destination to match the"
        " origin"
    ),
)
@click.option(
    "--item",
    "-i",
    required=False,
    type=(str, str, bool),
    multiple=True,
    cls=JointlyExhaustive,
    jointly_exhaustive=["items_file"],
    help=(
        "Used to specify the transfer items; provide as many of this option as files"
        " to transfer. The format for this option is `--item SRC DST RECURSIVE`, where"
        " RECURSIVE specifies, if this item is a directory, to transfer the entire"
        " directory. For example: `--item ~/file1.txt ~/new_file1.txt false`"
    ),
)
@click.option(
    "--items-file",
    required=False,
    type=str,
    cls=JointlyExhaustive,
    jointly_exhaustive=["item"],
    help="file containing table of items to transfer",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Show full JSON output",
)
def transfer(
    name: str,
    start: Optional[datetime.datetime],
    interval: str,
    source_endpoint: str,
    dest_endpoint: str,
    label: Optional[str],
    stop_after_date: Optional[datetime.datetime],
    stop_after_runs: Optional[int],
    sync_level: Optional[int],
    encrypt_data: bool,
    verify_checksum: bool,
    preserve_timestamp: bool,
    item: Optional[List[Tuple[str, str, Optional[str]]]],
    items_file: Optional[str],
    verbose: bool,
):
    """
    Submit a task for periodic transfer or sync using Globus transfer. The options for
    this command are tailored to the transfer action.
    """
    action_url = urllib.parse.urlparse(
        "https://actions.automate.globus.org/transfer/transfer/run"
    )
    endpoints = [source_endpoint, dest_endpoint]
    tc = get_transfer_client()
    error_if_not_activated(tc, endpoints)
    data_access_scopes = _get_required_data_access_scopes(tc, endpoints)
    transfer_ap_scope = (
        "https://auth.globus.org/scopes/actions.globus.org/transfer/transfer"
    )
    if len(data_access_scopes) > 0:
        transfer_ap_scope = (
            f"{transfer_ap_scope}[{TRANSFER_ALL_SCOPE}[{' '.join(data_access_scopes)}]]"
        )
    # Just declare it for typing purposes
    transfer_items: List[Dict[str, Union[str, bool]]] = []
    if item:
        transfer_items = [
            {
                "source_path": i[0].strip(),
                "destination_path": i[1].strip(),
                "recursive": i[2],
            }
            for i in item
        ]
    elif items_file:
        # Unwind the generator
        transfer_items = [i for i in _read_csv(items_file)]

    action_body = {
        "source_endpoint_id": source_endpoint,
        "destination_endpoint_id": dest_endpoint,
        "transfer_items": transfer_items,
    }
    if label:
        action_body["label"] = label
    else:
        action_body["label"] = f"Job from Timer service named {name}"
    if sync_level is not None:
        action_body["sync_level"] = sync_level
    action_body["encrypt_data"] = encrypt_data
    action_body["verify_checksum"] = verify_checksum
    action_body["preserve_timestamp"] = preserve_timestamp
    callback_body = {"body": action_body}
    interval_seconds = _parse_timedelta(interval).total_seconds()
    if not interval_seconds:
        raise click.UsageError(f"Couldn't parse interval: {interval}")
    if interval_seconds < 60:
        raise click.UsageError(f"Interval is too short, minimum is 1 minute")
    response = job_submit(
        name,
        start,
        interval_seconds,
        transfer_ap_scope,
        action_url,
        action_body=None,
        action_file=None,
        callback_body=callback_body,
        stop_after_date=stop_after_date,
        stop_after_runs=stop_after_runs,
    )
    show_job(response, verbose=verbose)


@cli.group(help="Commands related to managing your Globus Auth credentials.")
def session():
    pass


@session.command(
    help="Cache identity information for future operations. This is "
    "optional, as it will be done on demand if this command is not used."
)
def login():
    user_info = get_current_user()
    click.echo(f"Logged in as {user_info['preferred_username']}")


@session.command(help="Print information about your currently logged in session.")
@click.option(
    "--format",
    type=click.Choice(["brief", "full", "json"], case_sensitive=False),
    default="brief",
    help="Select the detail level and format for output.",
)
def whoami(format: str):
    user_info = get_current_user(no_login=True)
    if not user_info:
        click.echo(
            "Not logged in yet; use `globus-timer session login` to initialize your"
            " session",
            err=True,
        )
        sys.exit(1)
    full_fields = ["name", "email", "preferred_username", "organization"]
    if format == "brief":
        click.echo(f"{user_info['preferred_username']}")
    elif format == "full":
        click.echo(make_table(full_fields, [[user_info[k] for k in full_fields]]))
    elif format == "json":
        click.echo(json.dumps({k: user_info[k] for k in full_fields}, indent=2))


@session.command(help="Remove the saved Globus Auth identity identity information.")
def logout():
    logged_out = auth_logout()
    if logged_out:
        click.echo("Successfully logged out.")
    else:
        click.echo("Unable to remove stored tokens to perform the logout.")


@session.command(help="Remove Timer's authorization to use your credentials.")
def revoke():
    if revoke_login():
        click.echo("Successfully revoked permission for all Timer operations.")
    else:
        click.echo("Unable to revoke login.")


def main():
    cli()


if __name__ == "__main__":
    cli()
