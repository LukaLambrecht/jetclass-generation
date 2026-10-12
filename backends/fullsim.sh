#!/bin/bash
# FullSim backend for run.sh: CMS full simulation, reconstruction and HLT in
# CMSSW, from the SAME generated events (gen_configs/, events.hepmc) the Delphes
# backend reconstructs, and writing the SAME ntuple schema.
#
# Uses only openly available software and conditions - no CERN account, no CMS
# membership - so it can in principle run anywhere; see fullsim_configs/README.md
# for where each ingredient comes from and what the remaining caveats are (no
# pile-up, 2018 design conditions).
#
# BACKEND_OPTS (run.sh arg 6):
#   offline+hlt   (default) one combined ntuple per jet: the offline AK8 jet and
#                 its matched HLT AK8 jet, i.e. the same row structure as the
#                 Delphes "onlyFatJet+onlyFatJetHLT" card pair
#   offline       offline jets only; the hlt_* branches exist but are empty /
#                 hlt_matched=false (the HLT step still RUNS - the RECO step
#                 needs its RAW output - so this saves ntuple size, not CPU)
#
# Per batch: GEN,SIM (from events.hepmc) -> DIGI,L1,DIGI2RAW,HLT:GRun (+ the
# unconditional AK8/PF-vertex paths) -> RAW2DIGI,L1Reco,RECO -> ntuple. The three
# CMSSW steps run inside a container (the open-data CMSSW_10_6_30 image), because
# they need an SLC7 userland; everything else runs on the host as usual.
#
# Cost, measured without pile-up: ~2 min/event in total (GEN,SIM ~70 s/event,
# DIGI+L1+HLT ~30 s/event, RECO ~38 s/event for 2-event test batches), i.e.
# roughly three orders of magnitude more than Delphes. Size the jobs accordingly.

BACKEND_DEFAULT_OPTS=offline+hlt

# All overridable, so this can be pointed at a local copy of any of it (which is
# the whole point of the open-data route - none of these needs privileged access):
#   the container image holding an SLC7 userland + CMSSW
FULLSIM_CONTAINER=${FULLSIM_CONTAINER:-/cvmfs/unpacked.cern.ch/registry.hub.docker.com/cmsopendata/cmssw_10_6_30-slc7_amd64_gcc700:latest}
#   the CMSSW release to use inside it
FULLSIM_CMSSW_DIR=${FULLSIM_CMSSW_DIR:-/cvmfs/cms.cern.ch/slc7_amd64_gcc700/cms/cmssw/CMSSW_10_6_30}
FULLSIM_SCRAM_ARCH=${FULLSIM_SCRAM_ARCH:-slc7_amd64_gcc700}
#   the open condition databases (see fullsim_configs/README.md)
FULLSIM_CONDDB=${FULLSIM_CONDDB:-/cvmfs/cms-opendata-conddb.cern.ch}
#   directories to bind-mount into the container, beyond the work directory
#   (which is added automatically). Note the REPOSITORY is deliberately NOT
#   mounted: it lives on EOS, and EOS inside the container is unreliable (reads
#   fail with "Permission denied" through the FUSE mount), so everything the
#   container needs is copied into the work directory first - see backend_setup.
FULLSIM_BINDS=${FULLSIM_BINDS:-/cvmfs}

# Per-batch CMSSW timeout, in seconds. Same class of hang risk the generation and
# Delphes steps are already guarded against (see run_gen_with_timeout and
# backends/delphes.sh), and the same treatment: on a timeout this batch simply
# contributes no ntuple, which the job tolerates. Generous, because this is the
# expensive backend: a 10-event batch legitimately takes ~20 minutes.
FULLSIM_TIMEOUT_SEC=${FULLSIM_TIMEOUT_SEC:-14400}

# Runs a command inside the container, with the same setsid + `pkill -g` whole-
# process-group kill as run_gen_with_timeout (see its comment for why plain
# `timeout` is not enough on its own).
fullsim_in_container() {
    local rc
    local binds=""
    local d other skip
    # $WORKDIR and $REPO_DIR must be visible inside the container; they are often
    # already inside one of FULLSIM_BINDS (e.g. the repo under /eos), so drop any
    # entry that another entry already covers rather than mounting it twice
    for d in $FULLSIM_BINDS "$WORKDIR"; do
        [ -e "$d" ] || continue
        skip=no
        for other in $FULLSIM_BINDS "$WORKDIR"; do
            [ "$d" = "$other" ] && continue
            case "$d" in "$other"/*) skip=yes ;; esac
        done
        [ "$skip" = no ] && binds="$binds -B $d"
    done
    setsid timeout -k 30 "${FULLSIM_TIMEOUT_SEC}s" \
        $FULLSIM_CONTAINER_CMD exec $binds --pwd "$WORKDIR" \
        --env FS_WORK="$FS_WORK",FS_CFGSRC="$FS_CFGSRC",FS_ANASRC="$FS_ANASRC",FS_NEVENT="$FS_NEVENT",FS_KEEP="$KEEP_INTERMEDIATE",FULLSIM_CMSSW_DIR="$FULLSIM_CMSSW_DIR",FULLSIM_SCRAM_ARCH="$FULLSIM_SCRAM_ARCH",FULLSIM_CONDDB="$FULLSIM_CONDDB",NT_JETS="$NT_JETS",NT_HLTJETS="$NT_HLTJETS",NT_QCDLABEL="$NT_QCDLABEL",NT_V1LABELS="$NT_V1LABELS",NT_DOHLT="$NT_DOHLT",NT_KEEPGENJET="$NT_KEEPGENJET",NT_JETPTMIN="$NT_JETPTMIN",NT_JETETAMAX="$NT_JETETAMAX",FS_FRAGMENT="$FS_FRAGMENT",FS_FRAGNAME="$FS_FRAGNAME" \
        "$FULLSIM_CONTAINER" bash -lc "bash $FS_CFGSRC/run_chain.sh $*" &
    local pgid=$!
    # Keep run.sh's stall watchdog fed while the container runs. Without this a
    # legitimately long batch (CMSSW is ~2 min/event, so anything above ~15
    # events exceeds STALL_TIMEOUT_SEC) would look stuck and the watchdog would
    # abort the whole job. Safe to do here, unlike for the generation step: this
    # step is bounded by its OWN `timeout` above, and everything it touches is
    # /cvmfs or local scratch - never the EOS mount whose unkillable hangs are
    # what the watchdog exists for.
    ( while sleep 60; do heartbeat; done ) &
    local ticker=$!
    wait $pgid
    rc=$?
    kill $ticker 2>/dev/null
    pkill -KILL -g $pgid 2>/dev/null
    heartbeat
    return $rc
}

backend_setup() {
    case "$BACKEND_OPTS" in
        offline+hlt) NT_DOHLT=true ;;
        offline)     NT_DOHLT=false ;;
        *)
            echo "ERROR: unknown fullsim option '$BACKEND_OPTS'. Expected: offline+hlt, offline." >&2
            exit 1
            ;;
    esac

    # apptainer is the current name, singularity the old one; both are present on
    # lxbatch, neither is guaranteed elsewhere
    FULLSIM_CONTAINER_CMD=${FULLSIM_CONTAINER_CMD:-}
    if [ -z "$FULLSIM_CONTAINER_CMD" ]; then
        for c in apptainer singularity; do
            if command -v $c >/dev/null 2>&1; then FULLSIM_CONTAINER_CMD=$c; break; fi
        done
    fi
    if [ -z "$FULLSIM_CONTAINER_CMD" ]; then
        echo "ERROR: neither apptainer nor singularity found - the fullsim backend needs one of them to run CMSSW (set FULLSIM_CONTAINER_CMD to override)" >&2
        exit 1
    fi
    if [ ! -e "$FULLSIM_CONTAINER" ]; then
        echo "ERROR: container image not found: $FULLSIM_CONTAINER (set FULLSIM_CONTAINER)" >&2
        exit 1
    fi
    if [ ! -d "$FULLSIM_CONDDB" ]; then
        echo "ERROR: open conditions not found at $FULLSIM_CONDDB (set FULLSIM_CONDDB; see fullsim_configs/README.md for how to get them)" >&2
        exit 1
    fi

    FS_WORK=$WORKDIR/fullsim
    # Everything the container reads is copied into the (local-scratch) work
    # directory first: the repository is on EOS, which is not reliably readable
    # from inside the container.
    FS_CFGSRC=$WORKDIR/fullsim_configs
    # The ntuplizer source is assembled into one directory: its own file plus the
    # headers it SHARES with the Delphes ntuplizers (the gen-level jet labelling
    # in particular, so the two backends cannot label a jet differently - see
    # fullsim_analyzers/StandaloneTypes.h).
    FS_ANASRC=$WORKDIR/fullsim_analyzer
    mkdir -p "$FS_WORK" "$FS_ANASRC" "$FS_CFGSRC"
    cp "$REPO_DIR"/fullsim_configs/*.py "$REPO_DIR"/fullsim_configs/run_chain.sh "$FS_CFGSRC/"
    cp "$REPO_DIR"/delphes_analyzers/EventData.h "$REPO_DIR"/delphes_analyzers/FatJetMatching.h \
       "$REPO_DIR"/delphes_analyzers/ParticleID.h "$REPO_DIR"/delphes_analyzers/ParticleInfo.h \
       "$REPO_DIR"/fullsim_analyzers/StandaloneTypes.h \
       "$REPO_DIR"/fullsim_analyzers/makeNtuplesFullSim.cc \
       "$REPO_DIR"/fullsim_analyzers/build.sh "$FS_ANASRC/"

    # How the generator-level events arrive (see run.sh's PROC_KIND):
    #   hepmc          -1 = "every event in this batch's events.hepmc", so a batch that
    #                  generated slightly fewer events than asked is still fully
    #                  reconstructed
    #   cmssw_fragment CMSSW generates them itself, so the count has to be stated: it is
    #                  exactly the batch size
    FS_FRAGMENT=''
    FS_FRAGNAME=''
    FS_NEVENT=-1
    if [ "$PROC_KIND" = "cmssw_fragment" ]; then
        FS_NEVENT=$NEVENT_GEN
        # cmsDriver imports the fragment as a python MODULE
        # (Configuration.GenProduction.<name>), so the name must be a valid
        # identifier - process names like "QCD_PT-470to600" are not.
        FS_FRAGNAME=$(echo "$PROC" | sed 's/[^A-Za-z0-9_]/_/g')
        FS_FRAGMENT=$FS_CFGSRC/$FS_FRAGNAME.py
        cp "$REPO_DIR/gen_configs/$PROC/fragment.py" "$FS_FRAGMENT"
        echo "fullsim: CMSSW GEN fragment $PROC -> Configuration/GenProduction/python/$FS_FRAGNAME.py"
    fi
    NT_JETS=${NT_JETS:-ak8PFJetsCHS}
    NT_HLTJETS=${NT_HLTJETS:-hltAK8PFJets}
    NT_QCDLABEL=${NT_QCDLABEL:-true}
    NT_V1LABELS=$USE_V1_LABELS
    NT_KEEPGENJET=${NT_KEEPGENJET:-false}
    # offline jet selection; the defaults match the CMS reference dataset (and the
    # Delphes cards' own 200 GeV) - see makeNtuplesFullSim.cc's header
    NT_JETPTMIN=${NT_JETPTMIN:-200}
    NT_JETETAMAX=${NT_JETETAMAX:-2.4}

    # Write the three cmsRun configs and build the ntuplizer ONCE for the whole
    # job: generating the HLT config alone takes ~1 minute (the GRun menu is
    # ~4.5 MB of python), which would be absurd to repeat per batch.
    echo "fullsim: preparing configs and building the ntuplizer (container: $FULLSIM_CONTAINER_CMD)"
    if ! fullsim_in_container setup > "$FS_WORK/setup.out" 2>&1; then
        echo "ERROR: fullsim setup failed - see below" >&2
        tail -40 "$FS_WORK/setup.out" >&2
        exit 1
    fi
    if ! grep -q SETUP_OK "$FS_WORK/setup.out"; then
        echo "ERROR: fullsim setup did not report success - see below" >&2
        tail -40 "$FS_WORK/setup.out" >&2
        exit 1
    fi
    echo "fullsim: setup done"
    NTUPLES_PRODUCED=0
}

# cwd on entry: $WORKDIR/proc_base, with this batch's events.hepmc in it
backend_run_batch() {
    local i=$1
    local bdir=$FS_WORK/batch_$i
    mkdir -p "$bdir"
    if [ "$PROC_KIND" != "cmssw_fragment" ]; then
        if [ ! -s events.hepmc ]; then
            echo "WARNING: batch $i produced no events.hepmc - skipping its reconstruction" >&2
            return 0
        fi
        # moved, not copied: the HepMC file is large (~10 MB per 100 events) and the
        # generation step has no further use for it
        mv events.hepmc "$bdir/events.hepmc"
    fi

    # NOT piped into tee: that would make the exit status checked below tee's,
    # not the container's, so a failed batch would look successful
    fullsim_in_container batch "$i" > "$bdir/batch.out" 2>&1
    local rc=$?
    cat "$bdir/batch.out"
    if [ $rc -eq 0 ] && [ -s "$bdir/ntuple.root" ]; then
        NTUPLES_PRODUCED=$((NTUPLES_PRODUCED + 1))
    else
        # Same policy as the other backends' per-step failures: this batch's
        # contribution is lost, the job carries on with a slightly reduced yield.
        if [ $rc -eq 0 ]; then
            echo "WARNING: batch $i reported success but produced no ntuple.root - skipping it" >&2
        else
            echo "WARNING: fullsim batch $i failed or timed out (limit ${FULLSIM_TIMEOUT_SEC}s) - skipping it" >&2
        fi
        # A failed ntuplizer still leaves an 811-byte keyless ntuple.root behind.
        # It MUST go: the merge steps below glob batch_*/ntuple.root, so leaving it
        # would feed garbage to hadd and let a job in which every batch failed still
        # publish a file and exit 0. That is exactly what happened to job
        # 406255.45 of the 2026-10-09 round (ProductNotFound in the ntuplizer, both
        # batches, "0 of 2 batches reconstructed successfully", exit 0, empty file
        # on EOS).
        rm -f "$bdir/ntuple.root"
    fi
    # the HepMC file is the single biggest intermediate; nothing needs it now
    [ "$KEEP_INTERMEDIATE" != "true" ] && rm -f "$bdir/events.hepmc"
    cd "$WORKDIR"
}

# Push a valid partial ntuple to EOS after every batch but the last.
#
# backend_finalize() is the only place that copies output out, so a job killed by
# SYSTEM_PERIODIC_REMOVE at the wall-time limit used to lose EVERY completed batch
# (the 2026-10-08 jetclass2sb trial lost 88 jobs, including all 30 of its lowest
# pThat bin, with ~8 h of finished reconstruction each and zero files written).
# Checkpointing under the SAME final name keeps the output layout unchanged - one
# ntuple_$JOBNUM.root per job - and backend_finalize simply overwrites it with the
# complete merge. Never fails the job: a failed checkpoint is not worse than the
# old behaviour.
backend_intermediate_merge() {
    local i=$1
    # the last batch is backend_finalize's job
    [ "$i" -ge "$((nbatch - 1))" ] && return 0

    local outdir=$OUTPUT_PATH/$PROC/fullsim_$BACKEND_OPTS
    local partial=$FS_WORK/ntuple_partial.root
    [ "$NTUPLES_PRODUCED" -eq 0 ] && return 0
    local files
    files=$(ls "$FS_WORK"/batch_*/ntuple.root 2>/dev/null)
    [ -z "$files" ] && return 0

    if [ "$(echo "$files" | wc -l)" -eq 1 ]; then
        cp $files "$partial" || return 0
    else
        hadd -f "$partial" $files >/dev/null 2>&1 || return 0
    fi
    if copy_to_eos "$partial" "$outdir/ntuple_$JOBNUM.root"; then
        echo -e "\033[1m  [checkpoint] batches 0-$i safe at $outdir/ntuple_$JOBNUM.root\033[0m"
    fi
    rm -f "$partial"
    return 0
}

backend_finalize() {
    local unit=$BACKEND_OPTS
    local outdir=$OUTPUT_PATH/$PROC/fullsim_$unit
    local local_ntuple=$FS_WORK/ntuple_$JOBNUM.root
    local files
    files=$(ls "$FS_WORK"/batch_*/ntuple.root 2>/dev/null)
    if [ -z "$files" ] || [ "$NTUPLES_PRODUCED" -eq 0 ]; then
        echo "ERROR: no batch produced an ntuple ($NTUPLES_PRODUCED of $nbatch succeeded)" >&2
        echo "ERROR: failing the job rather than publishing an empty ntuple" >&2
        exit 1
    fi
    # one flat TTree per batch: hadd is all that is needed (unlike the Delphes
    # backend, which merges its per-batch detector files BEFORE ntuplizing)
    if [ "$(echo "$files" | wc -l)" -eq 1 ]; then
        mv $files "$local_ntuple"
    else
        hadd -f "$local_ntuple" $files || { echo "ERROR: hadd of the per-batch ntuples failed" >&2; exit 1; }
    fi

    if [ "$KEEP_INTERMEDIATE" = "true" ]; then
        local f
        for f in "$FS_WORK"/batch_*/reco.root; do
            [ -s "$f" ] || continue
            local b=$(basename "$(dirname "$f")")
            copy_to_eos "$f" "$outdir/aodsim_${JOBNUM}_${b}.root" || exit 1
        done
    fi
    copy_to_eos "$local_ntuple" "$outdir/ntuple_$JOBNUM.root" || exit 1

    echo -e "\033[1mJob done. Generated $NEVENT events for $PROC with the fullsim backend"
    echo -e "($NTUPLES_PRODUCED of $nbatch batches reconstructed successfully).\033[0m"
    echo -e "\033[1m[$unit] Ntuple file path: $outdir/ntuple_$JOBNUM.root\033[0m"
}
