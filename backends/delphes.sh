#!/bin/bash
# Delphes backend for run.sh: fast parameterised simulation, the original (and
# still default) way this repo makes its datasets. Unchanged in behaviour from
# when all of this lived directly in run.sh - it was only moved here so that a
# second backend (backends/fullsim.sh) could share run.sh's generation loop,
# EOS copying and watchdogs instead of duplicating them.
#
# Implements the backend interface documented at the top of run.sh. BACKEND_OPTS
# is the comma-separated list of Delphes cards (what used to be run.sh's
# positional arg 5, DELPHES_CARD_NAMES).

BACKEND_DEFAULT_OPTS=onlyFatJet

DELPHES_PATH=${DELPHES_PATH:-/eos/user/l/llambrec/jetclass/delphes}

# Per-card Delphes-reconstruction timeout, in seconds - the same class of
# hang risk run.sh's run_gen_with_timeout() guards against, just on the
# detector-sim side instead of the generation side. Found the hard way:
# adding the offline+HLT card PAIR (DELPHES_CARD_NAMES like
# "onlyFatJet+onlyFatJetHLT") doubled the DelphesHepMC2 work per batch (one
# run per card), and 8 of 70 train_higgs2p jobs in that first paired
# production then ran the FULL HTCondor "workday" wall-time budget (8h)
# before being killed by SYSTEM_PERIODIC_REMOVE - producing ZERO output,
# since run.sh only copies to EOS once, at the very end - while every
# surrounding job finished in under 2h. DelphesHepMC2 was the only
# completely unbounded step left in the per-batch loop.
#
# Unlike run.sh's run_gen_with_timeout(), a timed-out DelphesHepMC2 call is NOT
# retried: it reconstructs the SAME already-generated events.hepmc, so a
# hang triggered by specific event content would just repeat identically -
# there's no "fresh random draw" to retry into like run_gen.sh has. A
# timeout here is instead treated exactly like any other DelphesHepMC2
# failure already was: this batch's contribution for that card is skipped
# (events_delphes_$i.root simply isn't produced), the same small,
# already-tolerated yield reduction a failed run_gen.sh attempt causes.
DELPHES_TIMEOUT_SEC=${DELPHES_TIMEOUT_SEC:-900}

# Runs DelphesHepMC2 under the timeout above, with the same setsid+pkill -g
# process-group-kill approach as run.sh's run_gen_with_timeout() (see its own comment
# for why plain `timeout` alone isn't enough to reliably kill the whole
# subprocess tree). No retry loop here - see DELPHES_TIMEOUT_SEC's own
# comment for why retrying wouldn't help.
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

backend_setup() {
    DELPHES_CARD_NAMES=$BACKEND_OPTS
    ANALYZER_PATH=$REPO_DIR/delphes_analyzers

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
    # install isn't patched for it: an unpatched Delphes silently IGNORES unknown
    # parameters, so the offline and HLT runs would quietly go back to drawing
    # independent vertex positions/pile-up overlays. See
    # delphes_cards/KNOWN_ISSUES.md and delphes_patches/.
    if grep -qE '^\s*set PerEventSeed true' "${CARD_PATHS[@]}" && \
       ! grep -aq "PerEventSeed requires a nonzero global RandomSeed" "$DELPHES_PATH/libDelphes.so"; then
        echo "ERROR: a Delphes card sets PerEventSeed, but $DELPHES_PATH is not patched for it - apply delphes_patches/PileUpMerger_PerEventSeed.patch there and rebuild (see INSTALL.md)" >&2
        exit 1
    fi
}

# cwd on entry: $WORKDIR/proc_base, with this batch's events.hepmc in it
backend_run_batch() {
    local i=$1

    # run each requested Delphes card on the same events.hepmc
    ln -sf $DELPHES_PATH/MinBias_100k.pileup .
    # One random seed per batch, shared by every card of the batch (prepended
    # to a per-batch copy of each card as the global RandomSeed). With the
    # patched PileUpMerger's `PerEventSeed true` (see
    # delphes_cards/KNOWN_ISSUES.md) this gives the offline and HLT runs of the
    # same event the same vertex position and pile-up overlay, so the two only
    # differ by detector effects. Random (not derived from PROC/JOBNUM) so that
    # different productions don't reuse the same overlays; logged for
    # reproducibility. Nonzero: Delphes treats RandomSeed 0 as time-based.
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

backend_finalize() {

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
            if [ "$KEEP_INTERMEDIATE" = "true" ]; then
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
            if [ "$KEEP_INTERMEDIATE" = "true" ]; then
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
        if [ "${#parts[@]}" -eq 2 ] && [ "$KEEP_INTERMEDIATE" = "true" ]; then
            echo -e "\033[1m[$unit] Offline Delphes file path: $OUTPUT_PATH/$PROC/$unit/events_delphes_offline_$JOBNUM.root\033[0m"
            echo -e "\033[1m[$unit] HLT Delphes file path: $OUTPUT_PATH/$PROC/$unit/events_delphes_hlt_$JOBNUM.root\033[0m"
        elif [ "$KEEP_INTERMEDIATE" = "true" ]; then
            echo -e "\033[1m[$unit] Delphes file path: $OUTPUT_PATH/$PROC/$unit/events_delphes_$JOBNUM.root\033[0m"
        fi
        echo -e "\033[1m[$unit] Ntuple file path: $OUTPUT_PATH/$PROC/$unit/ntuple_$JOBNUM.root\033[0m"
    done
}
