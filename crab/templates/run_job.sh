#!/bin/bash
# Drives the fullsim chain for one CRAB job.
#
# Two containers, one job: this script runs on the worker node itself and re-invokes
# itself with --step inside whichever container a step needs.
#
#   EL7  everything CMSSW: the conditions and MG5 fetches, run_chain.sh, the final
#        hadd. The release used is slc7.
#   EL9  MadGraph5 + Pythia8 generation for hepmc processes. The MG5 install needs a
#        newer glibc and python than SLC7 provides and will not start there.
#
# Containers cannot be nested, so the dispatcher has to sit outside both. This mirrors
# run.sh, where generation runs on the host and only CMSSW enters the container.
#
# Leaves exactly one ntuple.root in the job directory for CRAB to stage out.
set -u

EL7=${JETCLASS_EL7:-/cvmfs/cms.cern.ch/common/cmssw-el7}
EL9=${JETCLASS_EL9:-/cvmfs/cms.cern.ch/common/cmssw-el9}

# baked in by build_simpack.py
PROC_KIND=__PROCKIND__          # cmssw_fragment | hepmc
MG5_URL=__MG5_URL__             # only used when PROC_KIND=hepmc

# ---------------------------------------------------------------------------
# Steps. Each runs inside a container, inheriting the environment and cwd from the
# dispatcher.
# ---------------------------------------------------------------------------
cmssw_env() {
    source /cvmfs/cms.cern.ch/cmsset_default.sh >/dev/null 2>&1
    pushd "$FULLSIM_CMSSW_DIR" >/dev/null && eval "$(scram runtime -sh)" && popd >/dev/null
}

if [ "${1:-}" = "--step" ]; then
    step=$2; shift 2
    case "$step" in
    fetch)
        # $1 = destination dir, rest = files to fetch from $CONDDB_SRC
        dest=$1; shift
        cmssw_env
        for db in "$@"; do
            t0=$(date +%s)
            xrdcp -f -s "$CONDDB_SRC/$db" "$dest/$db" || exit 65
            [ -s "$dest/$db" ] || exit 65
            echo "  $db: fetched $(stat -c %s "$dest/$db") bytes in $(( $(date +%s) - t0 ))s"
        done
        ;;
    fetch-mg5)
        cmssw_env
        xrdcp -f -s "$MG5_URL" "$1" || exit 65
        ;;
    chain)
        # $@ = arguments for run_chain.sh (setup | batch <i>)
        bash "$FS_CFGSRC/run_chain.sh" "$@"
        ;;
    gen)
        # $1 = events to generate. run_gen.sh cd's to its own directory and writes
        # events.hepmc there.
        #
        # MG5 compiles the process code it generates, so it needs a Fortran compiler,
        # which the bare EL9 container has none of. A CMSSW el9 release ships a gcc
        # toolchain including gfortran, so borrow only that directory, in a subshell,
        # and put it on PATH. Nothing in the generation uses CMSSW itself, and
        # sourcing its full environment would break MG5: PYTHIA8DATA would point at
        # CMSSW's Pythia xmldoc and make MG5's own Pythia abort on a version
        # mismatch.
        GEN_ARCH=${GEN_SCRAM_ARCH:-el9_amd64_gcc12}
        FC_DIR=$( source /cvmfs/cms.cern.ch/cmsset_default.sh >/dev/null 2>&1
                  export SCRAM_ARCH=$GEN_ARCH
                  R=$(ls -d /cvmfs/cms.cern.ch/"$GEN_ARCH"/cms/cmssw/CMSSW_14_0_* 2>/dev/null | tail -1)
                  [ -n "$R" ] || exit 0
                  cd "$R" && eval "$(scram runtime -sh)" >/dev/null 2>&1
                  command -v gfortran >/dev/null && dirname "$(command -v gfortran)" )
        # PATH alone is not enough: the Fortran front end loads a library from the
        # toolchain's own lib/, so that must be on LD_LIBRARY_PATH too. Still only the
        # compiler's directories, never CMSSW's full path, which would bring the
        # Pythia conflict back.
        if [ -n "$FC_DIR" ]; then
            export PATH="$FC_DIR:$PATH"
            GCC_ROOT=$(dirname "$FC_DIR")
            export LD_LIBRARY_PATH="$GCC_ROOT/lib64:$GCC_ROOT/lib:${LD_LIBRARY_PATH:-}"
        fi
        command -v gfortran >/dev/null \
            || { echo "ERROR: no gfortran on PATH in the EL9 container - MG5 cannot build" >&2; exit 1; }
        echo "  gen: $(gfortran --version | head -1)  [from $FC_DIR]"

        # Data paths for MG5's bundled Pythia8 and LHAPDF, set explicitly.
        #
        # Neither of the two easier options works: CRAB sets up its own release before
        # calling scriptExe, so PYTHIA8DATA arrives pointing at CMSSW's Pythia xmldoc
        # and MG5's own Pythia aborts on the version mismatch; and merely unsetting it
        # makes the interface binary fall back to a path baked in at install time,
        # which names the machine MG5 was built on.
        unset LHAPATH
        if [ -d "$MG5_PATH/bin/HEPTools/pythia8/share/Pythia8/xmldoc" ]; then
            export PYTHIA8DATA="$MG5_PATH/bin/HEPTools/pythia8/share/Pythia8/xmldoc"
        else
            unset PYTHIA8DATA
        fi
        if [ -d "$MG5_PATH/bin/HEPTools/lhapdf6_py3/share/LHAPDF" ]; then
            export LHAPDF_DATA_PATH="$MG5_PATH/bin/HEPTools/lhapdf6_py3/share/LHAPDF"
        fi
        echo "  gen: PYTHIA8DATA=${PYTHIA8DATA:-<unset>}"
        echo "  gen: LHAPDF_DATA_PATH=${LHAPDF_DATA_PATH:-<unset>}"
        cd "$GENDIR" && MG5_PATH="$MG5_PATH" ./run_gen.sh "$1"
        ;;
    merge)
        cmssw_env
        command -v hadd >/dev/null || { echo "ERROR: hadd not on PATH" >&2; exit 1; }
        out=$1; shift
        hadd -f "$out" "$@"
        ;;
    *) echo "ERROR: unknown step '$step'" >&2; exit 2 ;;
    esac
    exit $?
fi

# ---------------------------------------------------------------------------
# Dispatcher (runs on the worker node, outside any container)
# ---------------------------------------------------------------------------
NEVENTS=0; BATCH=0; JOBID=${1:-0}
for a in "$@"; do
    case "$a" in
        events=*) NEVENTS=${a#events=} ;;
        batch=*)  BATCH=${a#batch=} ;;
    esac
done
[ "$BATCH" -le 0 ] && BATCH=$NEVENTS
NBATCH=$(( NEVENTS / BATCH )); [ "$NBATCH" -le 0 ] && NBATCH=1

echo "=== run_job.sh: jobid=$JOBID events=$NEVENTS batch=$BATCH nbatch=$NBATCH kind=$PROC_KIND ==="
for c in "$EL7" "$EL9"; do
    [ -x "$c" ] || { echo "ERROR: container wrapper $c not available on this node" >&2; exit 1; }
done

HERE=$(pwd)
export FS_WORK=$HERE/work
export FS_CFGSRC=$HERE/payload/cfg
export FS_ANASRC=$HERE/payload/ana
export GENDIR=$HERE/payload/gen
export FS_KEEP=false
export FULLSIM_CONDDB=${FULLSIM_CONDDB:-/cvmfs/cms-opendata-conddb.cern.ch}
export FULLSIM_CMSSW_DIR=${FULLSIM_CMSSW_DIR:-/cvmfs/cms.cern.ch/slc7_amd64_gcc700/cms/cmssw/CMSSW_10_6_30}
export FULLSIM_SCRAM_ARCH=${FULLSIM_SCRAM_ARCH:-slc7_amd64_gcc700}
export CONDDB_SRC=${CONDDB_SRC:-root://eospublic.cern.ch//eos/opendata/cms/conddb}
export NT_JETPTMIN=__JETPTMIN__
export NT_JETETAMAX=__JETETAMAX__
if [ "$PROC_KIND" = "cmssw_fragment" ]; then
    export FS_FRAGMENT=$FS_CFGSRC/__FRAGNAME__.py
    export FS_FRAGNAME=__FRAGNAME__
    export FS_NEVENT=$BATCH
else
    # run_chain.sh takes its HepMC route when FS_FRAGMENT is empty, and -1 means
    # "every event in this batch's events.hepmc", so a batch that generated fewer
    # events than asked is still fully reconstructed.
    export FS_FRAGMENT=''
    export FS_FRAGNAME=''
    export FS_NEVENT=-1
fi

# ---- conditions: CVMFS if mounted, else fetch from the open-data portal ----
# The open conditions repo is not auto-mounted at most sites, and is far too large for
# the CRAB sandbox, but the same files are published as ordinary xrootd-readable files,
# anonymously. So no site whitelist is needed.
CONDDB_FILES="__CONDDB_FILES__"
need_fetch=false
for db in $CONDDB_FILES; do [ -s "$FULLSIM_CONDDB/$db" ] || need_fetch=true; done
if [ "$need_fetch" = false ]; then
    echo "conditions: CVMFS mount present at $FULLSIM_CONDDB - nothing to fetch"
else
    echo "conditions: $FULLSIM_CONDDB incomplete here (site ${GLIDEIN_CMSSite:-unknown}) - fetching over xrootd"
    dest=$HERE/conddb; mkdir -p "$dest"; missing=''
    for db in $CONDDB_FILES; do
        if [ -s "$FULLSIM_CONDDB/$db" ]; then ln -sf "$FULLSIM_CONDDB/$db" "$dest/$db"; echo "  $db: from CVMFS"
        else missing="$missing $db"; fi
    done
    if [ -n "$missing" ]; then
        "$EL7" --command-to-run "./run_job.sh --step fetch $dest$missing" \
            || { echo "ERROR: conditions fetch failed" >&2; exit 65; }
    fi
    export FULLSIM_CONDDB=$dest
fi
echo "conditions OK: $FULLSIM_CONDDB"

# ---- MG5, for hepmc processes only ----
if [ "$PROC_KIND" = "hepmc" ]; then
    if [ -n "${MG5_PATH:-}" ] && [ -x "${MG5_PATH}/bin/mg5_aMC" ]; then
        echo "MG5 provided via MG5_PATH=$MG5_PATH - skipping the fetch"
        export MG5_PATH
        MG5_IS_OURS=false
    else
        t0=$(date +%s)
        "$EL7" --command-to-run "./run_job.sh --step fetch-mg5 $HERE/mg5.tar.gz" \
            || { echo "ERROR: could not fetch MG5 from $MG5_URL" >&2; exit 65; }
        mkdir -p "$HERE/mg5"
        tar -xzf "$HERE/mg5.tar.gz" -C "$HERE/mg5" --strip-components=1 \
            || { echo "ERROR: could not unpack the MG5 tarball" >&2; exit 65; }
        rm -f "$HERE/mg5.tar.gz"
        export MG5_PATH=$HERE/mg5
        [ -x "$MG5_PATH/bin/mg5_aMC" ] \
            || { echo "ERROR: $MG5_PATH/bin/mg5_aMC missing after unpack" >&2; exit 65; }
        MG5_IS_OURS=true
        echo "MG5 ready at $MG5_PATH ($(( $(date +%s) - t0 ))s)"
    fi
    chmod +x "$GENDIR/run_gen.sh" 2>/dev/null
fi

# MG5 looks up lhapdf-config by bare name unless told otherwise, and it is on PATH
# nowhere, so generate_events dies without a user config. Write one here, derived from
# wherever MG5 actually landed. CRAB sets HOME to the job directory, so this is
# job-local and touches no shared install.
if [ "$PROC_KIND" = "hepmc" ]; then
    # HEPTools' *-config scripts bake in the prefix they were installed under, so
    # after unpacking elsewhere they still advertise the original machine's paths and
    # MG5 looks for its PDF index where nothing exists. Rewrite that root to wherever
    # MG5 landed; pythia8-config locates itself and needs no help, lhapdf-config does.
    #
    # Never rewrite an install this job did not unpack: MG5_PATH may point at a shared
    # read-only copy, and sed -i would corrupt it for everyone.
    OLDROOT=$(grep -m1 '^prefix=' "$MG5_PATH/bin/HEPTools/lhapdf6_py3/bin/lhapdf-config" 2>/dev/null \
              | sed 's/^prefix=//; s|/bin/HEPTools/.*||')
    if [ "${MG5_IS_OURS:-false}" = true ] && [ -n "$OLDROOT" ] && [ "$OLDROOT" != "$MG5_PATH" ]; then
        echo "MG5 paths: rewriting baked prefix $OLDROOT -> $MG5_PATH"
        grep -rl "$OLDROOT" "$MG5_PATH"/bin/HEPTools/*/bin "$MG5_PATH"/HEPTools/*/bin 2>/dev/null \
            | xargs -r sed -i "s|$OLDROOT|$MG5_PATH|g"
    fi

    LHA=$MG5_PATH/HEPTools/lhapdf6_py3/bin/lhapdf-config
    if [ -x "$LHA" ]; then
        mkdir -p "$HOME/.mg5"
        { echo "lhapdf_py3 = $LHA"; echo "lhapdf = $LHA"; } > "$HOME/.mg5/mg5_configuration.txt"
        echo "MG5 lhapdf: $LHA"
    else
        echo "ERROR: no lhapdf-config at $LHA - the run card asks for pdlabel=lhapdf" >&2
        exit 65
    fi
fi

mkdir -p "$FS_WORK"
"$EL7" --command-to-run "./run_job.sh --step chain setup" \
    || { echo "ERROR: run_chain setup failed" >&2; exit 1; }

nok=0
for i in $(seq 0 $((NBATCH-1))); do
    if [ "$PROC_KIND" = "hepmc" ]; then
        # run_gen.sh draws a fresh random parameter point on every call, so each
        # batch samples the scan independently. The MG5 `proc` directory built on the
        # first call is reused by the later batches.
        rm -f "$GENDIR/events.hepmc"
        mkdir -p "$FS_WORK/batch_$i"
        if ! "$EL9" --command-to-run "./run_job.sh --step gen $BATCH"; then
            echo "WARNING: generation failed for batch $i - skipping it" >&2; continue
        fi
        if [ ! -s "$GENDIR/events.hepmc" ]; then
            echo "WARNING: batch $i produced no events.hepmc - skipping it" >&2; continue
        fi
        mv "$GENDIR/events.hepmc" "$FS_WORK/batch_$i/events.hepmc"
    fi
    if "$EL7" --command-to-run "./run_job.sh --step chain batch $i"; then
        [ -s "$FS_WORK/batch_$i/ntuple.root" ] && nok=$((nok+1))
    else
        echo "WARNING: batch $i failed - skipping it" >&2
        rm -f "$FS_WORK/batch_$i/ntuple.root"
    fi
done

if [ "$nok" -eq 0 ]; then
    echo "ERROR: no batch produced an ntuple - failing rather than staging out nothing" >&2
    exit 1
fi
# Space-separated, not the newline-separated output of a bare `ls`: this string is
# passed to --command-to-run as one command line, and an embedded newline breaks it.
files=$(ls "$FS_WORK"/batch_*/ntuple.root 2>/dev/null | tr '\n' ' ')
nfiles=$(echo $files | wc -w)
if [ "$nfiles" -eq 1 ]; then
    cp $files "$HERE/ntuple.root" || exit 1
else
    "$EL7" --command-to-run "./run_job.sh --step merge $HERE/ntuple.root $files" || exit 1
fi
echo "=== done: $nok/$NBATCH batches -> $(stat -c %s "$HERE/ntuple.root") bytes ==="

# ---------------------------------------------------------------------------
# FrameworkJobReport.xml
#
# CRAB's wrapper parses this the moment the scriptExe returns. If it is missing or
# unparseable the job fails with exit code 50115 and, the expensive part, no stageout
# is done however well the work went.
#
# A scriptExe that runs cmsRun as its last act gets the report for free. This one does
# not - the ntuplizer is a standalone FWLite binary and the merge is a hadd - so the
# report is written here.
#
# It must be an <AnalysisFile>, not a <File>. A <File> describes an EDM output, and
# CRAB follows it by reading provenance with edmProvDump, which aborts on a plain TTree
# and fails the job with exit code 56, again only after all the work is done.
# <AnalysisFile> is what cmsRun emits for a TFileService output, i.e. an ordinary ROOT
# file, which is what the ntuplizer writes. Keep this in step with the TFileService
# declaration in pset.py: together they are what make CRAB treat the ntuple as a TFile
# output rather than an EDM one.
NEV_DONE=$(( nok * BATCH ))
cat > "$HERE/FrameworkJobReport.xml" <<EOF
<FrameworkJobReport>
<AnalysisFile>
  <FileName>ntuple.root</FileName>
  <Source  Value="TFileService" />
</AnalysisFile>
</FrameworkJobReport>
EOF
echo "=== wrote FrameworkJobReport.xml: ntuple.root, $NEV_DONE events ==="
