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

# MG5 needs ~/.mg5/mg5_configuration.txt to find lhapdf-config; see the identical
# block in run_gen_default.sh for why. Only written when absent, so a user's own
# configuration is never overwritten.
if [ ! -f "$HOME/.mg5/mg5_configuration.txt" ]; then
    LHA=$MG5_PATH/HEPTools/lhapdf6_py3/bin/lhapdf-config
    if [ -x "$LHA" ]; then
        mkdir -p "$HOME/.mg5"
        { echo "lhapdf_py3 = $LHA"; echo "lhapdf = $LHA"; } > "$HOME/.mg5/mg5_configuration.txt"
        echo "MG5 lhapdf config written: $LHA"
    fi
fi


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
# MG5 seed. NOT bash's $RANDOM: that only spans 0-32767, so over the ~8000 MG5 runs
# of a 4000-job signal round some ~980 PAIRS of batches draw the same iseed (birthday
# problem). Today those pairs still differ, because `shuf` picks the (mass, pT_min)
# point from a 4900-line grid independently - but that is the parameter grid rescuing
# the seed, not the seed being sound, and it would stop being true for a process with
# a smaller grid or none. $RANDOM can also return 0, which MG5 does not read as a
# literal seed. Draw from /dev/urandom instead, over the same 9e8 range run_chain.sh
# uses for the CMSSW seeds, which makes a collision in a full round ~1e-4 likely.
MG5_SEED=$(( $(od -An -N4 -tu4 /dev/urandom) % 900000000 + 1 ))
sed -i "s/\$SEED/$MG5_SEED/g" mg5_step2.dat # initialize seed, important!
echo "MG5 seed: $MG5_SEED"

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
# Pythia reads `PDF:pSet = LHAPDF6:...` (set by the CP5 tune block) by dlopen'ing
# libpythia8lhapdf6.so *by bare name*. That plugin lives in HEPTools/pythia8/lib,
# not HEPTools/lib, and the only thing that used to find it was the absolute ELF
# RPATH baked into the MG5 build, which names this install's own EOS prefix. On a
# grid worker node the tarball unpacks elsewhere and that prefix does not exist, so
# the dlopen failed and Pythia aborted with "could not set up PDF for beam A".
# List every directory holding the plugin and its NEEDED libs explicitly, so the
# lookup never depends on RPATH. These are relative symlinks into bin/HEPTools and
# are preserved by the tarball, so they resolve wherever MG5 is unpacked.
PY8_LD_PATH=$MG5_PATH/HEPTools/lib:$MG5_PATH/HEPTools/pythia8/lib:$MG5_PATH/HEPTools/lhapdf6_py3/lib
LD_LIBRARY_PATH=$PY8_LD_PATH:$LD_LIBRARY_PATH $MG5_PATH/HEPTools/MG5aMC_PY8_interface/MG5aMC_PY8_interface py8.dat
