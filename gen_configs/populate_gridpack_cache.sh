#!/bin/bash -x

# Download, extract and patch a precompiled JetClass-I gridpack from
# https://github.com/jet-universe/jetclass_generation into the persistent
# GRIDPACK_CACHE. A no-op if that process' entry already exists.
#
# Called both by run_gen_precompiled.sh, as its step1, and by
# ../download_gridpack.py, which populates many entries ahead of time without
# generating events. Keeping it in one place is what makes the two agree.
#
# MG5_PATH must be set: it replaces the gridpack's hardcoded original install
# path. GRIDPACK_CACHE defaults as below, the same default
# run_gen_precompiled.sh uses.

GRIDPACK_NAME=$1

if [ -z "$GRIDPACK_NAME" ]; then
    echo "ERROR: usage: populate_gridpack_cache.sh GRIDPACK_NAME" >&2
    exit 1
fi
if [ -z "$MG5_PATH" ]; then
    echo "ERROR: MG5_PATH must be set before calling populate_gridpack_cache.sh" >&2
    exit 1
fi

GRIDPACK_CACHE=${GRIDPACK_CACHE:-/eos/user/l/llambrec/jetclass/gridpack_cache}
CACHED_PROC=$GRIDPACK_CACHE/$GRIDPACK_NAME/proc

if [ -d "$CACHED_PROC" ]; then
    echo "Gridpack cache for $GRIDPACK_NAME already populated at $CACHED_PROC"
    exit 0
fi

echo "Populating gridpack cache for $GRIDPACK_NAME"
DLDIR=$(mktemp -d)
curl -sL "https://raw.githubusercontent.com/jet-universe/jetclass_generation/main/gridpacks/${GRIDPACK_NAME}.tar.gz" -o $DLDIR/gridpack.tar.gz
tar -xzf $DLDIR/gridpack.tar.gz -C $DLDIR
if [ ! -d "$DLDIR/$GRIDPACK_NAME" ]; then
    echo "ERROR: expected $DLDIR/$GRIDPACK_NAME after extracting gridpack.tar.gz - download or extraction of $GRIDPACK_NAME failed" >&2
    rm -rf $DLDIR
    exit 1
fi
# The gridpack hardcodes its original, inaccessible MG5 install path here;
# repoint it at ours.
sed -i "s#/afs/cern.ch/work/h/hqu/tools/madgraph/LCG100/MG5_aMC_v3_1_1#$MG5_PATH#g" \
    $DLDIR/$GRIDPACK_NAME/Cards/me5_configuration.txt
mkdir -p $GRIDPACK_CACHE/$GRIDPACK_NAME
# Move into place under a unique name and then rename, so jobs racing to
# populate the same entry cannot clobber each other. If another job won the
# race, discard our copy.
UNIQUE=proc.tmp.$$_$RANDOM
mv $DLDIR/$GRIDPACK_NAME $GRIDPACK_CACHE/$GRIDPACK_NAME/$UNIQUE
mv -T $GRIDPACK_CACHE/$GRIDPACK_NAME/$UNIQUE $CACHED_PROC 2>/dev/null \
    || rm -rf $GRIDPACK_CACHE/$GRIDPACK_NAME/$UNIQUE
rm -rf $DLDIR

if [ -d "$CACHED_PROC" ]; then
    echo "Gridpack cache for $GRIDPACK_NAME populated at $CACHED_PROC"
else
    echo "ERROR: gridpack cache for $GRIDPACK_NAME still missing after populate attempt (lost the race and the winner's copy is also missing?)" >&2
    exit 1
fi
