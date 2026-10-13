#!/bin/bash
#
# Wrapper around monitor_crab_jobs.py.
#
# Run it periodically, e.g. from acrontab:
#   0 * * * * lxplus.cern.ch cd <path to here>; bash monitor_crab_jobs.sh >> monitor.log 2>&1
#
# The tool walks <simpackdir>/**/crab_logs/* to find tasks, and for each one shells out
# to crab_command.sh inside that simpack - which build_simpack.py ships. Pass -r to
# resubmit failed jobs as it goes.
#
# RESUBMITTING WITH EXTRA CRAB OPTIONS - USE `=`, NOT A SPACE:
#
#   ./monitor_crab_jobs.sh -r --resubmit_args='--siteblacklist=T2_IT_Pisa,T2_AT_Vienna'
#
# argparse refuses a value that begins with '-', so the space-separated form shown in
# the upstream repo's own help text
#   ./monitor_crab_jobs.sh -r --resubmit_args '--siteblacklist=...'     # BROKEN
# dies with "argument --resubmit_args: expected one argument" before anything runs.
# It is easy to miss: the wrapper has already printed its header by then, so the log
# looks like a normal start that simply stopped.
set -u

THISDIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SIMPACKS=${SIMPACKS:-$THISDIR/../production}
DEST=${DEST:-/eos/user/${USER:0:1}/$USER/www/monitor_crab_jobs/index.html}

echo "Running monitor_crab_jobs.sh"
date
echo "Settings:"
echo "THISDIR=$THISDIR"
echo "SIMPACKS=$SIMPACKS"
echo "DEST=$DEST"

# NOTE the `set +u`, and do not remove it. cmsset_default.sh sources the site-local
# /cvmfs/cms.cern.ch/SITECONF/local/JobConfig/cmsset_local.sh, which reads CVS_RSH
# without a default. Under `set -u` an unbound variable in a SOURCED script exits the
# shell outright - and with output redirected the message is lost, so the log simply
# stops after the last echo. An interactive lxplus login sets CVS_RSH, which is why
# this only ever failed from acron. Same trap as in site-probe/collect_probe.sh.
set +u
source /cvmfs/cms.cern.ch/cmsset_default.sh >/dev/null 2>&1
set -u

# crab needs a proxy. A cron/acron run has no interactive session, so point it at a
# long-lived copy with --proxy rather than relying on /tmp/x509up_u<uid> being there.
PROXY_ARG=""
if [ -n "${X509_USER_PROXY:-}" ] && [ -f "${X509_USER_PROXY}" ]; then
    PROXY_ARG="--proxy ${X509_USER_PROXY}"
fi

python3 "$THISDIR/monitor_crab_jobs.py" -i "$SIMPACKS" -d "$DEST" $PROXY_ARG "$@"
