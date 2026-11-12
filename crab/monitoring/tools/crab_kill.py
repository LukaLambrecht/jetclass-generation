# Kill CRAB tasks
#
# Normal use is through the single entry point:
#     python3 monitor_crab_jobs.py -i <searchdir> --kill
#     python3 monitor_crab_jobs.py -t <requestdir> [<requestdir> ...] --kill
# Standalone, for debugging this step on its own:
#     python3 -m tools.crab_kill -i <searchdir>
#
# Which tasks to act on is worked out by tools/inputs.py, shared with the monitoring
# and the log mirroring, so all three select tasks the same way.
#
# Killing is irreversible: it throws away whatever the jobs have done so far and the
# work has to be resubmitted. So the default is to list what would be killed and ask
# once, and --yes has to be given explicitly to skip that - an unattended caller
# (acron, a wrapper script) must say so deliberately rather than by omission.

import argparse
import sys

from . import crabcmd
from . import inputs


def kill_tasks(tasks, proxy=None, confirm=True, dry_run=False):
    """Run 'crab kill' for each task. Returns the number killed.

    Input arguments:
    - tasks: inputs.Task objects (see tools/inputs.py).

    Never raises for a task that cannot be killed;
    it is reported and the rest are still attempted.
    """
    tasks = list(tasks)
    if not tasks:
        print('No CRAB tasks found; nothing to kill.')
        return 0

    print('Will kill the following CRAB task(s):')
    for t in tasks:
        print('  - {}'.format(t.path))

    if dry_run:
        print('(dry run: nothing was killed)')
        return 0

    if confirm:
        try:
            answer = input('Continue? (y/n) ')
        except EOFError:
            print('ERROR: no answer available (not a terminal).')
            return 0
        if answer.strip().lower() not in ('y', 'yes'):
            print('Aborted; nothing was killed.')
            return 0

    nkilled = 0
    for idx, t in enumerate(tasks, start=1):
        print('Killing task {} of {}: {}'.format(idx, len(tasks), t.path))
        rc = crabcmd.call(['kill', t.path], proxy=proxy)
        if rc == 0:
            nkilled += 1
        else:
            print('  crab kill returned {} for {}'.format(rc, t.path))

    print('Killed {} of {} task(s).'.format(nkilled, len(tasks)))
    return nkilled


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='python3 -m tools.crab_kill',
        description='Kill CRAB tasks found by scanning directories and/or named '
                    'individually.')
    ap.add_argument('-i', '--searchdir', default=[], nargs='+', metavar='DIR',
                    help='Directory/ies scanned recursively for CRAB project dirs')
    ap.add_argument('-t', '--requestdir', default=[], nargs='+', metavar='DIR',
                    help='CRAB project directory/ies (crab_<requestName>)')
    ap.add_argument('-p', '--proxy', default=None,
                    help='Path to a valid grid proxy (passed to crab as --proxy)')
    ap.add_argument('-y', '--yes', action='store_true',
                    help='Do not ask for confirmation (required when not on a terminal)')
    ap.add_argument('-n', '--dry-run', action='store_true',
                    help='List the tasks that would be killed and stop')
    args = ap.parse_args(argv)

    try:
        tasks = inputs.collect(args.searchdir, args.requestdir)
    except ValueError as e:
        ap.error(str(e))
        return 1

    kill_tasks(tasks, proxy=args.proxy, confirm=not args.yes, dry_run=args.dry_run)
    return 0


if __name__ == '__main__':
    sys.exit(main())
