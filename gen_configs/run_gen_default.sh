#!/bin/bash -x

# a wrapper to generate hepmc file
# note: this can only generate events from a certain paramter choice

NEVENT=$1

# the MG process dir
MDIR=proc

# cd into current genpack's dir
cd "$( dirname "${BASH_SOURCE[0]}" )"

# sample one line from the paramter file if mg5_params.dat exists
if [ -f mg5_params.dat ]; then
    RANDOM_PARAMS=$(shuf -n 1 mg5_params.dat)
    IFS=' ' read -ra PARAMS <<< $RANDOM_PARAMS
fi

# step1: setup the MG dir for the first time
# MG5 looks up lhapdf-config by BARE NAME and it is on PATH nowhere, so without a user
# config generate_events dies with "lhapdf executable (lhapdf-config) is not found on
# your system" for any process whose run card asks for pdlabel=lhapdf. On a developer's
# lxplus account this is masked by an existing ~/.mg5/mg5_configuration.txt; on a bare
# worker node there is none. crab/templates/run_job.sh writes one for the CRAB route,
# which is why that route works - this covers every other way of invoking the chain
# (run.sh directly, run_condor*.py, a fresh checkout).
#
# Only written when absent, so a user's own configuration is never overwritten.
if [ ! -f "$HOME/.mg5/mg5_configuration.txt" ]; then
    LHA=$MG5_PATH/HEPTools/lhapdf6_py3/bin/lhapdf-config
    if [ -x "$LHA" ]; then
        mkdir -p "$HOME/.mg5"
        { echo "lhapdf_py3 = $LHA"; echo "lhapdf = $LHA"; } > "$HOME/.mg5/mg5_configuration.txt"
        echo "MG5 lhapdf config written: $LHA"
    else
        echo "WARNING: no lhapdf-config at $LHA; MG5 will fail if the run card uses lhapdf" >&2
    fi
fi

if [ ! -d $MDIR ]; then
    echo "Setup MG dir"
    $MG5_PATH/bin/mg5_aMC mg5_step1.dat
fi

# step2: generate event

## write mg5_step2.dat
cp -f mg5_step2_templ.dat mg5_step2.dat
## if mg5_params.dat exists, replace $1, $2, ... by the customized params
if [ -f mg5_params.dat ]; then
    for i in `seq 1 ${#PARAMS[@]}`; do
        sed -i "s/\$${i}/${PARAMS[$((i-1))]}/g" mg5_step2.dat
    done
fi

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
# Main:numberOfEvents=-1 is meant to auto-detect the event count from the LHEF,
# but newer Pythia8 releases reject -1 as out of range and silently fall back
# to their own default (1000), causing a hang when the LHEF has fewer events.
# Set it explicitly to the requested count instead.
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
