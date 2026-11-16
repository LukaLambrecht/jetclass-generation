#!/bin/bash -x

# Generate the events.hepmc for one batch: MadGraph5 for the hard process, then
# Pythia8 for the shower.
#
# One random parameter point is drawn per invocation, so a retry gives a fresh
# draw.

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
# MG5 looks up lhapdf-config by bare name and it is on PATH nowhere, so without a
# user config generate_events dies for any process whose run card asks for
# pdlabel=lhapdf. An interactive account usually has one already; a bare worker
# node does not. Only written when absent, so a user's own config is kept.
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
# Main:numberOfEvents=-1 should auto-detect the count from the LHEF, but newer
# Pythia8 releases reject -1 and fall back to their own default of 1000, which
# hangs when the LHEF holds fewer events. State the count explicitly instead.
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
