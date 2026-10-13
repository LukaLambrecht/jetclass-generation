#!/bin/bash
# Submit this simpack to CRAB. Needs a valid proxy:  voms-proxy-init -voms cms -valid 192:00
set -e
source /cvmfs/cms.cern.ch/cmsset_default.sh
if [ -z "${CMSSW_BASE:-}" ]; then
    # CRAB needs *a* CMSSW environment; any recent release will do, it is not the one
    # the jobs run (that is CMSSW_10_6_30 inside the container, see run_job.sh)
    export SCRAM_ARCH=el9_amd64_gcc12
    [ -d CMSSW_14_0_0 ] || scram project CMSSW CMSSW_14_0_0 >/dev/null
    pushd CMSSW_14_0_0/src >/dev/null && eval "$(scram runtime -sh)" && popd >/dev/null
fi
source /cvmfs/cms.cern.ch/crab3/crab.sh
voms-proxy-info -exists -valid 0:10 || { echo "ERROR: no valid proxy - run: voms-proxy-init -voms cms -valid 192:00" >&2; exit 1; }
crab submit -c crab_config.py "$@"
