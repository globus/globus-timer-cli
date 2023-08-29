Migrating to the Globus CLI
###########################

The features and functionality of the Timer CLI have been incorporated into the `Globus CLI`_,
which provides a robust, comprehensive suite of commands for interacting with Globus services.

For this reason, the Timer CLI is no longer being developed or maintained,
and users are encouraged to migrate scripts, cron jobs, and internal documentation
to use and reference the `Globus CLI`_.

There are some differences in how the Timer CLI and the `Globus CLI`_ operate,
what commands they support, and what arguments and options they accept.
This guide provides a comprehensive summary of the current differences at the time of writing.


Commands
========

..  csv-table:: Session commands
    :header: "Purpose", "Timer CLI command", "Globus CLI command"

    "Log in", "``globus-timer session login``", "``globus login``"
    "Show current user", "``globus-timer session whoami``", "``globus whoami``"
    "Revoke consents", "``globus-timer session revoke``", "``globus logout``"
    "Log out", "``globus-timer session logout``", "``globus logout``"


..  csv-table:: Timers commands
    :header: "Purpose", "Timer CLI command", "Globus CLI command"

    "List timers", "``globus-timer job list``", "``globus timer list``"
    "Create a new Transfer timer", "``globus-timer job transfer``", "``globus timer create transfer``"
    "Get the status of a timer", "``globus-timer job status``", "``globus timer show``"
    "Delete a timer", "``globus-timer job delete``", "``globus timer delete``"


..  note::

    To support development of the Timers service,
    the Timer CLI supported fine-grained control of timer creation
    via the ``globus-timer job submit`` command.
    At the time of writing, there is no equivalent for this command in the Globus CLI.


Options
=======

Although most Timer CLI options were ported to the Globus CLI without a name change,
some of the options' values were modified.
In most cases these differences align the Timers-specific options and values with
existing options and values used when submitting tasks to the Globus Transfer service.

The Timer CLI options listed below must be updated when migrating to the Globus CLI.

*   ``--source-endpoint <UUID>``

    The source endpoint is now a positional argument, not a CLI option.
    For example:

    ..  code-block:: bash

        # Timer CLI command
        globus-timer job create --source-endpoint <SRC_ID> --dest-endpoint <DST_ID>

        # Globus CLI command
        globus timer create transfer <SRC_ID> <DST_ID>

*   ``--dest-endpoint <UUID>``

    The destination endpoint is now a positional argument, not a CLI option.

    The example above shows how to specify the destination endpoint ID.

*   ``--sync-level <number>``

    The sync level was specified as a number in the Timer CLI
    (either ``0``, ``1``, ``2``, or ``3``).

    The Globus CLI supports the ``--sync-level`` option,
    but accepts a keyword value that indicates what conditional test to use
    when determining whether to transfer a file:

    ..  csv-table:: ``--sync-level`` values
        :header: "Globus CLI keyword", "Timer CLI number", "Meaning"

        "``exist``", "``0``", "Transfer files if they don't exist at the destination"
        "``size``", "``1``", "Transfer files if their sizes differ"
        "``mtime``", "``2``", "Transfer files if their modification times differ"
        "``checksum``", "``3``", "Transfer files if their checksums differ"

    Example:

    ..  code-block:: bash

        # Timer CLI command
        globus-timer job transfer [...] --sync-level 2

        # Globus CLI command
        globus timer create transfer [...] --sync-level mtime

*   ``--item <SRC_PATH> <DST_PATH> <RECURSIVE_FLAG>``

    The ``--item`` option is not supported in the Globus CLI.

    To specify a single source and destination path for the Transfer timer,
    add the paths directly to the source and destination endpoints
    using a colon (``:``) as a separator.

    ..  note::

        The Timer CLI allowed users to pass the ``--item`` option multiple times,
        but also supported a ``--items-file`` option for batching transfers
        within a single source and destination endpoint combination.
        See the next bullet point for a discussion of the equivalent in the Globus CLI.

    Where the Timer CLI used ``true`` to indicate that the source was a directory,
    the Globus CLI uses a ``--recursive`` option.
    Similarly, ``false`` in the Timer CLI should be replaced with ``--no-recursive``.
    If neither ``--recursive`` nor ``--no-recursive`` are passed to the Globus CLI,
    the Transfer service will auto-detect whether recursion is needed for the transfer.

    For example:

    ..  code-block:: bash
        :caption: Recursive transfer timer

        # Timer CLI command (recursive)
        globus-timer job transfer \
            --source-endpoint SRC_ID --dest-endpoint DST_ID \
            --item SRC_PATH DST_PATH true

        # Globus CLI command
        globus timer create transfer SRC_ID:SRC_PATH DST_ID:DST_PATH --recursive

    ..  code-block:: bash
        :caption: Non-recursive transfer timer

        # Timer CLI command (recursive)
        globus-timer job transfer \
            --source-endpoint SRC_ID --dest-endpoint DST_ID \
            --item SRC_PATH DST_PATH false

        # Globus CLI command
        globus timer create transfer SRC_ID:SRC_PATH DST_ID:DST_PATH --no-recursive

*   ``--items-file <FILE>``

    Like the Timer CLI,
    the Globus CLI is able to read source and destination paths from a file.
    It uses a ``--batch`` option instead of an ``--items-file`` option,
    and the structure of the "batch file" differs from the structure of an "items file".

    The Timer CLI's "items file" uses triplets of source and destination paths,
    together with a mandatory ``true`` or ``false`` to flag a recursive transfer.
    The Globus CLI's "batch file" requires only a source and destination path,
    but it optionally supports ``--recursive`` and ``--no-recursive`` options
    which can appear on each line of the file.

    For example:

    ..  code-block::

        # Timer CLI "items file" example
        /~/output.txt   /results/experiment/NMR-1234.txt    false
        /~/results/     /results/experiment/NMR-1234/       true


        # Globus CLI "batch file" example
        --no-recursive  /~/output.txt   /results/experiment/NMR-1234.txt
        --recursive     /~/results/     /results/experiment/NMR-1234/

    Note that the ``--recursive`` and ``--no-recursive`` options are not mandatory;
    if not specified, the Transfer service will auto-detect files and directories
    and will enable recursion if needed.


Example 1
=========

The Timer CLI command below will transfer a file every 8 hours.

Notably, the equivalent Globus CLI command does not specify a ``--no-recursive`` option,
which allows the Globus Transfer service to auto-detect whether recursion is needed.

..  list-table:: Example 1
    :header-rows: 1

    *   -   Timer CLI
        -   Globus CLI

    *   -   ..  code-block:: shell

                globus-timer job transfer \
                    --name example-job \
                    --label 'Timer Transfer Job' \
                    --interval 28800 \
                    --start '2023-09-01T12:34:56' \
                    --source-endpoint 0abeeda6-90f0-4d28-8394-987a45bbfc35 \
                    --dest-endpoint 58af0a9a-f01f-4590-81e9-8d420edf485a \
                    --item '/my/file.txt' '/~/copy.txt' false

        -   ..  code-block:: shell

                globus timer create transfer \
                    --name example-job \
                    --label 'Timer Transfer Job' \
                    --interval 8h \
                    --start '2023-09-01T12:34:56' \
                    '0abeeda6-90f0-4d28-8394-987a45bbfc35:/my/file.txt' \
                    '58af0a9a-f01f-4590-81e9-8d420edf485a:/~/copy.txt'


Example 2
=========

The Timer CLI command below will recursively transfer a directory every 24 hours.
It also ensures that file checksums match (rather than file sizes or modification times)
and mandates that checksums must be re-verified after the transfer completes.

As above, the equivalent Globus CLI command does not specify a ``--recursive`` option,
which allows the Globus Transfer service to auto-detect whether recursion is needed.


..  list-table:: Example 2
    :header-rows: 1

    *   -   Timer CLI
        -   Globus CLI

    *   -   ..  code-block:: shell

                globus-timer job transfer \
                    --name accounting \
                    --label 'Galileo Accounting Logs' \
                    --interval 86400 \
                    --stop-after-runs 30 \
                    --sync-level 3 \
                    --verify-checksum \
                    --encrypt-data \
                    --start 2023-09-01T12:00:00-0700 \
                    --source-endpoint dabc23fa-d59d-4cd0-afc7-8710ad200ee9 \
                    --dest-endpoint a62f9fa6-cfd2-4005-b45c-59630e2ddd98 \
                    --item /logs/galileo/accounting_new /galileo/accounting True

        -   ..  code-block:: shell

                globus timer create transfer \
                    --name accounting \
                    --label 'Galileo Accounting Logs' \
                    --interval 24h \
                    --stop-after-runs 30 \
                    --sync-level checksum \
                    --verify-checksum \
                    --encrypt-data \
                    --start 2023-09-01T12:00:00-0700 \
                    dabc23fa-d59d-4cd0-afc7-8710ad200ee9:/logs/galileo/accounting_new \
                    a62f9fa6-cfd2-4005-b45c-59630e2ddd98:/galileo/accounting


Additional information
======================

The information above summarizes key differences between the commands, options, and values
supported by the Timer CLI and the `Globus CLI`_.

The Globus CLI has extensive documentation for its suite of ``globus timer`` commands.
For up-to-date information about supported commands, options, and values,
please review the `Globus CLI Timers commands reference`_.



..  Links
..  -----
..
..  _Globus CLI: https://docs.globus.org/cli/
..  _Globus CLI Timers commands reference: https://docs.globus.org/cli/reference/#globus_timer_commands
