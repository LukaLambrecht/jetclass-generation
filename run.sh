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
# (all actually `export`ed, unlike before - previously these were plain
# shell-local assignments, invisible to run_gen.sh/mg5_aMC/py8_main's own
# child processes; harmless for PYTHIA8DATA/LHAPDFCONFIG, which those tools
# can also resolve via their own build-time-baked-in fallback paths, but not
# for MG5's *python* LHAPDF interface below, which has no such fallback -
# see PYTHONPATH/LD_LIBRARY_PATH's own comment for what that broke)
export LHAPDFCONFIG=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/lhapdf6_py3/share/LHAPDF/lhapdf.conf
export LHAPDF_DATA_PATH=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/lhapdf6_py3/share/LHAPDF
export PYTHIA8DATA=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/pythia8/share/Pythia8/xmldoc
# MG5's own *python* LHAPDF interface (used to resolve an explicit `lhaid`
# in mg5_step2_templ.dat, e.g. jetclass2/train_higgs2p's lhaid 315000 ->
# NNPDF31_nnlo_as_0118_mc_hessian_pdfas) is a separate thing from the
# LHAPDF_DATA_PATH-based C++ interface above - it needs `import lhapdf` to
# succeed, which needs both the compiled extension module's own directory on
# PYTHONPATH and libLHAPDF.so findable via LD_LIBRARY_PATH. Without these
# (the previous state), MG5 printed a "Failed to access python version of
# LHAPDF" warning and silently fell back to whatever default PDF set is
# bundled inside its own freshly generated proc/lib/PDFsets/ (NNPDF31_lo_as_0118,
# NOT the requested set) instead of erroring - found by cross-checking
# generate_events' own log output against the process' own lhaid.
export PYTHONPATH=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/lhapdf6_py3/lib64/python3.9/site-packages:$PYTHONPATH
export LD_LIBRARY_PATH=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/lhapdf6_py3/lib:$LD_LIBRARY_PATH

## fixed configuration
GENCFG_PATH=$(realpath gen_configs)

# Per-batch generation timeout/retry, in seconds - guards against a single
# pathological (mass, pT_min) or pT_hat draw hanging the whole job. Found
# the hard way: jetclass2/train_higgs2p production jobs stuck for 90+
# minutes on ONE batch (confirmed via condor_ssh_to_job - the shower
# process pegged at ~99% CPU, /proc/<pid>/wchan == 0 i.e. genuinely
# spinning in user-space, not I/O-blocked, with byte-identical stdout the
# whole time - not a slow-but-real event, an actual hang), across several
# DIFFERENT random parameter draws, so it's some general kinematic regime
# Pythia8's shower/hadronization can get stuck on, not one specific bad
# point. A "healthy" batch takes ~1 minute (measured); 900s (15x that) is
# generous headroom for genuinely slow-but-real batches while still
# bounding a hung one to a small fraction of the job's total wall time.
GEN_TIMEOUT_SEC=${GEN_TIMEOUT_SEC:-900}
GEN_MAX_ATTEMPTS=${GEN_MAX_ATTEMPTS:-5}

# Runs `./run_gen.sh $1` (cwd: proc_base) with the timeout/retry policy
# above. Each retry re-invokes run_gen.sh from scratch, which re-samples a
# FRESH random (mass,pT_min)/pT_hat draw itself (see run_gen_default.sh/
# gen_configs/*/run_gen.sh's own `shuf -n 1 ...`) - so a retry isn't just
# "try the same hang again", it's a real second chance at a different draw.
# `setsid` gives the attempt its OWN process group (pgid == its own pid,
# captured via $!) so a timeout can reliably SIGKILL the WHOLE subprocess
# tree (run_gen.sh -> generate_events -> MG5aMC_PY8_interface/py8_main, none
# of which `exec` down into the next stage) via `pkill -g` - not just
# run_gen.sh's own bash process, which would otherwise leave the actual
# hung worker process orphaned and still spinning on the shared node.
# `pkill -g <that exact pgid>` is safe to use blindly (no risk of killing a
# different concurrent job's own legitimate process on a shared worker
# node) specifically because it's scoped to this one setsid-created group,
# not matched by command name (which IS shared across concurrent jobs -
# every job runs the literal same "MG5aMC_PY8_interface py8.dat").
# On exhausting GEN_MAX_ATTEMPTS, gives up and returns nonzero - the caller
# (the batch loop below) already tolerates a batch producing no usable
# events.hepmc (events_delphes.root just doesn't get moved forward for that
# one batch), so the job still completes with a very slightly reduced
# yield instead of hanging for its entire wall-time budget.
run_gen_with_timeout() {
    local nevent_gen=$1 attempt rc
    for ((attempt=1; attempt<=GEN_MAX_ATTEMPTS; attempt++)); do
        setsid timeout -k 30 "${GEN_TIMEOUT_SEC}s" env MG5_PATH="$MG5_PATH" GENCFG_PATH="$GENCFG_PATH" ./run_gen.sh "$nevent_gen" &
        local pgid=$!
        wait $pgid
        rc=$?
        pkill -KILL -g $pgid 2>/dev/null
        heartbeat
        if [ $rc -eq 0 ]; then
            return 0
        fi
        echo "WARNING: run_gen.sh attempt $attempt/$GEN_MAX_ATTEMPTS failed or timed out (rc=$rc, limit ${GEN_TIMEOUT_SEC}s) - retrying with a fresh random draw" >&2
    done
    echo "ERROR: run_gen.sh failed $GEN_MAX_ATTEMPTS times in a row - giving up on this batch (events.hepmc likely missing/stale; the batch's events_delphes.root simply won't be produced, see caller)" >&2
    return 1
}

# Per-card Delphes-reconstruction timeout, in seconds - the same class of
# hang risk run_gen_with_timeout() above guards against, just on the
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
# Unlike run_gen_with_timeout(), a timed-out DelphesHepMC2 call is NOT
# retried: it reconstructs the SAME already-generated events.hepmc, so a
# hang triggered by specific event content would just repeat identically -
# there's no "fresh random draw" to retry into like run_gen.sh has. A
# timeout here is instead treated exactly like any other DelphesHepMC2
# failure already was: this batch's contribution for that card is skipped
# (events_delphes_$i.root simply isn't produced), the same small,
# already-tolerated yield reduction a failed run_gen.sh attempt causes.
DELPHES_TIMEOUT_SEC=${DELPHES_TIMEOUT_SEC:-900}

# Runs DelphesHepMC2 under the timeout above, with the same setsid+pkill -g
# process-group-kill approach as run_gen_with_timeout() (see its own comment
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

# Stall watchdog for the per-batch generation loop (startup included), in
# seconds. The timeouts above can only bound a step whose processes can
# actually be killed - a process blocked on an EOS FUSE read (uninterruptible
# sleep) ignores even SIGKILL, so `timeout` never returns and neither does
# the `wait` on it. Found the hard way: 24 of 140 jetclass2/train_higgs2p
# jobs in the 20260917 production sat out the full 8h wall-time budget and
# were killed by SYSTEM_PERIODIC_REMOVE with zero output, their memory
# never growing past 15-50 MB (a healthy job reaches ~400 MB within 20 min)
# - i.e. stuck before producing a single event, most likely in the first
# batch's MG5 setup (which runs straight out of the MG5 install on EOS; qcd,
# which doesn't, was unaffected), in the same evening EOS was also failing
# writes (see copy_to_eos()). Every legitimate step between two heartbeat
# calls is bounded by one of the timeouts above (<= 930s), so no heartbeat
# for STALL_TIMEOUT_SEC means something is stuck beyond what they can kill:
# the watchdog then aborts run.sh, so the job fails within the hour instead
# of holding its slot for 8h. Only armed during the batch loop, not for the
# final merge/ntupling/copy steps, whose durations aren't bounded this way.
STALL_TIMEOUT_SEC=${STALL_TIMEOUT_SEC:-1800}
STALL_POLL_SEC=${STALL_POLL_SEC:-60}

heartbeat() {
    [ -n "$HEARTBEAT_FILE" ] && touch "$HEARTBEAT_FILE"
}

start_stall_watchdog() {
    HEARTBEAT_FILE=$WORKDIR/.heartbeat
    heartbeat
    local main_pid=$$
    (
        set +x  # don't flood the job's stderr (run.sh runs under bash -x)
        while sleep $STALL_POLL_SEC; do
            local age=$(( $(date +%s) - $(stat -c %Y "$HEARTBEAT_FILE" 2>/dev/null || echo 0) ))
            if [ $age -gt $STALL_TIMEOUT_SEC ]; then
                echo "ERROR: no progress for ${age}s (limit STALL_TIMEOUT_SEC=${STALL_TIMEOUT_SEC}s) - something is stuck beyond what the per-step timeouts can kill (most likely a read from EOS); aborting the job" >&2
                kill -TERM $main_pid 2>/dev/null
                sleep 10
                kill -KILL $main_pid 2>/dev/null
                exit 0
            fi
        done
    ) &
    WATCHDOG_PID=$!
}

stop_stall_watchdog() {
    [ -n "$WATCHDOG_PID" ] && kill $WATCHDOG_PID 2>/dev/null
    WATCHDOG_PID=""
    HEARTBEAT_FILE=""
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
#
# "Landed" means the EOS *server* holds exactly as many bytes as the local
# source - not just that the file exists. Found the hard way: in the
# 20260917 production 3 of 340 ntuples were left TRUNCATED on EOS (0.4-4.6
# MB instead of ~60 MB, unreadable) by jobs that exited 0 - `mv` onto the
# FUSE mount reported success and `[ -f ]` passed, while the upload behind
# it failed (other jobs logged xrootd write timeouts to the same EOS disk
# server in the same minutes). The mount's own `stat` can't be trusted for
# this either (it can answer from its local write cache), so for /eos paths
# the copy goes over xrootd directly (xrdcp, with an end-to-end adler32
# checksum) and the size is read back from the server (xrdfs stat). The
# FUSE `cp` + local `stat` is kept only as a fallback, for an attempt where
# xrdcp itself fails (e.g. no xrootd credentials on some node) or for a
# non-EOS OUTPUT_PATH. `cp` rather than `mv` so a failed/partial attempt
# can be retried from the still-intact local source; a destination left
# behind by the last failed attempt is removed, so a missing ntuple (not a
# corrupt one) is what signals the failure.
EOS_XRD_HOST=eosuser.cern.ch

# Canonical xrootd path for a path on the EOS FUSE mount, or nothing (and
# nonzero) if it isn't on EOS. `realpath` resolves /eos/user/l/llambrec to
# the FUSE-only alias /eos/home-l/llambrec, which the xrootd server rejects
# ("public access level restriction") - map it back.
eos_xrd_path() {
    case "$1" in
        /eos/home-?/*) echo "/eos/user/${1:10:1}/${1:12}" ;;
        /eos/user/*)   echo "$1" ;;
        *)             return 1 ;;
    esac
}

copy_to_eos() {
    local src=$1 dst=$2 dstdir attempt expected got xrd_path
    dstdir=$(dirname "$dst")
    expected=$(stat -c %s "$src")
    xrd_path=$(eos_xrd_path "$dst")
    for attempt in 1 2 3 4 5; do
        got=""
        if [ -n "$xrd_path" ] && command -v xrdcp >/dev/null && \
           xrdcp -f -p -s --cksum adler32 "$src" "root://$EOS_XRD_HOST/$xrd_path"; then
            got=$(xrdfs $EOS_XRD_HOST stat "$xrd_path" 2>/dev/null | awk '/^Size:/{print $2}')
        else
            [ -n "$xrd_path" ] && echo "WARNING: xrdcp to EOS failed (attempt $attempt/5) - falling back to the FUSE mount for this attempt" >&2
            mkdir -p "$dstdir"
            cp -f "$src" "$dst" && got=$(stat -c %s "$dst" 2>/dev/null)
        fi
        if [ "$got" = "$expected" ]; then
            rm -f "$src"
            return 0
        fi
        echo "WARNING: copy to EOS failed or incomplete (attempt $attempt/5, ${got:-no} of $expected bytes): $src -> $dst" >&2
        sleep $((attempt * 3))
    done
    rm -f "$dst"
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
trap 'stop_stall_watchdog; rm -rf "$WORKDIR"' EXIT

cd $WORKDIR

# generate delphes, in a batch of NEVENT_GEN
nbatch=$((NEVENT / NEVENT_GEN))

# see STALL_TIMEOUT_SEC's own comment - armed for the batch loop only
start_stall_watchdog

for ((i=0; i<nbatch; i++)); do

    echo "Batch: $i"
    heartbeat

    # copy genpack if not exist
    cd $WORKDIR
    if [ ! -d "proc_base" ]; then
        mkdir proc_base
        # Retry+verify these two copies before proceeding - same reasoning as
        # copy_to_eos() below, just in the other direction (EOS -> local
        # scratch instead of local scratch -> EOS): EOS's FUSE mount can
        # spuriously fail a `cp` mid-read too, not just a `mkdir`/`mv` under
        # load. Found the hard way: an unchecked "cp: error reading
        # '.../run_gen_default.sh': Input/output error" once left
        # proc_base/run_gen.sh missing for an entire job - every one of its
        # 10 batches then failed to generate anything, yet the job still
        # exited 0 and copied an EMPTY ntuple to EOS as if it were real
        # output (found via print_njets.py's per-label diagnostics: one job's
        # ntuple among ~170 others had exactly 0 jets - nothing in the job's
        # own logging/exit code flagged it). Checking "at least one file
        # landed" (mirroring validate_proc()'s own check in run_condor.py)
        # rather than `cp`'s exit code alone, since a partially-failed `cp -r`
        # can still exit 0 having copied only some of the files.
        for attempt in 1 2 3 4 5; do
            cp -r $GENCFG_PATH/$PROC/* proc_base/
            if [ -n "$(ls -A proc_base 2>/dev/null)" ]; then
                break
            fi
            echo "WARNING: copying gen_configs/$PROC into proc_base failed or produced nothing (attempt $attempt/5) - retrying" >&2
            sleep $((attempt * 3))
        done
        if [ -z "$(ls -A proc_base 2>/dev/null)" ]; then
            echo "ERROR: giving up copying gen_configs/$PROC into proc_base after 5 attempts - proc_base is empty" >&2
            exit 1
        fi
        # if genpack does not have a run_gen.sh, use the default
        if [ ! -f "proc_base/run_gen.sh" ]; then
            for attempt in 1 2 3 4 5; do
                cp $GENCFG_PATH/run_gen_default.sh proc_base/run_gen.sh
                if [ -s "proc_base/run_gen.sh" ]; then
                    break
                fi
                echo "WARNING: copying run_gen_default.sh failed or produced an empty file (attempt $attempt/5) - retrying" >&2
                sleep $((attempt * 3))
            done
            if [ ! -s "proc_base/run_gen.sh" ]; then
                echo "ERROR: giving up copying run_gen_default.sh after 5 attempts - proc_base/run_gen.sh missing/empty" >&2
                exit 1
            fi
        fi
    fi
    heartbeat
    cd $WORKDIR/proc_base

    # generate GEN events once per batch - shared across all Delphes cards
    rm -f events.hepmc
    run_gen_with_timeout $NEVENT_GEN

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

stop_stall_watchdog

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
