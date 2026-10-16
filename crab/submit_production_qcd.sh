#!/bin/bash
#
# Build and submit the ten QCD pThat bins as ten CRAB tasks (jetclass2sb).
#
# Signal (jetclass2/train_higgs2p) is NOT handled here - it is a hepmc process needing
# MadGraph5+Pythia8 before CMSSW; see crab/README.md.
#
# THE INVARIANT: njobs x nev/job = 200,000 for EVERY bin. That equal events-per-bin is
# what makes the jet pT spectrum flat (see gen_configs/jetclass2sb/README.md). Job size
# varies per bin only because per-event cost rises with pThat; njobs moves the opposite
# way to compensate. Change one without the other and you skew the mixture.
#
# SIZING: p90 job time ~7-8 h, from the marginal per-event cost measured on the
# completed 2026-10-09 lxplus round (its p90 job times with the fixed costs removed,
# so they stay valid at a different job size).
#
# WHY 8 h AND NOT 4 h. Shorter jobs are tempting now that CRAB makes job count cheap,
# but the ~1.67 GB conditions fetch is per JOB, not per event:
#
#     target p90   jobs     CPU        conditions transfer
#     4 h          14,250   37,014 h   23.8 TB
#     8 h           7,000   35,157 h   11.7 TB      <- this table
#
# 4 h costs ~5% more CPU (the ~600 s of fixed overhead - scram build, conditions fetch,
# cmsRun startups - spread over fewer events) AND doubles the pull from eospublic, a
# public service. CRAB also retries failed jobs automatically, which is most of what
# short jobs would otherwise buy. 8 h is additionally what CRAB itself aims for.
#
# REVISIT IF the site probe (site-probe/) comes back mostly CVMFS_OK: those sites fetch
# nothing, the transfer argument disappears, and 4 h costs only the 5% CPU. Then halve
# every nev/job and double every njobs in TABLE below - both, or the mixture skews.
#
# NOTE: there is no checkpointing on the CRAB path (run_job.sh merges at the end), so a
# killed job loses its batches. CRAB's automatic retries replace that, which is fine
# unless jobs are SYSTEMATICALLY over the limit - another reason not to push length.
#
# Expected: 7,000 jobs, 2,000,000 events, ~3.89M jets, ~35,000 CPU-h, ~11.7 TB fetched
# from eospublic (zero for jobs landing on sites that mount the conditions on CVMFS).
#
# USAGE
#   voms-proxy-init -voms cms -valid 192:00
#   ./submit_production.sh --dry-run            # print every command, run nothing
#   ./submit_production.sh --bins 470to600      # one bin, e.g. to test first
#   ./submit_production.sh
set -u

THISDIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
WORKDIR=${WORKDIR:-$THISDIR/production}
# ONE base for all ten bins. CRAB appends <family>/<proc>/<timestamp>/<counter>/ under
# it, so the result is laid out exactly like a local production and the validation
# scripts read it with no changes. T3_CH_CERNBOX maps /store/user/<user> to
# /eos/user/<initial>/<user>.
OUTLFN=${OUTLFN:-/store/user/$USER/jetclass/output_jetclass2sb_4M/}
SCALE=1            # multiplies njobs; keeps the invariant if you scale ALL bins
BINS=""
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
RUNTIME_MIN=900    # 15 h: above the ~10 h a slow 8 h job reaches, below the 24 h cap.
                   # Lower values match more sites during matchmaking; CRAB's own
                   # default is 1315 (21.9 h), which some sites will not accept.
# MEMORY/CORES: the 2026-10-13 round requested 2500 MB on 1 core and lost 11% of its
# failures to exit 50660, HTCondor killing jobs for memory. Measured across the ten QCD
# tasks and the signal task: 1616-1849 MB average, 3958 MB peak. CRAB refuses more than
# 3000 MB for a 1-core task, so the peak simply cannot be covered on one core - hence
# 2 cores and 4000 MB. The chain is single-threaded, so the second core is bought for
# its memory allowance, not for speed.
MEMORY=4000
CORES=2
DRYRUN=false

while [ $# -gt 0 ]; do
    case "$1" in
        --bins)      BINS=$2; shift 2 ;;
        --scale)     SCALE=$2; shift 2 ;;
        --whitelist) WHITELIST=$2; shift 2 ;;
        --blacklist) BLACKLIST=$2; shift 2 ;;
        --outlfn)    OUTLFN=$2; shift 2 ;;
        --runtime-min) RUNTIME_MIN=$2; shift 2 ;;
        --workdir)   WORKDIR=$2; shift 2 ;;
        --dry-run)   DRYRUN=true; shift ;;
        -h|--help)   sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

# bin  njobs  nev/job  batch     (njobs x nev/job = 200,000 for every row)
TABLE="\
170to300    400 500 250
300to470    500 400 200
470to600    500 400 200
600to800    500 400 200
800to1000   625 320 160
1000to1400  625 320 160
1400to1800  800 250 125
1800to2400  800 250 125
2400to3200 1000 200 100
3200toInf  1250 160  80"

run() { echo "+ $*"; if [ "$DRYRUN" = false ]; then "$@"; fi; }

if [ "$DRYRUN" = false ] && ! voms-proxy-info -exists -valid 0:10 >/dev/null 2>&1; then
    echo "ERROR: no valid proxy. Run:  voms-proxy-init -voms cms -valid 192:00" >&2
    exit 1
fi

tj=0
echo "=================================================================="
echo " jetclass2sb QCD production: 10 bins, scale x$SCALE, dry-run=$DRYRUN"
echo " work area: $WORKDIR"
echo " output   : $OUTLFN"
echo "=================================================================="
run mkdir -p "$WORKDIR"
while read -r bin nj nev batch; do
    [ -z "$bin" ] && continue
    if [ -n "$BINS" ] && ! echo ",$BINS," | grep -q ",$bin,"; then continue; fi
    nj=$(( nj * SCALE ))
    tj=$(( tj + nj ))
    echo
    echo "---- QCD_PT-$bin : $nj jobs x $nev events (batch $batch) = $(( nj * nev )) events ----"
    # Work directory named like the fragment and the output folder (QCD_PT-<bin>)
    # rather than the bare bin, so `ls production/` is self-describing. NOTE: runs
    # submitted before 2026-10-13 used the bare name, so they will not be recognised
    # as "already built" by a re-run - that is intended, they are separate rounds.
    d=$WORKDIR/QCD_PT-$bin
    extra=""
    [ -n "$WHITELIST" ] && extra="--whitelist $WHITELIST"
    [ -n "$BLACKLIST" ] && extra="$extra --blacklist $BLACKLIST"
    if [ -d "$d" ]; then echo "  (already built, skipping build)"; else
        run python3 "$THISDIR/build_simpack.py" --proc "jetclass2sb/QCD_PT-$bin" \
            --njobs "$nj" --nevents-per-job "$nev" --batch-size "$batch" \
            --runtime-min "$RUNTIME_MIN" --request-name "jetclass2sb_QCD_PT_$bin" \
            --memory "$MEMORY" --cores "$CORES" \
            --outlfn "$OUTLFN" $extra -o "$d"
    fi
    echo "+ (cd $d && ./crab_submit.sh)"
    if [ "$DRYRUN" = false ]; then ( cd "$d" && ./crab_submit.sh ) || echo "  SUBMIT FAILED: $bin"; fi
done <<< "$TABLE"

echo
echo "=================================================================="
echo " total jobs: $tj"
echo " monitor with: crab status -d $WORKDIR/<bin>/crab_logs/crab_jetclass2sb_QCD_PT_<bin>"
echo "=================================================================="
