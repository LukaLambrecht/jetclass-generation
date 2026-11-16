#!/bin/bash
#
# Build and submit the two-prong Higgs signal (jetclass2/train_higgs2p) as ONE CRAB task.
#
# Unlike the QCD submitter, which runs ten pThat bins that must carry equal events per
# bin to keep the jet pT spectrum flat, the signal is a single process: no mixture to
# preserve, no per-bin table, one task.
#
# It is also a hepmc process, not a CMSSW fragment: MadGraph5 generates an LHE for a
# randomly drawn mass point from the grid in the process' mg5_params.dat, Pythia8
# showers it to events.hepmc, and only then does CMSSW reconstruct. run_gen.sh draws a
# fresh point every batch, so the scan is sampled independently throughout.
#
# Two consequences, both handled by run_job.sh rather than here:
#   * generation runs in an EL9 container and CMSSW in EL7, since MG5 will not start
#     under SLC7;
#   * MG5 is fetched per job from the tarball crab/make_mg5_tarball.sh stages, being
#     far over the CRAB sandbox limit while the CVMFS copy is a different major
#     version.
#
# Sized at 4000 jobs x 500 events, targeting roughly 1.5M useful (non-QCD) jets.
#
# Runtime is the least certain part: no signal-specific per-event cost has been
# measured, so 500 events per job is an estimate. maxJobRuntimeMin is therefore set
# generously rather than at the value the QCD tasks use. Watch the first completions;
# if jobs come in well under, later rounds can use bigger jobs and fetch MG5 fewer
# times.
#
# USAGE
#   voms-proxy-init -voms cms -valid 192:00
#   ./submit_production_higgs2p.sh --dry-run      # print every command, run nothing
#   ./submit_production_higgs2p.sh
set -u

THISDIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKDIR=${WORKDIR:-$THISDIR/production}          # shared with the QCD submitter
OUTLFN=${OUTLFN:-/store/user/$USER/jetclass/output_jetclass2_4M/}
PROC=jetclass2/train_higgs2p
NJOBS=4000
NEVENTS=500
BATCH=250            # 2 batches per job, as for QCD
RUNTIME_MIN=1200     # 20 h; see "RUNTIME IS THE LEAST CERTAIN PART" above
# The chain averages well under 2 GB but peaks near 4 GB, and CRAB refuses more than
# 3000 MB for a 1-core task, so the peak cannot be covered on one core - hence two.
# The chain is single-threaded, so the second core buys the memory allowance, not
# speed; a CPU efficiency near 50% is expected.
MEMORY=4000
CORES=2
WHITELIST=""
# Sites that cannot run this chain, to be skipped by default.
#
# Our run_job.sh launches a container (cmssw-el7, and cmssw-el9 for hepmc processes)
# INSIDE the apptainer container CRAB already runs the job in. Some sites do not allow
# that nesting - the inner launch dies instantly with
#   FATAL: container creation failed: ... fuse-overlayfs exited: fuse: device not found
# and the job fails with exit code 50115 (BadFWJRXML) after a couple of minutes,
# having done no work.
#
# Measured on the 2026-10-13 signal task (596 failures out of 4000, 592 of them here):
#   T2_IT_Pisa     291 failed /   0 ran   100%
#   T2_AT_Vienna    19 failed /   0 ran   100%
#   T2_LB_HPC4L     12 failed /   0 ran   100%
#   T2_BR_SPRACE    97 failed /   4 ran    96%
#   T2_US_MIT      173 failed / 218 ran    44%  (per-node, not uniform - blacklisted
#                                               anyway, the waste outweighs the gain)
# Every other site had ZERO such failures.
#
#   T3_US_PuertoRico  added 2026-10-14, from the round submitted that morning: all
#                     three retries of a job landed there and died identically with
#                     "fuse-overlayfs exited: fuse: device not found" before any work
#                     started. Note this reports as 50115 BadFWJRXML, NOT as a
#                     container error - run_job.sh writes the job report as its last
#                     act, so any early death looks like a missing report. Read 50115
#                     as "the script failed somewhere" and go to the job log for the
#                     real cause.
#   T2_US_UCSD        added 2026-10-16 on the basis of the previous round's failures;
#                     same symptom as the others.
#
# Re-check this list occasionally: it reflects site configuration, which changes.
DEFAULT_BLACKLIST="T2_IT_Pisa,T2_AT_Vienna,T2_US_MIT,T2_BR_SPRACE,T2_LB_HPC4L,T3_US_PuertoRico,T2_US_UCSD"
BLACKLIST=${BLACKLIST:-$DEFAULT_BLACKLIST}
DRYRUN=false

while [ $# -gt 0 ]; do
    case "$1" in
        --njobs)       NJOBS=$2; shift 2 ;;
        --nevents)     NEVENTS=$2; shift 2 ;;
        --batch-size)  BATCH=$2; shift 2 ;;
        --outlfn)      OUTLFN=$2; shift 2 ;;
        --whitelist)   WHITELIST=$2; shift 2 ;;
        --blacklist)   BLACKLIST=$2; shift 2 ;;
        --runtime-min) RUNTIME_MIN=$2; shift 2 ;;
        --workdir)     WORKDIR=$2; shift 2 ;;
        --dry-run)     DRYRUN=true; shift ;;
        -h|--help)     sed -n '2,40p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

run() { echo "+ $*"; if [ "$DRYRUN" = false ]; then "$@"; fi; }

if [ "$DRYRUN" = false ] && ! voms-proxy-info -exists -valid 0:10 >/dev/null 2>&1; then
    echo "ERROR: no valid proxy. Run:  voms-proxy-init -voms cms -valid 192:00" >&2
    exit 1
fi

MG5_TARBALL=/eos/user/${USER:0:1}/$USER/jetclass/crab_inputs/MG5_aMC_v3_7_2.tar.gz
if [ ! -s "$MG5_TARBALL" ]; then
    echo "ERROR: MG5 tarball not found at $MG5_TARBALL" >&2
    echo "       every job fetches it; stage it first with:  ./make_mg5_tarball.sh" >&2
    exit 1
fi

echo "=================================================================="
echo " jetclass2/train_higgs2p signal production"
echo "   jobs    : $NJOBS x $NEVENTS events (batch $BATCH) = $(( NJOBS * NEVENTS )) events"
echo "   work    : $WORKDIR/train_higgs2p"
echo "   output  : $OUTLFN"
echo "   MG5     : $MG5_TARBALL ($(du -h "$MG5_TARBALL" 2>/dev/null | cut -f1), fetched per job)"
echo "   dry-run : $DRYRUN"
echo "=================================================================="

run mkdir -p "$WORKDIR"
d=$WORKDIR/train_higgs2p
extra=""
[ -n "$WHITELIST" ] && extra="--whitelist $WHITELIST"
[ -n "$BLACKLIST" ] && extra="$extra --blacklist $BLACKLIST"
if [ -d "$d" ]; then
    echo "  (already built, skipping build)"
else
    run python3 "$THISDIR/build_simpack.py" --proc "$PROC" \
        --njobs "$NJOBS" --nevents-per-job "$NEVENTS" --batch-size "$BATCH" \
        --runtime-min "$RUNTIME_MIN" --memory "$MEMORY" --cores "$CORES" \
        --request-name "jetclass2_train_higgs2p" \
        --outlfn "$OUTLFN" $extra -o "$d"
fi
echo "+ (cd $d && ./crab_submit.sh)"
if [ "$DRYRUN" = false ]; then
    ( cd "$d" && ./crab_submit.sh ) || { echo "  SUBMIT FAILED"; exit 1; }
fi

echo
echo "=================================================================="
echo " monitor with:"
echo "   crab status -d $d/crab_logs/crab_jetclass2_train_higgs2p"
echo "   or crab/monitoring/monitor_crab_jobs.sh (covers every task in production/)"
echo "=================================================================="
