#!/bin/bash
# FullSim backend for run.sh: CMS full simulation, reconstruction and HLT in
# CMSSW, from the same generated events the Delphes backend reconstructs and
# writing the same ntuple schema.
#
# Uses only openly available software and conditions.
# Caveats: no pile-up, and 2018 design conditions.
#
# BACKEND_OPTS:
#   offline+hlt   (default) one row per jet holding the offline AK8 jet and its
#                 matched HLT AK8 jet
#   offline       offline jets only; the hlt_* branches stay empty and
#                 hlt_matched is false. The HLT step still runs, since RECO needs
#                 its RAW output, so this saves ntuple size rather than CPU.
#
# Per batch: GEN,SIM (from events.hepmc) -> DIGI,L1,DIGI2RAW,HLT:GRun -> RAW2DIGI,
# L1Reco,RECO -> ntuple. The three CMSSW steps run inside a container because they
# need an SLC7 environment; everything else runs on the host.

BACKEND_DEFAULT_OPTS=offline+hlt

# All overridable, so this can be pointed at a local copy of any ingredient.
#   the container image holding an SLC7 userland + CMSSW
FULLSIM_CONTAINER=${FULLSIM_CONTAINER:-/cvmfs/unpacked.cern.ch/registry.hub.docker.com/cmsopendata/cmssw_10_6_30-slc7_amd64_gcc700:latest}
#   the CMSSW release to use inside it
FULLSIM_CMSSW_DIR=${FULLSIM_CMSSW_DIR:-/cvmfs/cms.cern.ch/slc7_amd64_gcc700/cms/cmssw/CMSSW_10_6_30}
FULLSIM_SCRAM_ARCH=${FULLSIM_SCRAM_ARCH:-slc7_amd64_gcc700}
#   the open condition databases
FULLSIM_CONDDB=${FULLSIM_CONDDB:-/cvmfs/cms-opendata-conddb.cern.ch}
#   directories to bind-mount into the container, beyond the work directory,
#   which is added automatically. The repository is deliberately not mounted: it
#   lives on EOS, and EOS reads from inside the container fail, so everything the
#   container needs is copied into the work directory by backend_setup.
FULLSIM_BINDS=${FULLSIM_BINDS:-/cvmfs}

# Per-batch CMSSW timeout, in seconds. Same hang risk and same treatment as the
# other steps: on a timeout the batch contributes no ntuple and the job carries
# on. Generous, because a 10-event batch legitimately takes ~20 minutes.
FULLSIM_TIMEOUT_SEC=${FULLSIM_TIMEOUT_SEC:-14400}

# Run one stage of run_chain.sh inside the container, in its own process group so
# the whole tree can be killed on timeout.
fullsim_in_container() {
    local rc
    local binds=""
    local d other skip
    # $WORKDIR and $REPO_DIR must be visible inside the container, but are often
    # already inside one of FULLSIM_BINDS, so drop any entry another one covers
    # rather than mounting it twice.
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
    # Keep run.sh's stall watchdog fed while the container runs: at ~2 min/event
    # any batch above ~15 events outlives STALL_TIMEOUT_SEC and would look stuck.
    # Safe here, unlike for the generation step, because this step is bounded by
    # its own timeout above and touches only /cvmfs and local scratch, never the
    # EOS mount whose unkillable hangs the watchdog exists for.
    ( while sleep 60; do heartbeat; done ) &
    local ticker=$!
    wait $pgid
    rc=$?
    kill $ticker 2>/dev/null
    pkill -KILL -g $pgid 2>/dev/null
    heartbeat
    return $rc
}

# Validate the environment, stage everything the container needs into local
# scratch, then write the cmsRun configs and build the ntuplizer.
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
    # Everything the container reads is copied into the local-scratch work
    # directory first, since the repository is on EOS.
    FS_CFGSRC=$WORKDIR/fullsim_configs
    # The ntuplizer source is assembled into one directory: its own file plus the
    # headers it shares with the Delphes ntuplizers. Sharing the gen-level jet
    # labelling in particular is what keeps the two backends from labelling a jet
    # differently.
    FS_ANASRC=$WORKDIR/fullsim_analyzer
    mkdir -p "$FS_WORK" "$FS_ANASRC" "$FS_CFGSRC"
    cp "$REPO_DIR"/fullsim_configs/*.py "$REPO_DIR"/fullsim_configs/run_chain.sh "$FS_CFGSRC/"
    cp "$REPO_DIR"/delphes_analyzers/EventData.h "$REPO_DIR"/delphes_analyzers/FatJetMatching.h \
       "$REPO_DIR"/delphes_analyzers/ParticleID.h "$REPO_DIR"/delphes_analyzers/ParticleInfo.h \
       "$REPO_DIR"/fullsim_analyzers/StandaloneTypes.h \
       "$REPO_DIR"/fullsim_analyzers/makeNtuplesFullSim.cc \
       "$REPO_DIR"/fullsim_analyzers/build.sh "$FS_ANASRC/"

    # How the generator-level events arrive (see run.sh's PROC_KIND):
    #   hepmc          -1 means "every event in this batch's events.hepmc", so a
    #                  batch that generated fewer events than asked is still
    #                  fully reconstructed
    #   cmssw_fragment CMSSW generates them itself, so the count must be stated
    FS_FRAGMENT=''
    FS_FRAGNAME=''
    FS_NEVENT=-1
    if [ "$PROC_KIND" = "cmssw_fragment" ]; then
        FS_NEVENT=$NEVENT_GEN
        # cmsDriver imports the fragment as a python module, so the name must be
        # a valid identifier - process names like "QCD_PT-470to600" are not.
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
    # Offline jet selection. The defaults match the CMS reference dataset and the
    # Delphes cards.
    NT_JETPTMIN=${NT_JETPTMIN:-200}
    NT_JETETAMAX=${NT_JETETAMAX:-2.4}

    # Write the cmsRun configs and build the ntuplizer once for the whole job:
    # generating the HLT config alone takes ~1 minute, so repeating it per batch
    # would dominate a short job.
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

# Run the full CMSSW chain for one batch and count whether it produced an ntuple.
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

    # Not piped into tee, which would make the status checked below tee's rather
    # than the container's, so a failed batch would look successful.
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
        # A failed ntuplizer still leaves a small keyless ntuple.root behind. It
        # must go: the merge steps below glob batch_*/ntuple.root, so leaving it
        # would feed garbage to hadd and let a job in which every batch failed
        # still publish a file and exit 0.
        rm -f "$bdir/ntuple.root"
    fi
    # the HepMC file is the single biggest intermediate; nothing needs it now
    [ "$KEEP_INTERMEDIATE" != "true" ] && rm -f "$bdir/events.hepmc"
    cd "$WORKDIR"
}

# Publish a valid partial ntuple after every batch but the last.
#
# Only backend_finalize copies output out, so without this a job killed at the
# wall-time limit loses every completed batch. The checkpoint uses the same final
# name, so the output layout stays one ntuple_$JOBNUM.root per job and
# backend_finalize simply overwrites it with the complete merge. Never fails the
# job: a failed checkpoint leaves things no worse than not checkpointing.
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

# Merge the per-batch ntuples and copy the result to EOS. Gated on
# NTUPLES_PRODUCED rather than on the glob, so a job in which every batch failed
# exits nonzero instead of publishing an empty file.
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
    # One flat TTree per batch, so hadd is all that is needed; the Delphes
    # backend instead merges its detector files before ntuplizing.
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
