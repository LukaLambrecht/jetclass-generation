#!/bin/bash
#
# Submit the two-prong Higgs signal (jetclass2/train_higgs2p) to lxplus HTCondor.
#
# This is the BACKUP ROUTE to crab/submit_production_higgs2p.sh. Same chain, same
# output schema - only the batch system differs.
#
# HOW THIS DIFFERS FROM THE QCD SUBMITTER: QCD is ten pThat bins that must carry equal
# events per bin to keep the jet pT spectrum flat. The signal is a single process, so
# there is no mixture to preserve and no per-bin table.
#
# IT IS ALSO A hepmc PROCESS, NOT A CMSSW FRAGMENT, and that is what makes it need more
# than the repo: MadGraph5 generates an LHE for a randomly drawn (Higgs mass, pT_min)
# point from the 4900-point grid in gen_configs/jetclass2/train_higgs2p/mg5_params.dat,
# Pythia8 showers it to events.hepmc, and only then does CMSSW reconstruct. So unlike
# the QCD submitter, THIS ONE NEEDS AN MG5 INSTALL - see INSTALL.md steps 2-3, and set
# MG5_PATH below or in the environment.
#
# SIZING: 4000 jobs x 500 events = 2,000,000 events. The 630k trial yielded 32.9%
# non-QCD ("useful") jets, so this targets roughly 1.5M useful jets. Runtime per job
# was never measured directly, so the default flavour is `tomorrow` (24 h) to be safe.
#
# USAGE
#   ./submit_production_higgs2p.sh --dry-run
#   MG5_PATH=/path/to/MG5_aMC_v3_7_2 ./submit_production_higgs2p.sh
set -u

THISDIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(dirname "$THISDIR")
OUTPUT=${OUTPUT:-/eos/user/${USER:0:1}/$USER/jetclass/output_jetclass2_4M}
CONDORDIR=${CONDORDIR:-$REPO/condor_jetclass2_higgs2p}
MAXRUNNING=${MAXRUNNING:-400}
MAXMATERIALIZE=${MAXMATERIALIZE:-80}
JOBFLAVOUR=${JOBFLAVOUR:-tomorrow}
NJOBS=4000
NEVENTS=500
BATCH=250
DRYRUN=false

while [ $# -gt 0 ]; do
    case "$1" in
        --njobs)       NJOBS=$2; shift 2 ;;
        --nevents)     NEVENTS=$2; shift 2 ;;
        --batch-size)  BATCH=$2; shift 2 ;;
        --output)      OUTPUT=$2; shift 2 ;;
        --max-running) MAXRUNNING=$2; shift 2 ;;
        --jobflavour)  JOBFLAVOUR=$2; shift 2 ;;
        --condordir)   CONDORDIR=$2; shift 2 ;;
        --dry-run)     DRYRUN=true; shift ;;
        -h|--help)     sed -n '2,26p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

run() { echo "+ $*"; if [ "$DRYRUN" = false ]; then "$@"; fi; }

# The generation step needs a working MG5 install; fail now with a pointer rather than
# letting 4000 jobs die one by one on a missing binary.
MG5=${MG5_PATH:-/eos/user/${USER:0:1}/$USER/jetclass/MG5_aMC_v3_7_2}
if [ ! -x "$MG5/bin/mg5_aMC" ]; then
    echo "ERROR: no MG5 install at $MG5 (looked for bin/mg5_aMC)." >&2
    echo "       jetclass2/* are hepmc processes: MadGraph5 + Pythia8 run before CMSSW." >&2
    echo "       Install it (INSTALL.md steps 2-3) and pass MG5_PATH=/path/to/MG5_aMC_vX.Y.Z." >&2
    exit 1
fi
if [ ! -x "$MG5/HEPTools/MG5aMC_PY8_interface/MG5aMC_PY8_interface" ]; then
    echo "ERROR: $MG5 has no MG5aMC_PY8_interface under HEPTools/." >&2
    echo "       This is the classic bin/HEPTools-vs-HEPTools layout problem - see" >&2
    echo "       INSTALL.md step 2, which explains the symlink fix." >&2
    exit 1
fi

echo "=================================================================="
echo " jetclass2/train_higgs2p signal production on lxplus HTCondor"
echo "   jobs        : $NJOBS x $NEVENTS events (batch $BATCH) = $(( NJOBS * NEVENTS )) events"
echo "   output      : $OUTPUT"
echo "   submit files: $CONDORDIR"
echo "   MG5         : $MG5"
echo "   concurrency : $MAXRUNNING   flavour: $JOBFLAVOUR"
echo "=================================================================="
echo
echo "NOTE: submitting from EOS needs the eossubmit schedd:"
echo "        module load lxbatch/eossubmit"
echo

run python3 "$REPO/run_condor_loop.py" --backend fullsim \
    --procs jetclass2/train_higgs2p \
    --njobs "$NJOBS" --nevents-per-job "$NEVENTS" --batch-size "$BATCH" \
    --output-path "$OUTPUT" --jobflavour "$JOBFLAVOUR" \
    --max-running "$MAXRUNNING" --max-materialize "$MAXMATERIALIZE" \
    --extra-env "MG5_PATH=$MG5" \
    -o "$CONDORDIR"

echo
echo "=================================================================="
echo " monitor with: condor_q   (module load lxbatch/eossubmit first)"
echo "=================================================================="
