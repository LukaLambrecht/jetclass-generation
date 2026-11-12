#!/bin/bash
#
# Wrapper around monitor_crab_jobs.py: fills in the two paths and the proxy, then
# forwards everything else straight through.
#
# Run it periodically, e.g. from acrontab:
#   0 * * * * lxplus.cern.ch cd <path to here>; bash monitor_crab_jobs.sh >> monitor.log 2>&1
#
# The settings below can be overridden from the environment:
#   SEARCHDIR=/some/other/tree ./monitor_crab_jobs.sh
#   WEBDIR=/eos/user/x/xyz/www/crab ./monitor_crab_jobs.sh
#   X509_USER_PROXY=$HOME/private/x509up_monitor ./monitor_crab_jobs.sh
#
# Extra arguments are passed on to monitor_crab_jobs.py.
# Examples:
#   ./monitor_crab_jobs.sh -i /tree/one /tree/two
#   ./monitor_crab_jobs.sh -t /path/to/crab_myrequest
#   ./monitor_crab_jobs.sh -r --resubmit_args='--siteblacklist=T2_IT_Pisa'
#   ./monitor_crab_jobs.sh --no-mirror-logs
#   ./monitor_crab_jobs.sh --kill --kill-yes
# Run it with --help to see every option.
#
# NOTE: arguments passed to monitor_crab_jobs.py take precedence over
# the ones set by this wrapper script!
# Example:
#   SEARCHDIR=/path/to/A ./monitor_crab_jobs.sh -i /path/to/B
# This will use /path/to/B and not /path/to/A.
# It is generally preferred to pass arguments on the command line
# rather than using environment variables.

# Initializations
set -u
THISDIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# Where to look for CRAB tasks; searched recursively for crab project directories.
SEARCHDIR=${SEARCHDIR:-$THISDIR/../production}

# Where the pages go; the main status page is "index.html" in the provided directory,
# with the failure pages and the mirrored job logs beside it.
WEBDIR=${WEBDIR:-/eos/user/${USER:0:1}/$USER/www/monitor_crab_jobs}

# Where to look for the proxy.
# NOTE: A cron/acron run has no interactive session, so point it at a
# long-lived copy rather than relying on /tmp/x509up_u<uid> being there.
X509_USER_PROXY=${X509_USER_PROXY:-}

# Print arguments
echo "Running monitor_crab_jobs.sh"
date
echo "Settings:"
echo "THISDIR=$THISDIR"
echo "SEARCHDIR=$SEARCHDIR"
echo "WEBDIR=$WEBDIR"
echo "X509_USER_PROXY=$X509_USER_PROXY"

# Set up the CVMFS environment.
#
# NOTE: the `set +u` is required here. cmsset_default.sh sources the site-local
# /cvmfs/cms.cern.ch/SITECONF/local/JobConfig/cmsset_local.sh, which reads CVS_RSH
# without a default. Under `set -u` an unbound variable in a SOURCED script exits the
# shell outright - and with output redirected the message is lost, so the log simply
# stops after the last echo. An interactive lxplus login sets CVS_RSH, which is why
# this only ever failed from acron.
set +u
source /cvmfs/cms.cern.ch/cmsset_default.sh >/dev/null 2>&1
set -u

# Set up the proxy argument.
PROXY_ARG=""
if [ -n "${X509_USER_PROXY:-}" ] && [ -f "${X509_USER_PROXY}" ]; then
    PROXY_ARG="--proxy ${X509_USER_PROXY}"
fi

# Call monitor_crab_jobs.py.
python3 "$THISDIR/monitor_crab_jobs.py" -i "$SEARCHDIR" -d "$WEBDIR" $PROXY_ARG "$@"
