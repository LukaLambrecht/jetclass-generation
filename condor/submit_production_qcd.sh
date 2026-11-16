#!/bin/bash
#
# Submit the ten QCD pThat bins (jetclass2sb) to lxplus HTCondor.
#
# The alternative to crab/submit_production_qcd.sh: same physics, same chain, same
# output schema, only a different batch system. Use it when CRAB is unavailable or when
# dedicated lxbatch resources are preferable to the grid.
#
# The invariant: njobs x nev/job must be the same for every bin. Equal events per bin is
# what makes the jet pT spectrum flat. Job size varies per bin because the per-event
# cost rises with pThat, and njobs moves the opposite way to compensate; change one
# without the other and the mixture is skewed.
#
# Sized for a p90 job time of 7-8 h, so the default flavour is `tomorrow` (24 h);
# `workday` (8 h) would lose the tail.
#
# Needs nothing beyond the repo: the fullsim backend wants only CVMFS and apptainer.
#
# USAGE
#   ./submit_production_qcd.sh --dry-run      # print every command, run nothing
#   ./submit_production_qcd.sh --bins 470to600
#   ./submit_production_qcd.sh
set -u

THISDIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(dirname "$THISDIR")
OUTPUT=${OUTPUT:-/eos/user/${USER:0:1}/$USER/jetclass/output_jetclass2sb_4M}
CONDORDIR=${CONDORDIR:-$REPO/condor_jetclass2sb}
MAXRUNNING=${MAXRUNNING:-400}
MAXMATERIALIZE=${MAXMATERIALIZE:-80}
JOBFLAVOUR=${JOBFLAVOUR:-tomorrow}
SCALE=1
BINS=""
DRYRUN=false

while [ $# -gt 0 ]; do
    case "$1" in
        --bins)        BINS=$2; shift 2 ;;
        --scale)       SCALE=$2; shift 2 ;;
        --output)      OUTPUT=$2; shift 2 ;;
        --max-running) MAXRUNNING=$2; shift 2 ;;
        --jobflavour)  JOBFLAVOUR=$2; shift 2 ;;
        --condordir)   CONDORDIR=$2; shift 2 ;;
        --dry-run)     DRYRUN=true; shift ;;
        -h|--help)     sed -n '2,28p' "$0"; exit 0 ;;
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

echo "=================================================================="
echo " jetclass2sb QCD production on lxplus HTCondor"
echo "   output      : $OUTPUT"
echo "   submit files: $CONDORDIR"
echo "   concurrency : $MAXRUNNING (global, across all clusters)"
echo "   flavour     : $JOBFLAVOUR"
echo "   scale       : x$SCALE"
echo "=================================================================="
echo
echo "NOTE: submitting from EOS needs the eossubmit schedd:"
echo "        module load lxbatch/eossubmit"
echo

tj=0
while read -r bin nj nev batch; do
    [ -z "$bin" ] && continue
    if [ -n "$BINS" ] && ! echo ",$BINS," | grep -q ",$bin,"; then continue; fi
    nj=$(( nj * SCALE )); tj=$(( tj + nj ))
    echo "---- QCD_PT-$bin : $nj jobs x $nev events (batch $batch) = $(( nj * nev )) events ----"
    run python3 "$REPO/run_condor_loop.py" --backend fullsim \
        --procs "jetclass2sb/QCD_PT-$bin" \
        --njobs "$nj" --nevents-per-job "$nev" --batch-size "$batch" \
        --output-path "$OUTPUT" --jobflavour "$JOBFLAVOUR" \
        --max-running "$MAXRUNNING" --max-materialize "$MAXMATERIALIZE" \
        -o "$CONDORDIR"
done <<< "$TABLE"

echo
echo "=================================================================="
echo " total jobs: $tj"
echo " monitor with: condor_q   (module load lxbatch/eossubmit first)"
echo "=================================================================="
