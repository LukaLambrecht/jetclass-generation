#!/bin/bash
#
# Wrapper around monitor_crab_jobs.py for THIS repo's layout.
#
# Run it periodically, e.g. from acrontab:
#   0 */4 * * * lxplus.cern.ch cd <path to here>; bash monitor_crab_jobs.sh >> monitor.log 2>&1
#
# The tool walks <simpackdir>/**/crab_logs/* to find tasks, and for each one shells out
# to crab_command.sh inside that simpack - which build_simpack.py ships. Pass -r to
# resubmit failed jobs as it goes.
set -u

THISDIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SIMPACKS=${SIMPACKS:-$THISDIR/../production}
DEST=${DEST:-/eos/user/${USER:0:1}/$USER/jetclass/monitor_crab_jobs/index.html}

echo "Running monitor_crab_jobs.sh"
date

source /cvmfs/cms.cern.ch/cmsset_default.sh >/dev/null 2>&1

# crab needs a proxy. A cron/acron run has no interactive session, so point it at a
# long-lived copy with --proxy rather than relying on /tmp/x509up_u<uid> being there.
PROXY_ARG=""
if [ -n "${X509_USER_PROXY:-}" ] && [ -f "${X509_USER_PROXY}" ]; then
    PROXY_ARG="--proxy ${X509_USER_PROXY}"
fi

python3 "$THISDIR/monitor_crab_jobs.py" -i "$SIMPACKS" -d "$DEST" $PROXY_ARG "$@"
