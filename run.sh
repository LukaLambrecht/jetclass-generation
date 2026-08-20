#!/bin/bash -x

PROC=$1
NEVENT=$2
NEVENT_GEN=$3
JOBNUM=$4
# optional 5th arg: which Delphes card to use - onlyFatJet (default), lite, or full
DELPHES_CARD_NAME=${5:-onlyFatJet}

# Setup environment

# ============ basic configuration ============
MG5_PATH=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2
DELPHES_PATH=/eos/user/l/llambrec/jetclass/delphes
OUTPUT_PATH=/eos/user/l/llambrec/jetclass/output_test

## some env variables are required by the softwares
LHAPDFCONFIG=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/lhapdf6_py3/share/LHAPDF/lhapdf.conf
LHAPDF_DATA_PATH=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/lhapdf6_py3/share/LHAPDF
PYTHIA8DATA=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/pythia8/share/Pythia8/xmldoc

## fixed configuration
GENCFG_PATH=$(realpath gen_configs)
case "$DELPHES_CARD_NAME" in
    onlyFatJet) DELPHES_CARD_FILE=delphes_card_CMS_JetClassII_onlyFatJet.tcl ;;
    lite)       DELPHES_CARD_FILE=delphes_card_CMS_JetClassII_lite.tcl ;;
    full)       DELPHES_CARD_FILE=delphes_card_CMS_JetClassII.tcl ;;
    *)
        echo "Unknown Delphes card option '$DELPHES_CARD_NAME'. Expected one of: onlyFatJet, lite, full." >&2
        exit 1
        ;;
esac
DELPHES_CARD_PATH=$(realpath delphes_cards)/$DELPHES_CARD_FILE
ANALYZER_PATH=$(realpath delphes_analyzers)
OUTPUT_PATH=$(realpath $OUTPUT_PATH)

# =============================================

# Create workdir
RANDSTR=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 10; echo)
WORKDIR=$(realpath $OUTPUT_PATH)/workdir_$(date +%y%m%d-%H%M%S)_${RANDSTR}_$(echo "$PROC" | sed 's/\//_/g')_$JOBNUM
mkdir -p $WORKDIR

cd $WORKDIR

generate_delphes(){
    # all GEN production logic inside the gen_configs folder
    # generate GEN events
    rm -f events.hepmc
    MG5_PATH=$MG5_PATH ./run_gen.sh $NEVENT_GEN

    # run delphes
    ln -s $DELPHES_PATH/MinBias_100k.pileup .
    rm -f events_delphes.root
    $DELPHES_PATH/DelphesHepMC2 $DELPHES_CARD_PATH events_delphes.root events.hepmc
    return $?
}

# generate delphes, in a batch of NEVENT_GEN
nbatch=$((NEVENT / NEVENT_GEN))

for ((i=0; i<nbatch; i++)); do

    echo "Batch: $i"

    # copy genpack if not exist
    cd $WORKDIR
    if [ ! -d "proc_base" ]; then
        mkdir proc_base
        cp -r $GENCFG_PATH/$PROC/* proc_base/
        # if genpack does not have a run_gen.sh, use the default
        if [ ! -f "proc_base/run_gen.sh" ]; then
            cp $GENCFG_PATH/run_gen_default.sh proc_base/run_gen.sh
        fi
    fi
    cd $WORKDIR/proc_base

    generate_delphes

    # if return code is 0
    if [ $? -eq 0 ]; then
        # successful
        mv events_delphes.root $WORKDIR/events_delphes_$i.root
    fi
    cd $WORKDIR

    # intermediate file merging for every 100 batches
    if [ $(((i+1) % 100)) -eq 0 ]; then
        hadd -f $WORKDIR/merged_events_delphes_$i.root $WORKDIR/events_delphes_*.root
        if [ $? -eq 0 ]; then
            rm -f $WORKDIR/events_delphes_*.root
        fi
    fi

done

# combine all root
if [ $nbatch -eq 1 ]; then
    mv $WORKDIR/events_delphes_0.root events_delphes.root
else
    hadd -f events_delphes.root $WORKDIR/*.root
fi
mkdir -p $OUTPUT_PATH/$PROC

# transfer the file
mv -f events_delphes.root $OUTPUT_PATH/$PROC/events_delphes_$JOBNUM.root

# produce ntuples from the Delphes output
# run in an isolated per-job copy of delphes_analyzers so that ACLiC's compilation
# (triggered by the "++" in makeNtuples.C++) doesn't race with other concurrent jobs
# compiling into the same shared delphes_analyzers/ directory
NTUPLE_PATH=$OUTPUT_PATH/$PROC/ntuple_$JOBNUM.root
mkdir -p $WORKDIR/analyzer
cp $ANALYZER_PATH/EventData.h $ANALYZER_PATH/FatJetMatching.h $ANALYZER_PATH/ParticleID.h $ANALYZER_PATH/ParticleInfo.h $ANALYZER_PATH/makeNtuples.C $WORKDIR/analyzer/
(
    cd $WORKDIR/analyzer
    source /cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh
    export ROOT_INCLUDE_PATH=$ROOT_INCLUDE_PATH:/cvmfs/sft.cern.ch/lcg/releases/delphes/3.5.1pre09-9fe9c/x86_64-el9-gcc13-opt/include
    root -b -q "makeNtuples.C++(\"$OUTPUT_PATH/$PROC/events_delphes_$JOBNUM.root\", \"$NTUPLE_PATH\", \"JetPUPPIAK8\", \"GenJetAK8\", true)"
)

# remove workspace
rm -rf $WORKDIR

echo -e "\033[1mJob done. Generated $NEVENT events for $PROC.\033[0m"
echo -e "\033[1mDelphes file path: $OUTPUT_PATH/$PROC/events_delphes_$JOBNUM.root\033[0m"
echo -e "\033[1mNtuple file path: $NTUPLE_PATH\033[0m"
