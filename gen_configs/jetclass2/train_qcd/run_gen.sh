#!/bin/bash -x

# Generate the events.hepmc for one batch.
#
# QCD variant: Pythia8 only, no MadGraph step.

NEVENT=$1

# cd into current genpack's dir
cd "$( dirname "${BASH_SOURCE[0]}" )"

# Draw this batch's parameters: one random line from py8_params.dat, whose
# fields are substituted for $1, $2, ... in the template below.
if [ -f py8_params.dat ]; then
    RANDOM_PARAMS=$(shuf -n 1 py8_params.dat)
    IFS=' ' read -ra PARAMS <<< $RANDOM_PARAMS
fi

# step1: compile py8 program
if [ ! -f py8_main ]; then
    echo "Comple py8 program"
    g++ py8_main.cc -o py8_main -I$MG5_PATH/HEPTools/pythia8//include -ldl -fPIC -lstdc++ -std=c++11 -O2 -DHEPMC2HACK -DGZIP -I$MG5_PATH/HEPTools/zlib/include -L$MG5_PATH/HEPTools/zlib/lib -Wl,-rpath,$MG5_PATH/HEPTools/zlib/lib -lz -L$MG5_PATH/HEPTools/pythia8//lib -Wl,-rpath,$MG5_PATH/HEPTools/pythia8//lib -lpythia8 -ldl -I$MG5_PATH/HEPTools/hepmc/include -L$MG5_PATH/HEPTools/hepmc/lib -Wl,-rpath,$MG5_PATH/HEPTools/hepmc/lib -lHepMC -DHEPMC2
fi

# step2: generate event

## write py8.dat
cp -f py8_templ.dat py8.dat
## substitute the drawn parameters for the $1, $2, ... placeholders
if [ -f py8.dat ]; then
    for i in `seq 1 ${#PARAMS[@]}`; do
        sed -i "s/\$${i}/${PARAMS[$((i-1))]}/g" py8.dat
    done
fi

sed -i "s/\$NEVENT/$NEVENT/g" py8.dat # initialize nevent
sed -i "s/\$SEED/$RANDOM/g" py8.dat # no effect here: the card uses pythia's own seeding

## generate hepmc events (events.hepmc)
./py8_main
