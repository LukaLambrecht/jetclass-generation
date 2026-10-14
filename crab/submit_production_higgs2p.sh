#!/bin/bash
#
# Build and submit the two-prong Higgs signal (jetclass2/train_higgs2p) as ONE CRAB task.
#
# HOW THIS DIFFERS FROM THE QCD SUBMITTER
# ---------------------------------------
# QCD (jetclass2sb) is ten pThat bins that must carry EQUAL events per bin to keep the
# jet pT spectrum flat. The signal is a single process, so there is no mixture to
# preserve and no per-bin table - just one task.
#
# It is also a hepmc process, not a CMSSW fragment: MadGraph5 generates an LHE for a
# randomly drawn (Higgs mass, pT_min) point from the 4900-point grid in
# gen_configs/jetclass2/train_higgs2p/mg5_params.dat, Pythia8 showers it to
# events.hepmc, and only then does CMSSW reconstruct. run_gen.sh re-draws that point on
# every batch, so the scan is sampled independently throughout the production.
#
# Consequences handled by run_job.sh, not here:
#   * generation runs in an EL9 container, CMSSW in EL7 - MG5 is built against glibc
#     2.34 and will not start under SLC7;
#   * MG5 itself (~363 MB compressed) is fetched per job from
#     crab/make_mg5_tarball.sh's staged tarball, since it is far over the CRAB sandbox
#     limit and the CVMFS copy is a different major version.
#
# SIZING: 4000 jobs x 500 events = 2,000,000 events. The 630k trial yielded 32.9%
# non-QCD ("useful") jets, so this targets roughly 1.5M useful jets.
#
# RUNTIME IS THE LEAST CERTAIN PART. No signal-specific per-event cost was ever
# measured - the 630k trial's condor records are gone - so 500 events/job is an
# estimate, not a measurement. maxJobRuntimeMin is therefore set generously (1200 min
# = 20 h, against CRAB's 2800 max) rather than the 900 the QCD tasks use. Watch the
# first completions: if jobs come in far under, later rounds can use bigger jobs and
# fetch MG5 fewer times.
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
# The 2026-10-13 round requested 2500 MB on 1 core and lost 23% of its failures to
# exit 50660 (HTCondor memory kills): measured 1631 MB average but 3958 MB peak over
# 1827 failed jobs. The early "~1.4 GB peak" came from a handful of local runs and was
# simply not representative. CRAB refuses more than 3000 MB for a 1-core task, so the
# peak cannot be covered on one core - hence 2 cores. The chain is single-threaded, so
# the second core buys the memory allowance, not speed.
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
# Re-check this list occasionally: it reflects site configuration, which changes.
DEFAULT_BLACKLIST="T2_IT_Pisa,T2_AT_Vienna,T2_US_MIT,T2_BR_SPRACE,T2_LB_HPC4L"
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
