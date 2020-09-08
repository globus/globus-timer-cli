"""
TODO:
    - look into https://github.com/click-contrib/click-help-colors
"""

import datetime
from distutils.util import strtobool
import sys
from typing import Iterable, List, Optional, Tuple
import urllib.parse
import uuid

import click

from timer_cli.job import (
    job_delete,
    job_list,
    job_status,
    job_submit,
    show_job,
    show_job_list,
)
from timer_cli.output import show_response


# List of datetime formats accepted as input. (`%z` means timezone.)
DATETIME_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S%z",
]


def _un_parse_opt(opt: str):
    return "--" + opt.replace("_", "-")


def show_usage(cmd: click.Command):
    """
    Show the relevant usage and exit.

    The actual usage message is also specific to incomplete commands, thanks to using
    the click context.
    """
    ctx = click.get_current_context()
    ctx.max_content_width = 100
    formatter = ctx.make_formatter()
    cmd.format_help_text(ctx, formatter)
    cmd.format_options(ctx, formatter)
    cmd.format_epilog(ctx, formatter)
    click.echo(formatter.getvalue().rstrip("\n"))
    ctx.exit()
    sys.exit(2)


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
        self.mutually_exclusive = kwargs.pop('mutually_exclusive')
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
            raise click.UsageError(
                f"Illegal usage: one of `{self.name}` or `{self.mutually_exclusive}`"
                " is required"
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
            full_options_names = ", ".join([
                "/".join(opt.opts)
                for opt in ctx.command.params
                if opt.name in self.jointly_exhaustive or opt == self
            ])
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


@cli.group()
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
        "Start time for the job (defaults to current time)"
    ),
)
@click.option(
    "--interval",
    required=True,
    type=int,
    help="Interval in seconds at which the job should run",
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
    interval: int,
    scope: str,
    action_url: urllib.parse.ParseResult,
    action_body: Optional[str],
    action_file: Optional[click.File],
    verbose: bool,
):
    """
    Submit a job.
    """
    response = job_submit(
        name,
        start,
        interval,
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
    """
    response = job_list(show_deleted=show_deleted)
    show_job_list(response, verbose=verbose)


@job.command(cls=Command)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show full JSON output",
)
@click.argument("job_id", type=uuid.UUID)
def status(job_id: uuid.UUID, verbose: bool):
    """
    Return the status of the job with the given ID.
    """
    show_job(job_status(job_id), verbose=verbose)


@job.command(cls=Command)
@click.argument("job_id", type=uuid.UUID)
def delete(job_id: uuid.UUID):
    show_response(job_delete(job_id))


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
        "Start time for the job (defaults to current time)"
    ),
)
@click.option(
    "--interval",
    required=True,
    type=int,
    help="Interval in seconds at which the job should run",
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
    interval: int,
    source_endpoint: str,
    dest_endpoint: str,
    label: Optional[str],
    sync_level: Optional[int],
    item: Optional[List[Tuple[str, str, Optional[str]]]],
    items_file: Optional[str],
    verbose: bool,
):
    """
    Submit specifically a transfer job. The options for this command are tailored to
    the transfer action.
    """
    action_url = urllib.parse.urlparse(
        "https://actions.automate.globus.org/transfer/transfer/run"
    )
    scope = "https://auth.globus.org/scopes/actions.globus.org/transfer/transfer"
    if item:
        transfer_items = [
            {"source_path": i[0], "destination_path": i[1], "recursive": i[2]}
            for i in item
        ]
    else:
        with open(items_file, "r") as f:
            lines = f.readlines()
        items = [line.split() for line in lines]
        transfer_items = [
            {
                "source_path": i[0],
                "destination_path": i[1],
                "recursive": bool(strtobool(i[2]))
            }
            for i in items
        ]
    action_body = {
        "source_endpoint_id": source_endpoint,
        "destination_endpoint_id": dest_endpoint,
        "transfer_items": transfer_items,
    }
    if label:
        action_body["label"] = label
    if sync_level:
        action_body["sync_level"] = sync_level
    callback_body = {"body": action_body}
    response = job_submit(
        name,
        start,
        interval,
        scope,
        action_url,
        action_body=None,
        action_file=None,
        callback_body=callback_body,
    )
    show_job(response, verbose=verbose)


def main():
    cli()


if __name__ == '__main__':
    cli()
