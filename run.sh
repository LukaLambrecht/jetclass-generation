#!/bin/bash -x

PROC=$1
NEVENT=$2
NEVENT_GEN=$3
JOBNUM=$4
# optional 5th arg: comma-separated list of Delphes cards to run, e.g.
# "onlyFatJet" (default) or "onlyFatJet,onlyFatJetHLT". The same generated
# events are reused for every card - only the detector-level reconstruction
# step is repeated per card, producing its own events_delphes_*.root and
# ntuple_*.root under a per-card subdirectory. An entry can also be an
# offline+HLT PAIR joined by "+" (e.g. "onlyFatJet+onlyFatJetHLT") - jet-
# matched into ONE combined ntuple instead of two independent ones, so an
# offline jet's own HLT reconstruction is directly recoverable - see
# delphes_analyzers/makeNtuplesPaired.C's own docstring.
DELPHES_CARD_NAMES=${5:-onlyFatJet}
# optional 6th arg: output directory, in place of the default below - lets a
# one-off/exploratory run (e.g. a timing scan) be pointed at a completely
# separate directory instead of mixing its output into the default one
OUTPUT_PATH=${6:-/eos/user/l/llambrec/jetclass/output_test}
# optional 7th arg: whether to also copy events_delphes_*.root to EOS
# (default false) - production runs only need the ntuples; the Delphes
# ROOT file is still produced and used locally to make the ntuple either
# way, it just isn't copied out unless this is "true"
KEEP_DELPHES_OUTPUT=${7:-false}

# Setup environment

# ============ basic configuration ============
# MG5_PATH respects a pre-set environment variable (falls back to the usual
# default otherwise) - lets a caller (e.g. run_condor.py's --extra-env) point
# a one-off run at a different MG5 install (e.g. for a toolchain-comparison
# test) without editing this file; DELPHES_PATH is intentionally NOT made
# overridable the same way - Delphes itself isn't part of what such tests
# vary, only the generation/showering toolchain upstream of it
MG5_PATH=${MG5_PATH:-/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2}
DELPHES_PATH=/eos/user/l/llambrec/jetclass/delphes

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
        JetClassI)         echo "delphes_card_CMS_JetClassI.tcl" ;;
        *)
            echo "Unknown Delphes card option '$1'. Expected one of: onlyFatJet, onlyFatJetHLT, onlyFatJetNoPU, onlyFatJetHLTNoPU, lite, full, JetClassI." >&2
            exit 1
            ;;
    esac
}

# Retry+verify a local-scratch -> EOS "mv" a few times before giving up.
# Needed because EOS's FUSE mount can spuriously fail `mkdir -p`/`mv` under
# heavy concurrent load - observed directly: "mkdir: cannot create
# directory '...': File exists" for a directory that DOES already exist
# (created moments earlier by another concurrent job sharing the same
# output subdirectory), immediately followed by the `mv` itself failing
# with "No such file or directory" even though the destination directory is
# genuinely there - a transient FUSE-side race/cache inconsistency, not a
# real missing-directory error (see testing/test-generation-time/README.md).
# Silently swallowing this (the previous behavior: no exit-code check on
# `mv`) meant run.sh exited 0 while quietly losing the job's actual output -
# found the hard way (nearly half of 100 concurrent jobs lost their output
# this way; see the README linked above). copy_to_eos() instead retries
# with backoff and, if it still can't verify the file landed, exits nonzero
# so the failure is loud and visible instead of silent.
copy_to_eos() {
    local src=$1 dst=$2 dstdir attempt
    dstdir=$(dirname "$dst")
    for attempt in 1 2 3 4 5; do
        mkdir -p "$dstdir"
        mv -f "$src" "$dst"
        if [ -f "$dst" ]; then
            return 0
        fi
        echo "WARNING: copy to EOS failed (attempt $attempt/5): $src -> $dst" >&2
        sleep $((attempt * 3))
    done
    echo "ERROR: giving up copying to EOS after 5 attempts: $src -> $dst" >&2
    return 1
}

# DELPHES_CARD_NAMES is comma-separated; each entry is either a single card
# name ("onlyFatJet") or an offline+HLT PAIR joined by "+"
# ("onlyFatJet+onlyFatJetHLT") - a pair is jet-matched into ONE combined
# ntuple (delphes_analyzers/makeNtuplesPaired.C) instead of two independent
# per-card ntuples with no correspondence between an offline jet and "its"
# HLT jet - see makeNtuplesPaired.C's own docstring for why that
# correspondence matters and how it's built. OUTPUT_UNITS keeps the raw
# entries (drives the ntuplizing loop below); CARD_NAMES is the flat,
# deduplicated list of every individual Delphes card actually needed (a
# name used standalone AND as half of a pair, e.g. testing both an
# independent "onlyFatJet" output and a paired one, only runs Delphes for
# it once) - unchanged from before for the per-batch Delphes-running loop
# and the per-card merge step, both still keyed on individual card names.
IFS=',' read -ra OUTPUT_UNITS <<< "$DELPHES_CARD_NAMES"
declare -a CARD_NAMES
declare -A SEEN_CARD
for unit in "${OUTPUT_UNITS[@]}"; do
    IFS='+' read -ra parts <<< "$unit"
    for name in "${parts[@]}"; do
        if [ -z "${SEEN_CARD[$name]}" ]; then
            CARD_NAMES+=("$name")
            SEEN_CARD[$name]=1
        fi
    done
done
declare -a CARD_PATHS
for name in "${CARD_NAMES[@]}"; do
    CARD_PATHS+=("$(realpath delphes_cards)/$(card_file_for_name "$name")")
done

ANALYZER_PATH=$(realpath delphes_analyzers)
OUTPUT_PATH=$(realpath $OUTPUT_PATH)

# =============================================

# Create workdir - on the worker node's own LOCAL scratch disk, not on EOS.
# All the heavy per-job I/O below (copying the gridpack, MG5/Pythia8 event
# generation, Delphes reconstruction, ntupling) happens here; only the two
# final output files per card are copied out to $OUTPUT_PATH (EOS) at the
# very end. This matters a lot once many jobs run concurrently: EOS charges
# real network-round-trip latency per file operation, and having dozens of
# jobs all doing that for every intermediate file (rather than just the 2
# final ones) is what caused severe slowdowns/timeouts when running 100
# jobs at once (see testing/test-generation-time/README.md).
# _CONDOR_SCRATCH_DIR is HTCondor's own per-job local scratch directory
# (auto-cleaned by condor on job exit); fall back to TMPDIR/tmp for a
# non-condor (e.g. interactive/local) invocation.
SCRATCH_BASE=${_CONDOR_SCRATCH_DIR:-${TMPDIR:-/tmp}}
RANDSTR=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 10; echo)
WORKDIR=$SCRATCH_BASE/workdir_$(date +%y%m%d-%H%M%S)_${RANDSTR}_$(echo "$PROC" | sed 's/\//_/g')_$JOBNUM
mkdir -p $WORKDIR
# clean up on ANY exit (success, failure, or an `exit 1` from copy_to_eos
# below) - not just the success path, so a failed job doesn't leave its
# local scratch copy behind. Condor tears down per-job scratch regardless
# once the job exits, but this also matters for a non-condor/local run.
trap 'rm -rf "$WORKDIR"' EXIT

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
# (triggered by the "++" in makeNtuples.C++/makeNtuplesPaired.C++) doesn't race
# with other concurrent jobs compiling into the same shared delphes_analyzers/ dir
mkdir -p $WORKDIR/analyzer
cp $ANALYZER_PATH/EventData.h $ANALYZER_PATH/FatJetMatching.h $ANALYZER_PATH/ParticleID.h $ANALYZER_PATH/ParticleInfo.h \
   $ANALYZER_PATH/makeNtuples.C $ANALYZER_PATH/makeNtuplesPaired.C $WORKDIR/analyzer/

# merge each individual card's own per-batch files into one - keyed on the
# flat, deduplicated CARD_NAMES (unchanged from before this file split into
# OUTPUT_UNITS/CARD_NAMES - see their own comment above), independent of
# whether a card is used standalone or as half of a pair below
for name in "${CARD_NAMES[@]}"; do
    if [ $nbatch -eq 1 ]; then
        mv $WORKDIR/$name/events_delphes_0.root $WORKDIR/$name/events_delphes.root
    else
        hadd -f $WORKDIR/$name/events_delphes.root $WORKDIR/$name/*.root
    fi
done

for unit in "${OUTPUT_UNITS[@]}"; do
    IFS='+' read -ra parts <<< "$unit"

    if [ "${#parts[@]}" -eq 2 ]; then
        # offline+HLT pair -> one matched ntuple (makeNtuplesPaired.C) - see
        # OUTPUT_UNITS/CARD_NAMES's own comment above and
        # delphes_analyzers/makeNtuplesPaired.C's own docstring
        offline_name=${parts[0]}
        hlt_name=${parts[1]}
        mkdir -p $WORKDIR/$unit
        LOCAL_NTUPLE_PATH=$WORKDIR/$unit/ntuple_$JOBNUM.root
        (
            cd $WORKDIR/analyzer
            source /cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh
            export ROOT_INCLUDE_PATH=$ROOT_INCLUDE_PATH:/cvmfs/sft.cern.ch/lcg/releases/delphes/3.5.1pre09-9fe9c/x86_64-el9-gcc13-opt/include
            root -b -q "makeNtuplesPaired.C++(\"$WORKDIR/$offline_name/events_delphes.root\", \"$WORKDIR/$hlt_name/events_delphes.root\", \"$LOCAL_NTUPLE_PATH\", \"JetPUPPIAK8\", \"GenJetAK8\", true, false, $USE_V1_LABELS)"
        )
        if [ "$KEEP_DELPHES_OUTPUT" = "true" ]; then
            copy_to_eos $WORKDIR/$offline_name/events_delphes.root $OUTPUT_PATH/$PROC/$unit/events_delphes_offline_$JOBNUM.root || exit 1
            copy_to_eos $WORKDIR/$hlt_name/events_delphes.root $OUTPUT_PATH/$PROC/$unit/events_delphes_hlt_$JOBNUM.root || exit 1
        fi
        copy_to_eos $LOCAL_NTUPLE_PATH $OUTPUT_PATH/$PROC/$unit/ntuple_$JOBNUM.root || exit 1
    else
        # single card - unchanged from before
        name=${parts[0]}
        LOCAL_NTUPLE_PATH=$WORKDIR/$name/ntuple_$JOBNUM.root
        (
            cd $WORKDIR/analyzer
            source /cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh
            export ROOT_INCLUDE_PATH=$ROOT_INCLUDE_PATH:/cvmfs/sft.cern.ch/lcg/releases/delphes/3.5.1pre09-9fe9c/x86_64-el9-gcc13-opt/include
            root -b -q "makeNtuples.C++(\"$WORKDIR/$name/events_delphes.root\", \"$LOCAL_NTUPLE_PATH\", \"JetPUPPIAK8\", \"GenJetAK8\", true, false, $USE_V1_LABELS)"
        )
        if [ "$KEEP_DELPHES_OUTPUT" = "true" ]; then
            copy_to_eos $WORKDIR/$name/events_delphes.root $OUTPUT_PATH/$PROC/$name/events_delphes_$JOBNUM.root || exit 1
        fi
        copy_to_eos $LOCAL_NTUPLE_PATH $OUTPUT_PATH/$PROC/$name/ntuple_$JOBNUM.root || exit 1
    fi
done

# (workspace cleanup happens via the EXIT trap set above, not here - so it
# still runs even if something above exited early)

echo -e "\033[1mJob done. Generated $NEVENT events for $PROC.\033[0m"
for unit in "${OUTPUT_UNITS[@]}"; do
    IFS='+' read -ra parts <<< "$unit"
    if [ "${#parts[@]}" -eq 2 ] && [ "$KEEP_DELPHES_OUTPUT" = "true" ]; then
        echo -e "\033[1m[$unit] Offline Delphes file path: $OUTPUT_PATH/$PROC/$unit/events_delphes_offline_$JOBNUM.root\033[0m"
        echo -e "\033[1m[$unit] HLT Delphes file path: $OUTPUT_PATH/$PROC/$unit/events_delphes_hlt_$JOBNUM.root\033[0m"
    elif [ "$KEEP_DELPHES_OUTPUT" = "true" ]; then
        echo -e "\033[1m[$unit] Delphes file path: $OUTPUT_PATH/$PROC/$unit/events_delphes_$JOBNUM.root\033[0m"
    fi
    echo -e "\033[1m[$unit] Ntuple file path: $OUTPUT_PATH/$PROC/$unit/ntuple_$JOBNUM.root\033[0m"
done
