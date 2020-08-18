# Globus Automate Timer CLI

This is an alpha-version CLI for use with the (also in alpha) timer API, to use
primarily for scheduling recurring transfer tasks through Globus Automate.

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

## Basic Usage

To summarize, the CLI can be used for the following tasks:
- Schedule a new recurring job: `globus-timer job submit ...`
- Check the list of previously-submitted jobs: `globus-timer job list`
- Check on the status of a particular job: `globus-timer job status JOB_ID`
- Show help for any of the above commands with `globus-timer job submit --help`
  etc.

As an example, a complete command would look something like this:

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
- `--start-time` is optional, defaulting to the current time, and allowed
  formats are listed in `globus-timer job submit --help`
- Instead of `--action-body` you can also give `--action-file` which should be a
  relative filepath to a file containing the same action body as JSON

To schedule transfers on your behalf, this CLI requires authentication through
Globus Auth. The CLI should initially prompt you with a Globus Auth page to
consent to this usage. Authentication information is cached in the file
`~/.config/globus/tokens.json` (so the authentication process is only needed on
the first use), which should be kept secret.

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

