#!/bin/bash
# Delphes backend for run.sh: fast parameterised simulation, and the default.
#
# Implements the backend interface documented at the top of run.sh.
# BACKEND_OPTS is the comma-separated list of Delphes cards.

BACKEND_DEFAULT_OPTS=onlyFatJet

DELPHES_PATH=${DELPHES_PATH:-/eos/user/l/llambrec/jetclass/delphes}

# Per-card reconstruction timeout, in seconds. DelphesHepMC2 is otherwise the one
# unbounded step in the batch loop, and a hung run costs the whole job: run.sh
# copies to EOS only at the very end, so a wall-time kill produces no output at
# all.
#
# A timed-out call is not retried, and the script skips to the next batch
# (same behaviour as for other Delphes errors or a failed generation step).
DELPHES_TIMEOUT_SEC=${DELPHES_TIMEOUT_SEC:-900}

# Run DelphesHepMC2 under the timeout above, in its own process group so the
# whole subprocess tree can be killed (as in run.sh's run_gen_with_timeout).
run_delphes_with_timeout() {
    local card_path=$1 out=$2 in=$3 rc
    setsid timeout -k 30 "${DELPHES_TIMEOUT_SEC}s" $DELPHES_PATH/DelphesHepMC2 "$card_path" "$out" "$in" &
    local pgid=$!
    wait $pgid
    rc=$?
    pkill -KILL -g $pgid 2>/dev/null
    heartbeat
    if [ $rc -ne 0 ]; then
        echo "WARNING: DelphesHepMC2 (card $(basename "$card_path")) failed or timed out (rc=$rc, limit ${DELPHES_TIMEOUT_SEC}s) - skipping this batch for this card" >&2
    fi
    return $rc
}

# Map a short card option to its .tcl file name in delphes_cards/.
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

# Resolve and validate the requested cards before any work is done.
backend_setup() {
    # A CMSSW GEN fragment never produces an events.hepmc, which is the only
    # input Delphes can read here. Refused loudly, rather than reaching
    # DelphesHepMC2 with no input and "succeeding" with an empty ntuple.
    if [ "$PROC_KIND" = "cmssw_fragment" ]; then
        echo "ERROR: process '$PROC' is a CMSSW GEN fragment (gen_configs/$PROC/fragment.py)," >&2
        echo "       which only the fullsim backend can generate. Use: run.sh fullsim $PROC ..." >&2
        exit 1
    fi

    DELPHES_CARD_NAMES=$BACKEND_OPTS
    ANALYZER_PATH=$REPO_DIR/delphes_analyzers

    # Each comma-separated entry is either one card name, or an offline+HLT pair
    # joined by "+" that is jet-matched into a single combined ntuple so an
    # offline jet's own HLT reconstruction stays recoverable.
    #
    # OUTPUT_UNITS keeps the raw entries and drives the ntuplizing loop;
    # CARD_NAMES is the flat deduplicated list of cards Delphes must actually be
    # run for, so a card used both standalone and inside a pair runs only once.
    declare -ga OUTPUT_UNITS
    IFS=',' read -ra OUTPUT_UNITS <<< "$DELPHES_CARD_NAMES"
    declare -ga CARD_NAMES
    declare -gA SEEN_CARD
    for unit in "${OUTPUT_UNITS[@]}"; do
        IFS='+' read -ra parts <<< "$unit"
        for name in "${parts[@]}"; do
            if [ -z "${SEEN_CARD[$name]}" ]; then
                CARD_NAMES+=("$name")
                SEEN_CARD[$name]=1
            fi
        done
    done
    declare -ga CARD_PATHS
    for name in "${CARD_NAMES[@]}"; do
        CARD_PATHS+=("$REPO_DIR/delphes_cards/$(card_file_for_name "$name")")
    done

    # Fail fast if a card asks for PileUpMerger's PerEventSeed but this Delphes
    # install is not patched for it: an unpatched Delphes silently ignores unknown
    # parameters, so the offline and HLT runs would quietly draw independent
    # vertex positions and pile-up overlays. See delphes_patches/.
    if grep -qE '^\s*set PerEventSeed true' "${CARD_PATHS[@]}" && \
       ! grep -aq "PerEventSeed requires a nonzero global RandomSeed" "$DELPHES_PATH/libDelphes.so"; then
        echo "ERROR: a Delphes card sets PerEventSeed, but $DELPHES_PATH is not patched for it - apply delphes_patches/PileUpMerger_PerEventSeed.patch there and rebuild (see INSTALL.md)" >&2
        exit 1
    fi
}

# Reconstruct one batch with every requested card.
# cwd on entry: $WORKDIR/proc_base, with this batch's events.hepmc in it
backend_run_batch() {
    local i=$1

    # Set pileup file.
    # Note: only used in practice if the pileup is set to > 0 in the Delphes card(s).
    ln -sf $DELPHES_PATH/MinBias_100k.pileup .
    # One seed per batch, shared by every card of that batch by prepending it to
    # a per-batch copy of each card. Together with the patched PileUpMerger's
    # `PerEventSeed true` this gives the offline and HLT runs of an event the
    # same vertex position and pile-up overlay, so the two differ only by
    # detector effects. Drawn at random so separate productions do not reuse
    # overlays, and logged for reproducibility. Nonzero, because Delphes reads
    # RandomSeed 0 as "seed from the clock".
    BATCH_SEED=$(( $(od -An -N4 -tu4 /dev/urandom) % 2147483646 + 1 ))
    echo "Batch $i: Delphes RandomSeed $BATCH_SEED"
    mkdir -p $WORKDIR/seeded_cards
    for idx in "${!CARD_NAMES[@]}"; do
        name=${CARD_NAMES[$idx]}
        path=$WORKDIR/seeded_cards/$(basename "${CARD_PATHS[$idx]}")
        { echo "set RandomSeed $BATCH_SEED"; cat "${CARD_PATHS[$idx]}"; } > "$path"
        mkdir -p $WORKDIR/$name
        rm -f events_delphes.root
        run_delphes_with_timeout $path events_delphes.root events.hepmc
        if [ $? -eq 0 ]; then
            mv events_delphes.root $WORKDIR/$name/events_delphes_$i.root
        fi
    done
    cd $WORKDIR
}

# Collapse the per-batch Delphes files every 100 batches, to keep their number
# manageable.
backend_intermediate_merge() {
    local i=$1

    # intermediate file merging for every 100 batches
    if [ $(((i+1) % 100)) -eq 0 ]; then
        for name in "${CARD_NAMES[@]}"; do
            hadd -f $WORKDIR/$name/merged_events_delphes_$i.root $WORKDIR/$name/events_delphes_*.root
            if [ $? -eq 0 ]; then
                rm -f $WORKDIR/$name/events_delphes_*.root
            fi
        done
    fi
}

# Merge the batches, ntuplize each output unit, and copy the results to EOS.
backend_finalize() {

    # Work in a per-job copy of delphes_analyzers, so that ACLiC's compilation
    # (the "++" in makeNtuples.C++) cannot race with other concurrent jobs
    # compiling into the same shared directory.
    mkdir -p $WORKDIR/analyzer
    cp $ANALYZER_PATH/EventData.h $ANALYZER_PATH/FatJetMatching.h $ANALYZER_PATH/ParticleID.h $ANALYZER_PATH/ParticleInfo.h \
       $ANALYZER_PATH/makeNtuples.C $ANALYZER_PATH/makeNtuplesPaired.C $WORKDIR/analyzer/

    # Merge each card's per-batch files, keyed on the deduplicated card list so
    # this is independent of how the cards are grouped into output units.
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
            # offline+HLT pair -> one jet-matched ntuple
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
            if [ "$KEEP_INTERMEDIATE" = "true" ]; then
                copy_to_eos $WORKDIR/$offline_name/events_delphes.root $OUTPUT_PATH/$PROC/$unit/events_delphes_offline_$JOBNUM.root || exit 1
                copy_to_eos $WORKDIR/$hlt_name/events_delphes.root $OUTPUT_PATH/$PROC/$unit/events_delphes_hlt_$JOBNUM.root || exit 1
            fi
            copy_to_eos $LOCAL_NTUPLE_PATH $OUTPUT_PATH/$PROC/$unit/ntuple_$JOBNUM.root || exit 1
        else
            # single card
            name=${parts[0]}
            LOCAL_NTUPLE_PATH=$WORKDIR/$name/ntuple_$JOBNUM.root
            (
                cd $WORKDIR/analyzer
                source /cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh
                export ROOT_INCLUDE_PATH=$ROOT_INCLUDE_PATH:/cvmfs/sft.cern.ch/lcg/releases/delphes/3.5.1pre09-9fe9c/x86_64-el9-gcc13-opt/include
                root -b -q "makeNtuples.C++(\"$WORKDIR/$name/events_delphes.root\", \"$LOCAL_NTUPLE_PATH\", \"JetPUPPIAK8\", \"GenJetAK8\", true, false, $USE_V1_LABELS)"
            )
            if [ "$KEEP_INTERMEDIATE" = "true" ]; then
                copy_to_eos $WORKDIR/$name/events_delphes.root $OUTPUT_PATH/$PROC/$name/events_delphes_$JOBNUM.root || exit 1
            fi
            copy_to_eos $LOCAL_NTUPLE_PATH $OUTPUT_PATH/$PROC/$name/ntuple_$JOBNUM.root || exit 1
        fi
    done

    # Workspace cleanup is left to run.sh's EXIT trap, so it also runs when
    # something above exits early.

    echo -e "\033[1mJob done. Generated $NEVENT events for $PROC.\033[0m"
    for unit in "${OUTPUT_UNITS[@]}"; do
        IFS='+' read -ra parts <<< "$unit"
        if [ "${#parts[@]}" -eq 2 ] && [ "$KEEP_INTERMEDIATE" = "true" ]; then
            echo -e "\033[1m[$unit] Offline Delphes file path: $OUTPUT_PATH/$PROC/$unit/events_delphes_offline_$JOBNUM.root\033[0m"
            echo -e "\033[1m[$unit] HLT Delphes file path: $OUTPUT_PATH/$PROC/$unit/events_delphes_hlt_$JOBNUM.root\033[0m"
        elif [ "$KEEP_INTERMEDIATE" = "true" ]; then
            echo -e "\033[1m[$unit] Delphes file path: $OUTPUT_PATH/$PROC/$unit/events_delphes_$JOBNUM.root\033[0m"
        fi
        echo -e "\033[1m[$unit] Ntuple file path: $OUTPUT_PATH/$PROC/$unit/ntuple_$JOBNUM.root\033[0m"
    done
}
