#!/bin/bash
#
# Pack the MG5_aMC installation so grid jobs can fetch it.
#
# WHY: processes without a CMSSW GEN fragment (gen_configs/jetclass2/*, i.e.
# PROC_KIND=hepmc) generate their events with a standalone MadGraph5 + Pythia8 run
# before CMSSW ever starts - see gen_configs/run_gen_default.sh. That needs a full
# MG5_aMC install, which a grid worker node does not have:
#   * /cvmfs/cms.cern.ch ships madgraph5amcatnlo 2.4.3 / 2.6.0 / 2.7.3 only, and this
#     setup uses v3.7.2 - a different major version, not a drop-in;
#   * the install is ~850 MB, far over the CRAB input-sandbox limit.
# So we stage it once and let each job pull it over xrootd, exactly as run_job.sh
# already does for the open-data conditions.
#
# The tarball is immutable: make it once, reuse it for every job and every production.
#
# USAGE
#   ./make_mg5_tarball.sh                      # defaults below
#   ./make_mg5_tarball.sh --src <dir> --dest <eos path>
set -u

SRC=${MG5_PATH:-/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2}
DEST=/eos/user/l/llambrec/jetclass/crab_inputs
NAME=""
DRYRUN=false
while [ $# -gt 0 ]; do
    case "$1" in
        --src)  SRC=$2; shift 2 ;;
        --dest) DEST=$2; shift 2 ;;
        --name) NAME=$2; shift 2 ;;
        --dry-run) DRYRUN=true; shift ;;
        -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done
[ -d "$SRC" ] || { echo "ERROR: MG5 install not found at $SRC" >&2; exit 1; }
[ -n "$NAME" ] || NAME=$(basename "$SRC").tar.gz

echo "  source : $SRC  ($(du -sh "$SRC" 2>/dev/null | cut -f1))"
echo "  tarball: $DEST/$NAME"
echo "  jobs will fetch: root://eosuser.cern.ch/$DEST/$NAME"
$DRYRUN && { echo "  (dry run, nothing written)"; exit 0; }

mkdir -p "$DEST"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
echo "  packing (this takes a few minutes for ~850 MB)..."
# -C so the tarball unpacks to a single directory named after the install
tar -czf "$TMP/$NAME" -C "$(dirname "$SRC")" "$(basename "$SRC")" || { echo "ERROR: tar failed" >&2; exit 1; }
echo "  packed: $(du -sh "$TMP/$NAME" | cut -f1)"
cp "$TMP/$NAME" "$DEST/$NAME" || { echo "ERROR: could not write to $DEST" >&2; exit 1; }
echo "  staged: $DEST/$NAME"
echo
echo "pass it to build_simpack.py with:"
echo "  --mg5-url root://eosuser.cern.ch/$DEST/$NAME"
