Globus Automate Timer CLI
=========================

This is an alpha-version CLI for use with the (also in alpha) timer API, to use primarily for scheduling recurring transfer tasks through Globus Automate.

Basic Usage
-----------

Install with `pip install ? TODO ?` (what do we officially call this thing?).

To summarize, the CLI can be used for the following tasks:
- Schedule a new recurring job: `timer job submit ...`
- Check the list of previously-submitted jobs: `timer job list`
- Check on the status of a particular job: `timer job status JOB_ID`
- Show help for any of the above commands with `timer job submit --help` etc.

Each command should be reasonably informative as to what arguments are required, and what type of input is expected for those arguments.

To schedule transfers on your behalf, this CLI requires authentication through Globus Auth. The CLI should initially prompt you with a Globus Auth page to consent to this usage. Authentication information is cached in the file ``$HOME/.config/globus/tokens.json`` (so the authentication process is only needed on the first use), which should be kept secret.
