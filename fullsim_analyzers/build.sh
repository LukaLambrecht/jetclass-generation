#!/bin/bash
# Build the FullSim ntuplizer as a standalone executable. Must be run inside a
# CMSSW environment (after `scram runtime -sh`), i.e. inside the container - see
# fullsim_configs/run_chain.sh, which calls this.
#
# Standalone rather than a ROOT macro: with ACLiC the compile itself works, but
# as soon as FWLite opens the file, cling auto-parses the CMSSW headers and
# ROOT 6.14 segfaults while reverting a transaction containing a lambda.
#
#   usage: build.sh [OUTPUT_BINARY] [SOURCE_DIR]
# SOURCE_DIR must hold makeNtuplesFullSim.cc, StandaloneTypes.h and the shared
# headers from delphes_analyzers/ (EventData.h, FatJetMatching.h, ParticleID.h,
# ParticleInfo.h) - run_chain.sh assembles exactly that.
set -e
OUT=${1:-makeNtuplesFullSim}
SRC=${2:-$(dirname "$(readlink -f "$0")")}

# When the environment is set up straight out of the release (no developer area,
# which is how the container is used here) scram leaves CMSSW_RELEASE_BASE EMPTY
# and points CMSSW_BASE at the release instead - so prefer whichever is set.
BASE=${CMSSW_RELEASE_BASE:-$CMSSW_BASE}
if [ -z "$BASE" ]; then
    echo "ERROR: no CMSSW environment (CMSSW_BASE/CMSSW_RELEASE_BASE unset) - run inside the container, after 'scram runtime -sh'" >&2
    exit 1
fi

# CMSSW_FWLITE_INCLUDE_PATH is scram's own list of the externals' include
# directories (boost, tbb, clhep, fastjet, ...) - using it avoids hardcoding
# either the external versions or which of them the CMSSW headers happen to need
INCLUDES="-I$SRC -I$BASE/src"
IFS=':' read -ra extra_inc <<< "${CMSSW_FWLITE_INCLUDE_PATH}"
for d in "${extra_inc[@]}"; do
    [ -n "$d" ] && INCLUDES="$INCLUDES -I$d"
done

# `scram tool info` only works from inside a scram area, which the build
# directory is not - so ask from the release directory instead
tool_var () { (cd "$BASE" && scram tool info "$1" 2>/dev/null) | sed -n "s/^$2=//p" | head -1; }
FASTJET_BASE=${FASTJET_BASE:-$(tool_var fastjet FASTJET_BASE)}
FASTJET_CONTRIB_BASE=${FASTJET_CONTRIB_BASE:-$(tool_var fastjet-contrib FASTJET_CONTRIB_BASE)}
for v in FASTJET_BASE FASTJET_CONTRIB_BASE; do
    [ -z "${!v}" ] && { echo "ERROR: could not determine $v from scram" >&2; exit 1; }
done
INCLUDES="$INCLUDES -I$FASTJET_BASE/include -I$FASTJET_CONTRIB_BASE/include"

LIBDIR=$BASE/lib/$SCRAM_ARCH
CMSLIBS="-L$LIBDIR -lFWCoreFWLite -lDataFormatsFWLite -lDataFormatsCommon -lDataFormatsCandidate
         -lDataFormatsJetReco -lDataFormatsVertexReco -lDataFormatsTrackReco
         -lDataFormatsHepMCCandidate -lDataFormatsParticleFlowCandidate -lDataFormatsMath
         -lFWCoreUtilities -lFWCoreParameterSet"
# Nsubjettiness and RecursiveTools (SoftDrop) are all inside the single
# "fragile" shared library of the fastjet-contrib external
FJLIBS="-L$FASTJET_BASE/lib -lfastjet -lfastjettools -L$FASTJET_CONTRIB_BASE/lib -lfastjetcontribfragile"

echo "Building $OUT from $SRC (CMSSW at $BASE)"
g++ -std=c++17 -O2 -Wall -Wno-unused-variable -Wno-unused-but-set-variable \
    $INCLUDES $(root-config --cflags) \
    "$SRC/makeNtuplesFullSim.cc" -o "$OUT" \
    $CMSLIBS $FJLIBS $(root-config --libs) -lGenVector -lPhysics \
    -Wl,-rpath,"$LIBDIR" -Wl,-rpath,"$FASTJET_BASE/lib" -Wl,-rpath,"$FASTJET_CONTRIB_BASE/lib"
echo "Built $OUT"
