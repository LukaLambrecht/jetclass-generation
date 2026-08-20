#!/bin/bash -x

PROC=$1
NEVENT=$2
NEVENT_GEN=$3
JOBNUM=$4
# optional 5th arg: comma-separated list of Delphes cards to run, e.g.
# "onlyFatJet" (default) or "onlyFatJet,onlyFatJetHLT". The same generated
# events are reused for every card - only the detector-level reconstruction
# step is repeated per card, producing its own events_delphes_*.root and
# ntuple_*.root under a per-card subdirectory.
DELPHES_CARD_NAMES=${5:-onlyFatJet}

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

card_file_for_name() {
    case "$1" in
        onlyFatJet)        echo "delphes_card_CMS_JetClassII_onlyFatJet.tcl" ;;
        onlyFatJetHLT)     echo "delphes_card_CMS_JetClassII_onlyFatJet_HLT.tcl" ;;
        onlyFatJetNoPU)    echo "delphes_card_CMS_JetClassII_onlyFatJet_noPU.tcl" ;;
        onlyFatJetHLTNoPU) echo "delphes_card_CMS_JetClassII_onlyFatJet_HLT_noPU.tcl" ;;
        lite)              echo "delphes_card_CMS_JetClassII_lite.tcl" ;;
        full)              echo "delphes_card_CMS_JetClassII.tcl" ;;
        *)
            echo "Unknown Delphes card option '$1'. Expected one of: onlyFatJet, onlyFatJetHLT, onlyFatJetNoPU, onlyFatJetHLTNoPU, lite, full." >&2
            exit 1
            ;;
    esac
}

IFS=',' read -ra CARD_NAMES <<< "$DELPHES_CARD_NAMES"
declare -a CARD_PATHS
for name in "${CARD_NAMES[@]}"; do
    CARD_PATHS+=("$(realpath delphes_cards)/$(card_file_for_name "$name")")
done

ANALYZER_PATH=$(realpath delphes_analyzers)
OUTPUT_PATH=$(realpath $OUTPUT_PATH)

# =============================================

# Create workdir
RANDSTR=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 10; echo)
WORKDIR=$(realpath $OUTPUT_PATH)/workdir_$(date +%y%m%d-%H%M%S)_${RANDSTR}_$(echo "$PROC" | sed 's/\//_/g')_$JOBNUM
mkdir -p $WORKDIR

cd $WORKDIR

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

    # generate GEN events once per batch - shared across all Delphes cards
    rm -f events.hepmc
    MG5_PATH=$MG5_PATH GENCFG_PATH=$GENCFG_PATH ./run_gen.sh $NEVENT_GEN

    # run each requested Delphes card on the same events.hepmc
    ln -sf $DELPHES_PATH/MinBias_100k.pileup .
    for idx in "${!CARD_NAMES[@]}"; do
        name=${CARD_NAMES[$idx]}
        path=${CARD_PATHS[$idx]}
        mkdir -p $WORKDIR/$name
        rm -f events_delphes.root
        $DELPHES_PATH/DelphesHepMC2 $path events_delphes.root events.hepmc
        if [ $? -eq 0 ]; then
            mv events_delphes.root $WORKDIR/$name/events_delphes_$i.root
        fi
    done
    cd $WORKDIR

    # intermediate file merging for every 100 batches
    if [ $(((i+1) % 100)) -eq 0 ]; then
        for name in "${CARD_NAMES[@]}"; do
            hadd -f $WORKDIR/$name/merged_events_delphes_$i.root $WORKDIR/$name/events_delphes_*.root
            if [ $? -eq 0 ]; then
                rm -f $WORKDIR/$name/events_delphes_*.root
            fi
        done
    fi

done

mkdir -p $OUTPUT_PATH/$PROC

# jetclass1/* processes use the original JetClass-I (v1) label scheme
# (Top_*/W_*/Z_*/H_*); everything else keeps the v2 scheme, unchanged.
case "$PROC" in
    jetclass1/*) USE_V1_LABELS=true ;;
    *)           USE_V1_LABELS=false ;;
esac

# produce ntuples from the Delphes output
# run in an isolated per-job copy of delphes_analyzers so that ACLiC's compilation
# (triggered by the "++" in makeNtuples.C++) doesn't race with other concurrent jobs
# compiling into the same shared delphes_analyzers/ directory
mkdir -p $WORKDIR/analyzer
cp $ANALYZER_PATH/EventData.h $ANALYZER_PATH/FatJetMatching.h $ANALYZER_PATH/ParticleID.h $ANALYZER_PATH/ParticleInfo.h $ANALYZER_PATH/makeNtuples.C $WORKDIR/analyzer/

for name in "${CARD_NAMES[@]}"; do
    # combine all root files for this card
    if [ $nbatch -eq 1 ]; then
        mv $WORKDIR/$name/events_delphes_0.root $WORKDIR/$name/events_delphes.root
    else
        hadd -f $WORKDIR/$name/events_delphes.root $WORKDIR/$name/*.root
    fi
    mkdir -p $OUTPUT_PATH/$PROC/$name

    # transfer the file
    mv -f $WORKDIR/$name/events_delphes.root $OUTPUT_PATH/$PROC/$name/events_delphes_$JOBNUM.root

    NTUPLE_PATH=$OUTPUT_PATH/$PROC/$name/ntuple_$JOBNUM.root
    (
        cd $WORKDIR/analyzer
        source /cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh
        export ROOT_INCLUDE_PATH=$ROOT_INCLUDE_PATH:/cvmfs/sft.cern.ch/lcg/releases/delphes/3.5.1pre09-9fe9c/x86_64-el9-gcc13-opt/include
        root -b -q "makeNtuples.C++(\"$OUTPUT_PATH/$PROC/$name/events_delphes_$JOBNUM.root\", \"$NTUPLE_PATH\", \"JetPUPPIAK8\", \"GenJetAK8\", true, false, $USE_V1_LABELS)"
    )
done

# remove workspace
rm -rf $WORKDIR

echo -e "\033[1mJob done. Generated $NEVENT events for $PROC.\033[0m"
for name in "${CARD_NAMES[@]}"; do
    echo -e "\033[1m[$name] Delphes file path: $OUTPUT_PATH/$PROC/$name/events_delphes_$JOBNUM.root\033[0m"
    echo -e "\033[1m[$name] Ntuple file path: $OUTPUT_PATH/$PROC/$name/ntuple_$JOBNUM.root\033[0m"
done
