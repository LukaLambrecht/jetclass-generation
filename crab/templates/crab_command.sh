#!/bin/bash
#
# Run any crab subcommand against this simpack's task, from a bare shell.
#
#   ./crab_command.sh status  crab_logs/crab_<name>
#   ./crab_command.sh resubmit crab_logs/crab_<name>
#   ./crab_command.sh kill    crab_logs/crab_<name>
#
# This exists mainly for crab/monitoring/, which shells out to exactly this script in
# each simpack rather than calling crab itself - the convention of the upstream
# private-sample-production repo this workflow is based on. It is also the easiest way
# to drive crab by hand without setting up an environment first.
#
# NOTE the `set +u`: crab.sh reads unbound variables, and under `set -u` an unbound
# variable in a SOURCED script exits the shell outright rather than returning non-zero,
# which fails silently. The same trap bit crab/site-probe/collect_probe.sh.
set +u
source /cvmfs/cms.cern.ch/cmsset_default.sh >/dev/null 2>&1

# Prefer the CMSSW area crab_submit.sh already made in this simpack; otherwise fall back
# to a release on cvmfs. Either works - crab only needs *a* CMSSW environment, not the
# one the jobs run (that is CMSSW_10_6_30 inside the container, see run_job.sh).
if [ -d CMSSW_14_0_0/src ]; then
    export SCRAM_ARCH=el9_amd64_gcc12
    pushd CMSSW_14_0_0/src >/dev/null && eval "$(scram runtime -sh)" && popd >/dev/null
elif [ -z "${CMSSW_BASE:-}" ]; then
    export SCRAM_ARCH=el9_amd64_gcc12
    REL=$(ls -d /cvmfs/cms.cern.ch/el9_amd64_gcc12/cms/cmssw/CMSSW_14_0_* 2>/dev/null | tail -1)
    [ -n "$REL" ] && { pushd "$REL" >/dev/null && eval "$(scram runtime -sh)" && popd >/dev/null; }
fi

source /cvmfs/cms.cern.ch/crab3/crab.sh >/dev/null 2>&1
command -v crab >/dev/null || { echo "ERROR: crab client not available" >&2; exit 1; }

crab "$@"
