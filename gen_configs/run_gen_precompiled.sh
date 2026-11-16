#!/bin/bash -x

# Generate events from a precompiled JetClass-I gridpack, taken from
# https://github.com/jet-universe/jetclass_generation, instead of building the
# process from scratch. This skips MG5's "output proc" and first compile, which
# dominates the per-job cost for a fixed-parameter process: minutes become
# seconds.
#
# Not run directly. Each process' own
# gen_configs/jetclass1/<PROC>/precompiled/run_gen.sh cds into its directory and
# sets GRIDPACK_NAME before calling this, so the relative paths below resolve
# against the caller's cwd.
#
# Caveat: these are binaries built elsewhere, on another machine, so portability
# to an arbitrary worker node's architecture and glibc is not guaranteed.

NEVENT=$1

if [ -z "$GRIDPACK_NAME" ]; then
    echo "ERROR: GRIDPACK_NAME must be set before calling run_gen_precompiled.sh" >&2
    exit 1
fi

# the MG process dir
MDIR=proc

# MG5 needs ~/.mg5/mg5_configuration.txt to find lhapdf-config; see the identical
# block in run_gen_default.sh. Only written when absent.
if [ ! -f "$HOME/.mg5/mg5_configuration.txt" ]; then
    LHA=$MG5_PATH/HEPTools/lhapdf6_py3/bin/lhapdf-config
    if [ -x "$LHA" ]; then
        mkdir -p "$HOME/.mg5"
        { echo "lhapdf_py3 = $LHA"; echo "lhapdf = $LHA"; } > "$HOME/.mg5/mg5_configuration.txt"
        echo "MG5 lhapdf config written: $LHA"
    fi
fi


# Persistent shared cache of extracted and patched gridpacks, populated by
# whichever job needs an entry first and reused by every later one.
GRIDPACK_CACHE=${GRIDPACK_CACHE:-/eos/user/l/llambrec/jetclass/gridpack_cache}
CACHED_PROC=$GRIDPACK_CACHE/$GRIDPACK_NAME/proc

# step1: populate this process' cache entry if it is not there yet. The same
# script is used by ../download_gridpack.py to do this ahead of time.
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
# MG5 seed, drawn from /dev/urandom rather than bash's $RANDOM: that spans only
# 0-32767, so a few thousand batches would repeat seeds often, and it can return 0,
# which MG5 does not read as a literal seed. The 9e8 range matches the one used for
# the CMSSW seeds and makes a collision over a full round negligible.
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
# `PDF:pSet = LHAPDF6:...` makes Pythia dlopen libpythia8lhapdf6.so by bare name.
# That plugin lives in HEPTools/pythia8/lib, not HEPTools/lib, and would otherwise
# only be found through the absolute RPATH baked into the MG5 build - which does
# not exist on a node where the tarball was unpacked elsewhere. Name every
# directory holding the plugin and its dependencies, so the lookup never depends
# on RPATH. These are relative symlinks into bin/HEPTools, preserved by the
# tarball, so they resolve wherever MG5 is unpacked.
PY8_LD_PATH=$MG5_PATH/HEPTools/lib:$MG5_PATH/HEPTools/pythia8/lib:$MG5_PATH/HEPTools/lhapdf6_py3/lib
LD_LIBRARY_PATH=$PY8_LD_PATH:$LD_LIBRARY_PATH $MG5_PATH/HEPTools/MG5aMC_PY8_interface/MG5aMC_PY8_interface py8.dat
