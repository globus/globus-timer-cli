# Globus Automate Timer CLI

This is an alpha-version CLI for use with the (also in alpha) timer API, to use
primarily for scheduling recurring transfer tasks through Globus Automate.

As the CLI and service are still in alpha, please feel free to email the current
maintainer (rudyard at globus dot org) with feedback or to resolve issues.

## What is this Service/CLI for?

The timer service can be used to schedule recurring transfer tasks. For example,
let’s say we want to have a transfer automatically run every night to back up
data. We submit a job to the timer API starting tonight, and with an interval of
1 day at which it will be re-run. In that request we provide the timer service
the same input we would give to the transfer action provider; that part of the
request contains the information for what endpoints we transfer to and from as
well as other options relevant to the transfer.

## Installation

This CLI requires Python version 3.5 or higher. See the [Globus CLI
docs](https://docs.globus.org/cli/installation/prereqs/) for help on how to set
up Python.

Once the appropriate version of Python is ready, install with `pip install
globus-timer-cli`.

## Transfer Quickstart

To avoid confusion, please read the entirety of this section before using the
transfer subcommand.

To schedule transfers on your behalf, this CLI requires authentication through
Globus Auth. The CLI should initially prompt you with a Globus Auth page to
consent to this usage. Authentication information is thereafter cached in the
file `~/.config/globus/tokens.json` (so the authentication process is only
needed on the first use); keep this file secret.

```
globus-timer job transfer \
    --name example-job
    --interval 28800
    --start '2020-01-01T12:34:56'
    --source-endpoint ddb59aef-6d04-11e5-ba46-22000b92c6ec \
    --dest-endpoint ddb59af0-6d04-11e5-ba46-22000b92c6ec \
    --item ~/file1.txt ~/new_file1.txt false \
    --item ~/file2.txt ~/new_file2.txt false
```
Specify any number of `--item`, which will be transferred from the source
endpoint to the destination endpoint at the interval specified, beginning at the
start time. The start time is inferred to be in the local timezone if an offset
is not specified. See `globus-timer job transfer --help` for additional details.
Instead of providing one or more `--item` options, you may instead provide
`--items-file`, which should contain space-separated values like each line is an
`--item`. For example, the file contents should look like this:
```
~/file1.txt ~/new_file1.txt false
~/file2.txt ~/new_file2.txt false
```

After submitting the transfer job, the CLI should return some results containing
a UUID `job_id`, which tracks this job in the timer service. To check on the
status of your jobs, use:
```
globus-timer job status JOB_ID
```
This command defaults to a summarized version of the job's information, which
does not include the full details for the corresponding task in Transfer. To
check those, use `-v/--verbose`:
```
globus-timer job status --verbose JOB_ID
```
Commands return date-times in ISO format, in UTC time, so probably a timezone
other than your own. No need to worry: the actual start time is still equal to
your submission's start time, etc.

A final important note: `Last Result` in the non-verbose output extends only as
far as the Automate system: `SUCCESS` indicates you have successfully submitted
your job to the timer service, which in turn successfully sent the task to the
Transfer Action Provider. It's possible that the Transfer service will
subsequently encounter some error running your transfer. Check the `--verbose`
output, which includes the actual response from Transfer, to be certain that
Transfer has run your job successfully.

## Basic Usage

[Note that functionality outside of transfer is currently much less
user-friendly and requires obtaining the specific scope(s) required to perform
your task to submit to the timer service. If all you need is transfer, use only
the `transfer` subcommand. Here be dragons.]

While part of the CLI is tailored to submitting transfer tasks, the interface
provides for scheduling generic actions in the Globus Automate API. To
summarize, the CLI can be used for the following tasks:
- Schedule a new recurring job: `globus-timer job submit ...`
- Check the list of previously-submitted jobs: `globus-timer job list`
- Check on the status of a particular job: `globus-timer job status JOB_ID`
- Show help for any of the above commands with `globus-timer job submit --help`
  etc.

As an example, a complete command would look something like this (excluding:

```
globus-timer job submit \
    --name test-tutorial-job \
    --interval 600 \
    --action-url https://actions.automate.globus.org/transfer/transfer/run \
    --action-body '{"body": {"source_endpoint_id": "ddb59aef-6d04-11e5-ba46-22000b92c6ec", "destination_endpoint_id": "ddb59af0-6d04-11e5-ba46-22000b92c6ec", "transfer_items": [{"source_path": "/~/file1.txt", "destination_path": "/~/new_file1.txt"}]}}'
```

Each command should be reasonably informative as to what arguments are required,
and what type of input is expected for those arguments. However, do note that
the `action-body` depends on the schema expected for that action provider, which
isn't known by the CLI. You can use the [Globus Automate
client](https://pypi.org/project/globus-automate-client/) to introspect the
input schema for an action provider, which is what the CLI needs for the
`--action-body` parameter. As for the other options, a quick breakdown:

- `--name` is just for the user to track their own submissions, and does not
  need to be unique
- `--interval`, for the job to re-run at, is in units of seconds
- `--start` is optional, defaulting to the current time, and allowed formats are
  listed in `globus-timer job submit --help`
- Instead of `--action-body` you can also give `--action-file` which should be a
  relative filepath to a file containing the same action body as JSON

## How Does it Work?

Internally, the service is using an algorithm similar to the unix utility cron.
The service will operate under the following guarantees:
- A job will not run more frequently than the specified interval.
- The time that a job starts may skew slightly depending on load (likely on the
  order of fractions of a second to individual seconds), but does not skew
  further over time. For example, suppose that your job is meant to run every 10
  seconds, but the scheduler is under unusually heavy load each time, and your
  job runs 1 second later than scheduled. It would not be possible for the job
  to run at 11, 22, 33, … rather it runs at 11, 21, 31, …
- Jobs are "soft-deleted," meaning they are removed from the scheduler but not
  the database, so the outputs of previous runs are still available. The results
  of the previous 10 runs are exposed in the API wherever the job is returned.

