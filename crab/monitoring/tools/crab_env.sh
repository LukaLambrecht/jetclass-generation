#!/bin/bash

# Run a crab subcommand, with the environment it needs
#
#   tools/crab_env.sh status   <project dir> [more crab args]
#   tools/crab_env.sh resubmit <project dir> [more crab args]
#   tools/crab_env.sh kill     <project dir> [more crab args]
#
# Why a shell script at all: crab needs a CMSSW environment, and that is set up by
# sourcing shell scripts from cvmfs, which cannot be done from inside an already
# running python process.
#
# Overridable, so a caller is never stuck with the defaults below:
#   CRAB_SCRAM_ARCH      scram architecture               (default el9_amd64_gcc12)
#   CRAB_CMSSW_RELEASE   release name or glob on cvmfs    (default CMSSW_14_0_*)
#   CRAB_CMSSW_DIR       path to an existing CMSSW area, used instead of cvmfs
#
# NOTE the `set +u` below, and do not remove it: crab.sh and cmsset_default.sh read
# unbound variables, and under `set -u` an unbound variable in a SOURCED script exits
# the shell outright rather than returning non-zero - which fails silently when the
# output is being captured.
set +u

source /cvmfs/cms.cern.ch/cmsset_default.sh >/dev/null 2>&1

ARCH=${CRAB_SCRAM_ARCH:-el9_amd64_gcc12}
export SCRAM_ARCH=$ARCH

if [ -n "${CRAB_CMSSW_DIR:-}" ] && [ -d "${CRAB_CMSSW_DIR}/src" ]; then
    RELEASE=$CRAB_CMSSW_DIR
else
    RELEASE=$(ls -d /cvmfs/cms.cern.ch/"$ARCH"/cms/cmssw/${CRAB_CMSSW_RELEASE:-CMSSW_14_0_*} \
              2>/dev/null | tail -1)
fi
if [ -z "$RELEASE" ]; then
    echo "ERROR: no CMSSW release found for arch $ARCH" >&2
    echo "       set CRAB_CMSSW_RELEASE, CRAB_SCRAM_ARCH or CRAB_CMSSW_DIR" >&2
    exit 1
fi

# `scram runtime` has to be run from inside the release area, hence the pushd; the
# environment it prints is what makes the crab client importable.
pushd "$RELEASE" >/dev/null || { echo "ERROR: cannot enter $RELEASE" >&2; exit 1; }
eval "$(scram runtime -sh)" || { echo "ERROR: scram runtime failed in $RELEASE" >&2; exit 1; }
popd >/dev/null

source /cvmfs/cms.cern.ch/crab3/crab.sh >/dev/null 2>&1
command -v crab >/dev/null || { echo "ERROR: crab client not available" >&2; exit 1; }

exec crab "$@"
