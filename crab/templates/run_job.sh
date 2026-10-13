#!/bin/bash
# Drives the fullsim chain for one CRAB job.
#
# TWO CONTAINERS, ONE JOB. This script runs on the worker node itself and re-invokes
# ITSELF with --step inside whichever container that step needs:
#
#   EL7 (cmssw-el7)  everything CMSSW: the conditions/MG5 fetches (xrdcp comes from the
#                    release), run_chain.sh, and the final hadd. CMSSW_10_6_30 is slc7.
#   EL9 (cmssw-el9)  MadGraph5 + Pythia8 generation for hepmc processes. The MG5 install
#                    is built against glibc 2.34 and python >= 3.7; under SLC7 (glibc
#                    2.17, python 2.7) it does not start at all.
#
# Containers cannot be nested, so the dispatcher has to sit outside both. This mirrors
# what run.sh does on lxplus, where generation runs on the EL9 host and only CMSSW
# enters the container.
#
# Leaves exactly one ntuple.root in the job directory for CRAB to stage out.
set -u

EL7=${JETCLASS_EL7:-/cvmfs/cms.cern.ch/common/cmssw-el7}
EL9=${JETCLASS_EL9:-/cvmfs/cms.cern.ch/common/cmssw-el9}

# baked in by build_simpack.py
PROC_KIND=__PROCKIND__          # cmssw_fragment | hepmc
MG5_URL=__MG5_URL__             # only used when PROC_KIND=hepmc

# ---------------------------------------------------------------------------
# Steps. Each runs INSIDE a container; the environment and cwd are inherited from
# the dispatcher (verified: cmssw-elX --command-to-run passes both through).
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
        # MG5 COMPILES the process code it generates, so it needs a Fortran compiler.
        # The bare EL9 container has none ("No Fortran Compiler detected! Please install
        # one"), and on lxplus this is invisible because the host supplies it. A CMSSW
        # el9 release ships its own gcc toolchain, gfortran included, so set that up
        # purely to put a compiler on PATH - nothing in the generation uses CMSSW itself.
        # Borrow ONLY the compiler directory, in a subshell, and put it on PATH.
        # Sourcing the full CMSSW environment here drags in variables that break MG5 -
        # notably PYTHIA8DATA, which points at CMSSW's Pythia 8.309 xmldoc and makes
        # MG5's bundled Pythia 8.317 abort with "unmatched version numbers".
        GEN_ARCH=${GEN_SCRAM_ARCH:-el9_amd64_gcc12}
        FC_DIR=$( source /cvmfs/cms.cern.ch/cmsset_default.sh >/dev/null 2>&1
                  export SCRAM_ARCH=$GEN_ARCH
                  R=$(ls -d /cvmfs/cms.cern.ch/"$GEN_ARCH"/cms/cmssw/CMSSW_14_0_* 2>/dev/null | tail -1)
                  [ -n "$R" ] || exit 0
                  cd "$R" && eval "$(scram runtime -sh)" >/dev/null 2>&1
                  command -v gfortran >/dev/null && dirname "$(command -v gfortran)" )
        # PATH alone is not enough: f951 (the Fortran front end) loads libisl.so.23 from
        # the toolchain's own lib/, so that has to be on LD_LIBRARY_PATH too, or every
        # compile dies with "error while loading shared libraries: libisl.so.23".
        # Still only the compiler's directories - NOT CMSSW's full LD_LIBRARY_PATH,
        # which would reintroduce the Pythia conflict.
        if [ -n "$FC_DIR" ]; then
            export PATH="$FC_DIR:$PATH"
            GCC_ROOT=$(dirname "$FC_DIR")
            export LD_LIBRARY_PATH="$GCC_ROOT/lib64:$GCC_ROOT/lib:${LD_LIBRARY_PATH:-}"
        fi
        command -v gfortran >/dev/null \
            || { echo "ERROR: no gfortran on PATH in the EL9 container - MG5 cannot build" >&2; exit 1; }
        echo "  gen: $(gfortran --version | head -1)  [from $FC_DIR]"

        # CRAB sets up its own CMSSW_14_0_0 (el9_amd64_gcc12) before calling scriptExe,
        # so PYTHIA8DATA arrives in the INHERITED environment pointing at CMSSW's Pythia
        # 8.309 xmldoc. MG5 bundles 8.317 and aborts with "unmatched version numbers".
        # Unset it unconditionally - MG5's Pythia finds its own data relative to itself.
        # (An earlier fix only stopped US exporting it, which was not the whole story.)
        unset PYTHIA8DATA
        # same family of problem: a stale LHAPDF data path would silently change PDFs
        unset LHAPDF_DATA_PATH LHAPATH
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
    # run_chain.sh keys off an EMPTY FS_FRAGMENT to take its HepMC route (MCFileSource
    # via patch_gen); -1 means "every event in this batch's events.hepmc", so a batch
    # that generated slightly fewer events is still fully reconstructed.
    export FS_FRAGMENT=''
    export FS_FRAGNAME=''
    export FS_NEVENT=-1
fi

# ---- conditions: CVMFS if mounted, else fetch from the open-data portal ----
# /cvmfs/cms-opendata-conddb.cern.ch is not auto-mounted at most sites, and at ~1.67 GB
# cannot ride in the CRAB sandbox - but the same files are published as ordinary
# xrootd-readable files, anonymously. So no site whitelist is needed.
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
        echo "MG5 ready at $MG5_PATH ($(( $(date +%s) - t0 ))s)"
    fi
    chmod +x "$GENDIR/run_gen.sh" 2>/dev/null
fi

# MG5 looks up lhapdf-config by BARE NAME unless told otherwise, and it is on PATH
# nowhere. On lxplus this is masked by a user config in the developer's home
# (~/.mg5/mg5_configuration.txt) holding an absolute path to the EOS install - which is
# in neither the repo nor the tarball, so the grid never sees it and generate_events
# dies with "lhapdf executable (lhapdf-config) is not found on your system".
#
# Write our own user config instead, derived from wherever MG5 actually landed. CRAB
# sets HOME to the job directory, so this is job-local and touches no shared install.
if [ "$PROC_KIND" = "hepmc" ]; then
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
        # run_gen.sh re-draws a random (mass, pT_min) point on every call, so each batch
        # samples the scan independently - the same behaviour as the lxplus path. The MG5
        # `proc` directory built on the first call is reused by later batches.
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
# NOTE: space-separated, NOT the newline-separated output of a bare `ls`. This string
# is passed to --command-to-run as one command line, and embedded newlines break it
# ("--step: $./run_job.sh: No such file or directory").
files=$(ls "$FS_WORK"/batch_*/ntuple.root 2>/dev/null | tr '\n' ' ')
nfiles=$(echo $files | wc -w)
if [ "$nfiles" -eq 1 ]; then
    cp $files "$HERE/ntuple.root" || exit 1
else
    "$EL7" --command-to-run "./run_job.sh --step merge $HERE/ntuple.root $files" || exit 1
fi
echo "=== done: $nok/$NBATCH batches -> $(stat -c %s "$HERE/ntuple.root") bytes ==="
