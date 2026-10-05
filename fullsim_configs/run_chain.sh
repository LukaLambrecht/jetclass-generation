#!/bin/bash
# The CMSSW side of the fullsim backend. Runs INSIDE the container (see
# backends/fullsim.sh, which is what launches it); sets up the CMSSW environment
# itself, so it can also be run by hand for debugging.
#
#   run_chain.sh setup       - write the three cmsRun configs and build the ntuplizer (once per job)
#   run_chain.sh batch <i>   - GEN,SIM -> DIGI,L1,HLT -> RECO -> ntuple, for one batch
#
# Configuration, all via the environment (backends/fullsim.sh sets these):
#   FS_WORK       work directory; holds cfg/ and batch_<i>/            (required)
#   FS_CFGSRC     the repo's fullsim_configs directory                 (required)
#   FS_ANASRC     directory holding makeNtuplesFullSim.cc + its headers (required)
#   FS_NEVENT     events per batch, -1 for "all that are in the HepMC file" (default -1)
#   FS_KEEP       "true" to keep the (large) intermediate CMSSW files   (default false)
#   NT_*          passed through to the ntuplizer, see makeNtuplesFullSim.cc's main()
#   FULLSIM_CMSSW_DIR, FULLSIM_SCRAM_ARCH, FULLSIM_CONDDB   see below
#
# Every step is skipped if its output is already there, so a batch that failed
# late (or a job that is retried) does not redo the expensive steps. Within a
# job that only matters for a retry by hand; it matters a lot when debugging.
set -u

FS_NEVENT=${FS_NEVENT:--1}
FS_KEEP=${FS_KEEP:-false}
CMSSW_DIR=${FULLSIM_CMSSW_DIR:-/cvmfs/cms.cern.ch/slc7_amd64_gcc700/cms/cmssw/CMSSW_10_6_30}
export SCRAM_ARCH=${FULLSIM_SCRAM_ARCH:-slc7_amd64_gcc700}
export FULLSIM_CONDDB=${FULLSIM_CONDDB:-/cvmfs/cms-opendata-conddb.cern.ch}

for v in FS_WORK FS_CFGSRC FS_ANASRC; do
    if [ -z "${!v:-}" ]; then echo "ERROR: $v is not set" >&2; exit 2; fi
done

# ---- CMSSW environment ----
if [ ! -d "$CMSSW_DIR" ]; then
    echo "ERROR: CMSSW not found at $CMSSW_DIR (set FULLSIM_CMSSW_DIR)" >&2
    exit 2
fi
source /cvmfs/cms.cern.ch/cmsset_default.sh >/dev/null 2>&1 || {
    echo "ERROR: could not source cmsset_default.sh - is /cvmfs/cms.cern.ch available?" >&2; exit 2; }
cd "$CMSSW_DIR"
eval "$(scram runtime -sh)" || { echo "ERROR: scram runtime failed in $CMSSW_DIR" >&2; exit 2; }

CFGDIR=$FS_WORK/cfg
GT=$(python -c "import sys; sys.path.insert(0,'$FS_CFGSRC'); import patch_cond; print(patch_cond.GT)")
BEAMSPOT=$(python -c "import sys; sys.path.insert(0,'$FS_CFGSRC'); import patch_cond; print(patch_cond.BEAMSPOT_NAME)")

# Appends the patch block that turns a bare cmsDriver config into one that runs
# on open conditions (and, for step 1, on our own HepMC input).
append_patch () {
    local cfg=$1; shift
    {
        echo ""
        echo "# ---- jetclass-generation fullsim backend: see fullsim_configs/ ----"
        echo "import sys"
        echo "sys.path.insert(0, '$FS_CFGSRC')"
        echo "import patch_cond"
        for line in "$@"; do echo "$line"; done
    } >> "$cfg"
}

do_setup () {
    mkdir -p "$CFGDIR"
    cd "$CFGDIR"

    if [ ! -s gensim_cfg.py ]; then
        # The fragment name is required by cmsDriver but its generator module is
        # removed again by patch_gen (we read our own HepMC file instead); it
        # only has to be a GEN fragment that exists in the release.
        cmsDriver.py QCD_Pt_600_800_13TeV_TuneCUETP8M1_cfi --mc --eventcontent FEVTDEBUG \
            --datatier GEN-SIM --conditions "$GT" --beamspot "$BEAMSPOT" --step GEN,SIM \
            --geometry DB:Extended --era Run2_2018 --python_filename gensim_cfg.py \
            --fileout file:gensim.root -n "$FS_NEVENT" --no_exec > cmsdriver_gensim.log 2>&1 \
            || { echo "ERROR: cmsDriver (GEN,SIM) failed, see $CFGDIR/cmsdriver_gensim.log" >&2; return 1; }
        append_patch gensim_cfg.py \
            "import patch_gen" \
            "process = patch_gen.apply(process, 'events.hepmc')" \
            "process = patch_cond.apply(process)" \
            "process = patch_cond.set_beamspot(process)"
    fi

    if [ ! -s hlt_cfg.py ]; then
        cmsDriver.py --filein file:gensim.root --fileout file:hlt.root --mc \
            --eventcontent FEVTDEBUGHLT --datatier GEN-SIM-RAW --conditions "$GT" \
            --step DIGI,L1,DIGI2RAW,HLT:GRun --geometry DB:Extended --era Run2_2018 \
            --python_filename hlt_cfg.py -n "$FS_NEVENT" --no_exec > cmsdriver_hlt.log 2>&1 \
            || { echo "ERROR: cmsDriver (DIGI,L1,HLT) failed, see $CFGDIR/cmsdriver_hlt.log" >&2; return 1; }
        append_patch hlt_cfg.py \
            "import patch_hlt" \
            "process = patch_cond.apply(process)" \
            "process = patch_cond.prune_hlt(process)" \
            "process = patch_hlt.add_hlt_jets(process)" \
            "process = patch_cond.set_beamspot(process)"
    fi

    if [ ! -s reco_cfg.py ]; then
        cmsDriver.py --filein file:hlt.root --fileout file:reco.root --mc \
            --eventcontent AODSIM --datatier AODSIM --conditions "$GT" \
            --step RAW2DIGI,L1Reco,RECO --geometry DB:Extended --era Run2_2018 \
            --python_filename reco_cfg.py -n "$FS_NEVENT" --no_exec > cmsdriver_reco.log 2>&1 \
            || { echo "ERROR: cmsDriver (RECO) failed, see $CFGDIR/cmsdriver_reco.log" >&2; return 1; }
        append_patch reco_cfg.py \
            "import patch_hlt" \
            "process = patch_cond.apply(process)" \
            "process = patch_cond.set_beamspot(process)" \
            "process = patch_hlt.keep_hlt_products(process)"
    fi

    if [ ! -x "$CFGDIR/makeNtuplesFullSim" ]; then
        bash "$FS_ANASRC/build.sh" "$CFGDIR/makeNtuplesFullSim" "$FS_ANASRC" > "$CFGDIR/build.log" 2>&1 \
            || { echo "ERROR: building the ntuplizer failed, see $CFGDIR/build.log" >&2;
                 tail -20 "$CFGDIR/build.log" >&2; return 1; }
    fi
    echo "SETUP_OK"
}

run_step () {
    local name=$1 out=$2
    if [ -s "$out" ]; then
        echo "  $name: $out exists - skipping"
        return 0
    fi
    local t0=$(date +%s)
    cmsRun "$CFGDIR/${name}_cfg.py" > "${name}.log" 2>&1
    local rc=$?
    echo "  $name: rc=$rc ($(( $(date +%s) - t0 ))s)"
    if [ $rc -ne 0 ]; then
        # the one line that actually says what went wrong, out of a ~10k-line log
        grep -m1 -A8 "Begin Fatal Exception" "${name}.log" | sed -n '2,8p' | cut -c1-160 >&2
    fi
    return $rc
}

do_batch () {
    local i=$1
    local bdir=$FS_WORK/batch_$i
    mkdir -p "$bdir"
    cd "$bdir"
    if [ ! -s events.hepmc ]; then
        echo "ERROR: $bdir/events.hepmc is missing - nothing to reconstruct" >&2
        return 1
    fi
    run_step gensim gensim.root || return 1
    run_step hlt hlt.root || return 1
    run_step reco reco.root || return 1

    local t0=$(date +%s)
    "$CFGDIR/makeNtuplesFullSim" \
        in=reco.root out=ntuple.root \
        jets="${NT_JETS:-ak8PFJetsCHS}" hltjets="${NT_HLTJETS:-hltAK8PFJets}" \
        qcdlabel="${NT_QCDLABEL:-true}" v1labels="${NT_V1LABELS:-false}" \
        dohlt="${NT_DOHLT:-true}" debug="${NT_DEBUG:-false}" \
        keepgenparticles="${NT_KEEPGENPARTICLES:-false}" \
        keepauxgenparticles="${NT_KEEPAUXGENPARTICLES:-false}" \
        keepgenjet="${NT_KEEPGENJET:-false}" \
        jetptmin="${NT_JETPTMIN:-200}" jetetamax="${NT_JETETAMAX:-2.4}" > ntuple.log 2>&1
    local rc=$?
    echo "  ntuple: rc=$rc ($(( $(date +%s) - t0 ))s) $(grep -m1 '^\*\* Written' ntuple.log || true)"
    if [ $rc -ne 0 ]; then
        tail -20 ntuple.log >&2
        return 1
    fi
    if [ "$FS_KEEP" != "true" ]; then
        # these are ~2.5 MB/event each and nothing downstream needs them
        rm -f gensim.root hlt.root reco.root
    fi
    echo "BATCH_OK $i"
}

case "${1:-}" in
    setup) do_setup ;;
    batch) do_batch "${2:?usage: run_chain.sh batch <index>}" ;;
    *) echo "usage: run_chain.sh setup | run_chain.sh batch <index>" >&2; exit 2 ;;
esac
