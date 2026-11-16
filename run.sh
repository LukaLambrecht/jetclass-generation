#!/bin/bash -x

# Generate a jetclass dataset: event generation followed by detector simulation
# and ntupling by one of two interchangeable backends.
#
#   ./run.sh <backend> <proc> <nevent> <nevent_gen> <jobnum> [<backend_opts>] [<output_path>] [<keep_intermediate>]
#
# BACKEND       delphes (fast parameterised simulation) or fullsim (CMS full
#               simulation + reconstruction + HLT in CMSSW). Both write the same
#               ntuple schema, so downstream scripts need not know which ran.
# PROC          process config under gen_configs/, e.g. jetclass2/train_qcd
# NEVENT        total number of events for this job
# NEVENT_GEN    events per batch; NEVENT/NEVENT_GEN batches run, each its own
#               generation + reconstruction, merged at the end
# JOBNUM        job number, used for the output file name
# BACKEND_OPTS  backend-specific; defaults to the backend's own default.
#               delphes: comma-separated Delphes cards, where an entry may be an
#               offline+HLT pair joined by "+" to produce one jet-matched ntuple.
#               fullsim: "offline+hlt" or "offline".
# OUTPUT_PATH   output directory, in place of the default below
# KEEP_INTERMEDIATE  also copy the backend's intermediate detector files, not
#               just the ntuples (default false)
BACKEND=${1:?usage: run.sh <backend> <proc> <nevent> <nevent_gen> <jobnum> [opts] [output_path] [keep_intermediate]}
PROC=$2
NEVENT=$3
NEVENT_GEN=$4
JOBNUM=$5

REPO_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# The backend supplies BACKEND_DEFAULT_OPTS and the functions backend_setup /
# backend_run_batch <i> / backend_intermediate_merge <i> / backend_finalize.
BACKEND_FILE=$REPO_DIR/backends/$BACKEND.sh
if [ ! -f "$BACKEND_FILE" ]; then
    echo "ERROR: unknown backend '$BACKEND' - expected one of: $(cd "$REPO_DIR/backends" && ls *.sh | sed 's/\.sh$//' | tr '\n' ' ')" >&2
    exit 1
fi
# No-op hook defined before sourcing, so a backend that defines its own wins and
# one with nothing to do between batches need not define it at all.
backend_intermediate_merge() { :; }

source "$BACKEND_FILE"

# How this process produces generator-level events, from what its gen_configs/
# directory contains:
#   hepmc           a standalone MG5_aMC+Pythia8 run writes events.hepmc, which
#                   the backend reconstructs. Works for either backend.
#   cmssw_fragment  the directory holds a fragment.py that CMSSW runs itself in
#                   its GEN step. FullSim only; delphes.sh refuses such a process.
if [ -f "$REPO_DIR/gen_configs/$PROC/fragment.py" ]; then
    PROC_KIND=cmssw_fragment
else
    PROC_KIND=hepmc
fi

BACKEND_OPTS=${6:-$BACKEND_DEFAULT_OPTS}
OUTPUT_PATH=${7:-/eos/user/l/llambrec/jetclass/output_test}
KEEP_INTERMEDIATE=${8:-false}

# Setup environment

# ============ basic configuration ============
# MG5_PATH honours a pre-set value, so a caller can point a one-off run at a
# different MG5 install. DELPHES_PATH deliberately cannot be overridden: only the
# generation toolchain is varied that way, never the simulation.
MG5_PATH=${MG5_PATH:-/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2}
DELPHES_PATH=/eos/user/l/llambrec/jetclass/delphes

## some env variables are required by the softwares
# Exported, not shell-local, because the generation tools' own child processes
# need them.
export LHAPDFCONFIG=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/lhapdf6_py3/share/LHAPDF/lhapdf.conf
export LHAPDF_DATA_PATH=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/lhapdf6_py3/share/LHAPDF
export PYTHIA8DATA=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/pythia8/share/Pythia8/xmldoc
# MG5 resolves an explicit `lhaid` through its *python* LHAPDF interface, which
# needs the extension module on PYTHONPATH and libLHAPDF.so on LD_LIBRARY_PATH.
# Without both, MG5 only warns and silently falls back to the default PDF set
# bundled in its generated proc/lib/PDFsets/, not the requested one.
export PYTHONPATH=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/lhapdf6_py3/lib64/python3.9/site-packages:$PYTHONPATH
export LD_LIBRARY_PATH=/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/lhapdf6_py3/lib:$LD_LIBRARY_PATH

## fixed configuration
GENCFG_PATH=$REPO_DIR/gen_configs

# Per-batch generation timeout and retry count, in seconds. Pythia8's shower can
# hang indefinitely on some kinematic regimes; a healthy batch takes ~1 minute,
# so 900 s leaves room for a slow-but-real batch while bounding a hung one.
GEN_TIMEOUT_SEC=${GEN_TIMEOUT_SEC:-900}
GEN_MAX_ATTEMPTS=${GEN_MAX_ATTEMPTS:-5}

# Run ./run_gen.sh (cwd: proc_base) under the timeout and retry policy above.
# Each retry re-invokes run_gen.sh, which re-samples a fresh random parameter
# draw, so a retry is a real second chance rather than the same hang again.
# `setsid` puts the attempt in its own process group so a timeout can SIGKILL
# the whole generation tree, scoped to this group and nothing else on the node.
# Returns nonzero once the attempts are exhausted; the caller tolerates a batch
# that produced no events.
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
# Stall watchdog for the batch loop, in seconds. The timeouts above can only kill
# a process that is killable; one blocked on an EOS read ignores even SIGKILL, so
# `timeout` never returns. Every legitimate step between heartbeats is bounded by
# those timeouts, so a long silence means something is stuck beyond them and the
# job should fail now rather than hold its slot for the full wall time.
STALL_TIMEOUT_SEC=${STALL_TIMEOUT_SEC:-1800}
STALL_POLL_SEC=${STALL_POLL_SEC:-60}

# Record that progress was made.
heartbeat() {
    [ -n "$HEARTBEAT_FILE" ] && touch "$HEARTBEAT_FILE"
}

# Start the background watchdog that aborts run.sh if the heartbeat goes stale.
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

# Stop the watchdog, e.g. before the unbounded final merge and copy steps.
stop_stall_watchdog() {
    [ -n "$WATCHDOG_PID" ] && kill $WATCHDOG_PID 2>/dev/null
    WATCHDOG_PID=""
    HEARTBEAT_FILE=""
}

# Host used for the direct xrootd route to EOS.
EOS_XRD_HOST=eosuser.cern.ch

# Canonical xrootd path for a path on the EOS FUSE mount, or nothing (and
# nonzero) if it is not on EOS. The FUSE-only /eos/home-<l>/ alias is rejected by
# the xrootd server, so map it back to /eos/user/<l>/.
eos_xrd_path() {
    case "$1" in
        /eos/home-?/*) echo "/eos/user/${1:10:1}/${1:12}" ;;
        /eos/user/*)   echo "$1" ;;
        *)             return 1 ;;
    esac
}

# Copy one file to EOS, retrying with backoff, and exit nonzero if it cannot be
# verified to have landed. "Landed" means the EOS *server* reports exactly as
# many bytes as the local source: the FUSE mount can report success for a write
# that later fails, leaving a silently truncated file. So for /eos paths the copy
# goes over xrootd with an end-to-end checksum and the size is read back from the
# server; the FUSE `cp` is only a fallback, for a non-EOS path or a node without
# xrootd credentials. `cp` rather than `mv` keeps the local source intact for the
# next attempt, and a partial destination is removed so failure shows up as a
# missing file rather than a corrupt one.
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

OUTPUT_PATH=$(realpath $OUTPUT_PATH)

# jetclass1/* processes use the JetClass-I label scheme (Top_*/W_*/Z_*/H_*),
# everything else the v2 scheme. Decided here because both backends label jets
# with the same code.
case "$PROC" in
    jetclass1/*) USE_V1_LABELS=true ;;
    *)           USE_V1_LABELS=false ;;
esac


# =============================================

# Create the workdir on the worker node's local scratch disk, not on EOS. All the
# heavy per-job I/O happens here and only the final output files are copied out,
# because EOS charges a network round trip per file operation and many concurrent
# jobs doing that for every intermediate file is enough to stall them all.
# _CONDOR_SCRATCH_DIR is HTCondor's per-job scratch, cleaned up on exit; the
# fallback covers a non-condor run.
SCRATCH_BASE=${_CONDOR_SCRATCH_DIR:-${TMPDIR:-/tmp}}
RANDSTR=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 10; echo)
WORKDIR=$SCRATCH_BASE/workdir_$(date +%y%m%d-%H%M%S)_${RANDSTR}_$(echo "$PROC" | sed 's/\//_/g')_$JOBNUM
mkdir -p $WORKDIR
# Clean up on any exit, not just the success path, so a failed run leaves nothing
# behind. Condor would tear down its own scratch anyway; this also covers a local
# run.
trap 'stop_stall_watchdog; rm -rf "$WORKDIR"' EXIT

cd $WORKDIR

# Backend preparation, after the workdir exists and has been entered, since a
# backend may want to put things in it.
backend_setup

# split into batches of NEVENT_GEN
nbatch=$((NEVENT / NEVENT_GEN))

# armed for the batch loop only
start_stall_watchdog

for ((i=0; i<nbatch; i++)); do

    echo "Batch: $i"
    heartbeat

    cd $WORKDIR
    if [ "$PROC_KIND" = "cmssw_fragment" ]; then
        # Nothing to generate: CMSSW does it in its own GEN step from the
        # process' fragment.py. Straight to the backend.
        backend_run_batch $i
        backend_intermediate_merge $i
        continue
    fi

    # copy genpack if not exist
    if [ ! -d "proc_base" ]; then
        mkdir proc_base
        # Retry and verify, for the same reason as copy_to_eos but in the other
        # direction: a read from the EOS mount can fail mid-copy, and an
        # unchecked failure here leaves run_gen.sh missing, so every batch
        # generates nothing while the job still exits 0 with an empty ntuple.
        # The check is "at least one file landed" rather than cp's exit code,
        # since a partially failed `cp -r` can still exit 0.
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

    # Generate this batch's events once; the backend may reconstruct them with
    # several detector configurations.
    rm -f events.hepmc
    run_gen_with_timeout $NEVENT_GEN

    # hand the batch to the backend, with cwd = $WORKDIR/proc_base and this
    # batch's events.hepmc in it
    backend_run_batch $i

    backend_intermediate_merge $i

done

stop_stall_watchdog

mkdir -p $OUTPUT_PATH/$PROC

backend_finalize
