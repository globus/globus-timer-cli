# Globus Automate Timer CLI

This is an alpha-version CLI for use with the (also in alpha) Globus Timer API, to use
primarily for scheduling recurring Globus transfers through Globus Automate.

As the CLI and service are still in alpha, please feel free to email the current
maintainer (rudyard at globus dot org) with feedback or to resolve issues.

## What is this Service/CLI for?

The Globus Timer service can be used to schedule recurring transfer
tasks. For example, let’s say we want to have a transfer automatically
run every night to back up data. We submit a job to the Timer Service
starting tonight, and with an interval of 1 day at which it will be
re-run. In that request we provide the Timer service the same input we
would give to the [Globus Transfer Action Provider]();
that part of the request contains the information for what Globus endpoints
we transfer to and from as well as other options relevant to the
transfer.

## Installation

This CLI requires Python version 3.5 or higher. See the [Globus CLI
docs](https://docs.globus.org/cli/installation/prereqs/) for help on how to set
up Python.

Once the appropriate version of Python is ready, install with `pip
install globus-timer-cli`. This will create a new command line
utility, `globus-timer` which can be used for all interactions with
the service. Online documentation is always available using the
`--help` option on any command. So, `globus-timer --help` will provide
information about the options on the command while `globus-timer job
--help` will provide help text specific to working with jobs. When in
doubt, add `--help` to a command for guidance on next steps.

## Getting Started

To schedule transfers on your behalf, this CLI requires authentication
through Globus Auth. Upon first use, the CLI will prompt you to
authorize use via the Globus Auth system. Typically, this will occur
by opening a web browser which will request that you login to your
Globus identity and to consent to the service looking up your identity
and interacting with the Globus Transfer service on your behalf. Some
Globus endpoints require additional authentication for use, when this
is necessary, a second browser window may open asking for consent for
using the Globus Transfer service and additionally for the specific
endpoint(s) used with that job.

Authentication information is thereafter cached in the file
`~/.globus_timer_tokens.cfg` (so the authentication process is only
needed on the first use); keep this file secret.

After first use, you can determine what Globus Auth identity is being
used for interacting with the service by running the command:

```
globus-timer session whoami
```

This will show the identity which will be used for running the
Transfers. Be sure that this identity is authorized to work with the
endpoints involved in the Transfer.

To remove your stored identity information so that you may
re-authenticate, for example to invoke subsequent operations using a
different Globus Auth identity, use the command:

```
globus-timer session logout
```

This will simply delete the file `~/.globus_timer_tokens.cfg`
removing the identity information stored there so you will be required
to authenticate again on next use of the tool. Note that should you
wish to both logout, and revoke the Timer service's permission to run
further operations, you may use the command `globus-timer session
revoke` however this should be an extreme measure as it is much
preferred to properly delete jobs as described below.

## Scheduling Periodic Globus Transfer operations

NOTE: To avoid confusion, please read the entirety of this section before using the
`job transfer` sub-command.

The starting point for working with the Timer service is scheduling
transfers to run periodically. The form of this command is below:

```
globus-timer job transfer \
    --name example-job \
    --label "Timer Transfer Job" \
    --interval 28800 \
    --start '2020-01-01T12:34:56' \
    --source-endpoint ddb59aef-6d04-11e5-ba46-22000b92c6ec \
    --dest-endpoint ddb59af0-6d04-11e5-ba46-22000b92c6ec \
    --item ~/file1.txt ~/new_file1.txt false \
    --item ~/file2.txt ~/new_file2.txt false
```

The parameters to the `job transfer` command are as follows, and may
be seen also by invoking `globus-timer job transfer --help`:

* `name`: A friendly name you can use to identify the job. However,
  note that all operations on the job (see below) are based on the job
  identifier (`job_id`) which is returned in the output of this
  command.

* `label`: A label string which will be used on the Globus Transfer
  tasks which will be created to perform the periodic transfer
  operations. You may use this to help you identify the source of the
  Globus Transfer task when viewing them in the Globus web
  application. If no `label` string is provided, the Globus Transfer
  label will include the `name` of this Timer job.

* `interval`: The time, in seconds, between invocations of the Globus
  Transfer operation. The Transfer will be invoked after this number
  of fixed seconds. Note that this easily allows for intervals such as
  hourly (3600 seconds), daily (86400 seconds) or weekly (604800
  seconds), but it doesn't allow for day of month or provide the
  ability to compensate for other time related changes like daylight
  savings time changes. This is presently a limitation of the Timer
  service. In some cases, the actual time the operation is started in
  Globus Transfer may be a few seconds longer than the specified
  interval, but any delay will not impact scheduling of the next
  operation (i.e. the job will stay on schedule and not "drift" due to
  delays in any particular execution).

* `start`: A timestamp defining when the job should first be
  scheduled. Thus, the first invocation of the Globus Transfer
  operation will occur at the specified time and then again after each
  `interval` number of seconds. The time may contain just a year,
  month and date, or may also contain the exact time of day as shown
  in the example. Unless a timezone is specified, the local timezone
  will be used.

* `source-endpoint` and `dest-endpoint`: Are the ids for Globus
  Transfer endpoints for the source and destination of the transfer
  operation respectively. These values can be retrieved from the
  Globus web application.

* `item`: Specifies the exact locations on the source and destination
  endpoints to perform the transfer operation. `item` should be
  followed by three values: the path on the source endpoint from which
  to start the transfer, the path on the destination endpoint where
  the data should be placed, and a true or false value indicating
  whether the transfer should be performed in a recursive manner. When
  the value is true, if the source path names a folder, the folder and
  all of its contained files and other folders will be transferred. If
  the value is false, the first (source) path should refer to a
  specific file.

Note that, as shown in the example, a single job creation command can
contain multiple specifications of the `item` parameter. This means
that a single job can transfer from multiple paths between a single
source endpoint and a single destination endpoint.

As an alternative to specifying the `item` parameter one or more
times, the item values may be stored in a file in which each line has
the same format as the `item` parameter. The file may be specified
with the `items-file` option which is used *instead of* the `item`
parameter. An example of the file which would perform the same
operations as the example above would look like:

```
# This is my items file
~/file1.txt, ~/new_file1.txt, false
~/file2.txt, ~/new_file2.txt, false
```

If this file was named `transfer_items.csv` it would be specified with the parameter:

```
--items-file transfer_items.csv
```

Note that this is a CSV file. The individual parts of the item are separated with commas, and lines starting with a `#` are considered to be comments and are not processed as items for the transfer job.

## Monitoring and Controlling Submitted jobs

After submitting the transfer job, the CLI should return some results containing
a `job_id`, which identifies this job in the Timer service. To check the
status of your jobs, use:

```
globus-timer job status <job_id>
```

This command defaults to a summarized version of the job's information, which
does not include the full details for the corresponding task in Globus Transfer. To
check those, use `-v/--verbose`:

```
globus-timer job status --verbose JOB_ID
```

Commands return date-times in ISO format, in UTC time, so the timezone
most likely will not match the local time where you run the
command. No need to worry: the actual start time is still equal to
your submission's start time, etc.

The job description will also contain a value for `status` indicating
the condition of the job. The `status` may contain one of the
following values:

* `new`: The job has been received, but it has not yet been scheduled
  for its first execution (for example the start time has not yet been
  reached).

* `loaded`: The job has reached its execution mode and is executing
  repeatedly on the requested interval. This is the "steady-state" for
  a job when it is executing as expected.

* `updated`: If the job has recently been updated, it will be in this
  state until the job has transitioned to its new regular
  operation. This state should rarely be encountered as it is a
  transient state immediately after a job update.

* `deleted`: Indicates that the job has been deleted. This would not
  normally be seen, but the `job status` command described above as
  well as other commands described below provide the option of
  retrieving jobs marked as deleted using a command line flag
  `--show-deleted`.

A final important note: `Last Result` in the non-verbose output extends only as
far as the Globus Automate system: `SUCCESS` indicates you have successfully submitted
your job to the Timer service, which in turn successfully sent the task to the
Globus Transfer Action Provider. It's possible that the Globus Transfer service will
subsequently encounter some error running your transfer. Check the `--verbose`
output, which includes the actual response from Transfer, to be certain that
Transfer has run your job successfully.

To see all of your jobs which are outstanding, use the command:

```
globus-timer job list
```

This is particularly helpful if you do not have the `job_id` for a
particular job available. It will show all of your jobs in the same
format as the `job status` command described above. Similarly, the
`--verbose/-v` and `--show-deleted` options are supported.

Finally, a job may be removed from operation using the command:

```
globus-timer job delete <job_id>
```

The job will be removed from operation and no further transfers will
be performed. The same information provided via `job status` will be
displayed, showing the final state of the job. As described above, the
`job status` command may still retrieve the job information by
providing the `--show-deleted` flag. This can be helpful to review the
final state of the job, such as the last transfer or error condition,
even if the output for the `job delete` command is lost.


[Globus Transfer Action Provider]: (https://globus-automate-client.readthedocs.io/en/latest/globus_action_providers.html#globus-transfer-transfer-data)
