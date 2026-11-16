#!/bin/bash
#
# Run any crab subcommand against this simpack's task, from a bare shell.
#
#   ./crab_command.sh status  crab_logs/crab_<name>
#   ./crab_command.sh resubmit crab_logs/crab_<name>
#   ./crab_command.sh kill    crab_logs/crab_<name>
#
# Copied into every simpack by build_simpack.py, as the easiest way to drive crab
# by hand against that task without setting up an environment first.
#
# NOTE the `set +u`, and do not remove it: crab.sh reads unbound variables, and
# under `set -u` an unbound variable in a SOURCED script exits the shell outright
# rather than returning non-zero, which fails silently.
set +u
source /cvmfs/cms.cern.ch/cmsset_default.sh >/dev/null 2>&1

# Prefer the CMSSW area crab_submit.sh made in this simpack, else a release on
# cvmfs. Either works: crab needs only some CMSSW environment, not the release the
# jobs themselves run.
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
