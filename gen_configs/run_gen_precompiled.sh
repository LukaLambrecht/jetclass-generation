#!/bin/bash -x

# Shared logic for generating events using a precompiled JetClass-I (v1)
# gridpack (from https://github.com/jet-universe/jetclass_generation) instead
# of compiling the process from scratch. This skips MG5's "output proc" +
# first compile step entirely, which is the dominant per-job cost for
# fixed-parameter processes (skipping it turned a ~30 minute from-scratch
# compile into a ~30 second reuse in local testing).
#
# Not meant to be run directly: invoked by each process's own
# gen_configs/jetclass1/<PROC>/precompiled/run_gen.sh, which first cds into
# its own directory (so relative paths below resolve against it) and sets
# GRIDPACK_NAME (matching the gridpack's name on the URL above) before
# calling this script - so this script operates on the caller's cwd.
#
# Caveat: this reuses precompiled Fortran/C++ binaries built years ago on a
# different machine. It worked in local testing on this cluster (shared
# libraries resolved, LHAPDF/couplings loaded correctly), but is not
# guaranteed portable to every condor worker node architecture/glibc.

NEVENT=$1

if [ -z "$GRIDPACK_NAME" ]; then
    echo "ERROR: GRIDPACK_NAME must be set before calling run_gen_precompiled.sh" >&2
    exit 1
fi

# the MG process dir
MDIR=proc

# persistent, shared cache of extracted+patched gridpacks: populated once
# (by whichever job needs it first), reused by every later job/process
GRIDPACK_CACHE=${GRIDPACK_CACHE:-/eos/user/l/llambrec/jetclass/gridpack_cache}
CACHED_PROC=$GRIDPACK_CACHE/$GRIDPACK_NAME/proc

# step1: populate the cache for this process, if not already there (shared
# with ../download_gridpack.py, which can do this ahead of time for many
# processes in parallel - see populate_gridpack_cache.sh for the logic)
GRIDPACK_CACHE=$GRIDPACK_CACHE MG5_PATH=$MG5_PATH $GENCFG_PATH/populate_gridpack_cache.sh $GRIDPACK_NAME

# step2: reuse the cached, precompiled process for this job
if [ ! -d $MDIR ]; then
    echo "Reusing precompiled gridpack for $GRIDPACK_NAME"
    cp -r $CACHED_PROC $MDIR
fi

# step3: generate event (same as run_gen_default.sh from here on)

## write mg5_step2.dat
cp -f mg5_step2_templ.dat mg5_step2.dat
sed -i "s/\$NEVENT/$NEVENT/g" mg5_step2.dat # initialize nevent
sed -i "s/\$SEED/$RANDOM/g" mg5_step2.dat # initialize seed, important!

# if mg5_step2_run_card_templ exists, copy it to the MG dir
if [ -f mg5_step2_run_card_templ.dat ]; then
    cp -f mg5_step2_run_card_templ.dat $MDIR/Cards/run_card.dat
fi

# if mg5_step2_madspin_templ exists, copy it to the MG dir so MadGraph
# runs MadSpin (forced decays, e.g. for TTBar/TTBarLep) as part of generate_events
if [ -f mg5_step2_madspin_templ.dat ]; then
    cp -f mg5_step2_madspin_templ.dat $MDIR/Cards/madspin_card.dat
fi

## generate MG events
rm -rf $MDIR/Events/*
cat mg5_step2.dat | $MDIR/bin/generate_events pilotrun
if [ -f $MDIR/Events/pilotrun_decayed_1/unweighted_events.lhe.gz ]; then
    echo "Run MG with MadSpin. Use the MadSpin generated LHE"
    mv -f $MDIR/Events/pilotrun_decayed_1/unweighted_events.lhe.gz .
else
    mv -f $MDIR/Events/pilotrun/unweighted_events.lhe.gz .
fi

# run pythia
rm -f events.hepmc
# see run_gen_default.sh for why this substitution is needed
sed -i "s/^Main:numberOfEvents.*/Main:numberOfEvents      = $NEVENT/" py8.dat
LD_LIBRARY_PATH=$MG5_PATH/HEPTools/lib:$LD_LIBRARY_PATH $MG5_PATH/HEPTools/MG5aMC_PY8_interface/MG5aMC_PY8_interface py8.dat
