# JetClass generation: installation notes

Setup instructions for the JetClass dataset generation
pipeline (MadGraph + Pythia8 + Delphes) on this machine (lxplus / EOS).

## 1. Clone the generation repo

```bash
git clone https://github.com/LukaLambrecht/jetclass-generation.git
```
To do: update with correct branch!

## 2. Install MG5aMC + Pythia8 + LHAPDF

Install outside this repo, e.g. one directory up.

```bash
wget <MG5 tarball URL from launchpad>
tar xzf MG5_aMC_vX.Y.Z.tar.gz
cd MG5_aMC_vX.Y.Z
./bin/mg5_aMC
> install pythia8
> install lhapdf6      # if not already linked to a system install
> exit
```

**Important:** run `./bin/mg5_aMC` from the top-level `MG5_aMC_vX.Y.Z/` directory, not from
inside `bin/`. Launching it from within `bin/` causes `install pythia8` / `install lhapdf6` to
drop everything under `bin/HEPTools/` instead of the standard `HEPTools/` (sibling of `bin/`).
The generation scripts in this repo (`gen_configs/run_gen_default.sh`,
`gen_configs/jetclass2/train_qcd/run_gen.sh`) hardcode `$MG5_PATH/HEPTools/...`, so if your
install ends up under `bin/HEPTools/` you'll get `No such file or directory` errors for
`MG5aMC_PY8_interface` and friends.

If you've already installed into `bin/HEPTools/` (check with `ls MG5_aMC_vX.Y.Z/HEPTools`,
`ls MG5_aMC_vX.Y.Z/bin/HEPTools`), symlink the top level to the real location:

```bash
cd MG5_aMC_vX.Y.Z
for d in bin hepmc include lhapdf6_py3 lib MG5aMC_PY8_interface pythia8 zlib; do
    ln -s ../bin/HEPTools/$d HEPTools/$d
done
```

Also double check that `HEPTools/lib/` has both a `.a` and a `.so` symlink for every installed
tool. On at least one install, the `pythia8` `install` step only created the `libpythia8.a`
symlink in `HEPTools/lib/`, silently omitting `libpythia8.so` (every other tool — HepMC, LHAPDF,
zlib — got both). This makes `MG5aMC_PY8_interface` fail with
`error while loading shared libraries: libpythia8.so: cannot open shared object file`. Fix by
symlinking it in like the others:

```bash
ln -s ../pythia8/lib/libpythia8.so MG5_aMC_vX.Y.Z/HEPTools/lib/libpythia8.so
```

(Adjust the relative path if your `HEPTools/lib` isn't a direct sibling of `HEPTools/pythia8`.)

## 3. Install the 2HDM UFO model

```bash
cp -r <downloaded 2HDM folder> MG5_aMC_vX.Y.Z/models/
```

## 4. Build Delphes (with the `PileUpMerger` patch)

```bash
git clone https://github.com/delphes/delphes.git
cd delphes
git apply /path/to/jetclass-generation/delphes_patches/PileUpMerger_PerEventSeed.patch
make -j4 && cd ..
```

**Do not skip the patch.** The offline and HLT cards set `PerEventSeed true` in
`PileUpMerger`, which makes the offline and HLT Delphes runs of the same event get the same
vertex position and pile-up overlay (so they only differ by detector effects) - see
`delphes_cards/KNOWN_ISSUES.md`, section "Required Delphes patch". Stock Delphes silently
ignores the unknown parameter; `run.sh` therefore checks for the patch and refuses to run
without it. The patch was made against Delphes commit `fb4d95b`; if `git apply` fails on a
newer Delphes, re-apply the (small, self-contained) change to `modules/PileUpMerger.{h,cc}` by
hand. To verify the build:

```bash
grep -ac "PerEventSeed requires a nonzero global RandomSeed" libDelphes.so   # should print 1
```

## 5. Link the pileup file

Requires CERN EOS access. **The symlink must be created inside your Delphes install directory
itself** (i.e. `$DELPHES_PATH/`), named exactly `MinBias_100k.pileup`:

```bash
cd <your Delphes install dir>
ln -s /eos/cms/store/group/upgrade/delphes/PhaseII/MinBias_100k.pileup .
```

`run.sh` does `ln -s $DELPHES_PATH/MinBias_100k.pileup .` inside the per-job workdir to stage the
pileup file where the Delphes card expects it (the card sets `PileUpFile MinBias_100k.pileup`).
If the real symlink lives anywhere other than directly under `$DELPHES_PATH`, that `ln -s` creates
a dangling symlink and Delphes fails with an I/O error trying to open the pileup file.

## 6. Configure run.sh

Open `run.sh` and set the paths it expects:

```bash
less run.sh   # inspect before running — confirm variable names/paths
```

```
MG5_PATH=<path to your MG5_aMC install>
DELPHES_PATH=<path to your Delphes install>
OUTPUT_PATH=<where output ROOT files should go>

LHAPDFCONFIG=$MG5_PATH/HEPTools/lhapdf6_py3/share/LHAPDF/lhapdf.conf
LHAPDF_DATA_PATH=$MG5_PATH/HEPTools/lhapdf6_py3/share/LHAPDF
PYTHIA8DATA=$MG5_PATH/HEPTools/pythia8/share/Pythia8/xmldoc
```

## 7. Run a test job

```bash
# ./run.sh [process_name] [num_tot_events] [num_events_per_gen_step] [job_num]
./run.sh jetclass2/train_higgs2p 10 10 0
```

Note the process name is relative to `gen_configs/` and must **not** include a `gen_configs/`
prefix — `./run.sh gen_configs/jetclass2/train_higgs2p ...` fails with a
`cp: cannot stat '.../gen_configs/gen_configs/jetclass2/train_higgs2p/*'` error, because `run.sh`
already resolves `$PROC` under its own `gen_configs/` directory.

A successful run produces, under `$OUTPUT_PATH/$PROC/`:
- `events_delphes_$JOBNUM.root` — the raw Delphes output.
- `ntuple_$JOBNUM.root` — the flat, jet-based ntuple produced from it (see step 8).

## 8. Ntuple production (built into run.sh)

`run.sh` now runs `delphes_analyzers/makeNtuples.C` automatically as its last step, converting
the Delphes ROOT file into the flat ntuple format described in the
[sophon README](https://github.com/jet-universe/sophon?tab=readme-ov-file#variable-details). No
extra action is needed — it's part of step 7 above. This runs the same macro the repo's own
`README.md` documents for manual use:

```bash
cd delphes_analyzers
source /cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh
export ROOT_INCLUDE_PATH=$ROOT_INCLUDE_PATH:/cvmfs/sft.cern.ch/lcg/releases/delphes/3.5.1pre09-9fe9c/x86_64-el9-gcc13-opt/include
root -b -q 'makeNtuples.C++("events_delphes.root", "ntuple.root", "JetPUPPIAK8", "GenJetAK8", true)'
```

## 9. Installing an alternate MG5/Pythia8 toolchain (e.g. MG5 3.1.1, for toolchain-comparison tests)

Central JetClass was originally produced with an older MG5/Pythia8 combination than the "main"
install from step 2 above (MG5 3.7.2). To reproduce that more closely - e.g. to check whether the
generator/shower vintage itself explains a discrepancy against central JetClass - it's useful to
have a **second, separate** MG5 install (here: MG5 3.1.1, released 2021-05-28) alongside the main
one, without disturbing it. This section documents that procedure end to end, including the
pitfalls hit getting it working.

### 9.1. Install MG5 3.1.1 itself

Same as step 2, but into its own directory (a sibling of the main install, not nested inside it -
e.g. `MG5_aMC_v3_1_1` next to `MG5_aMC_v3_7_2`), and **do not** run `install pythia8`/
`install lhapdf6` yet - those need extra setup first (9.2-9.3 below) or you'll hit the crash
described there.

```bash
wget https://launchpad.net/mg5amcnlo/3.0/3.1.x/+download/MG5_aMC_v3.1.1.tar.gz
tar xzf MG5_aMC_v3.1.1.tar.gz
```

(Adjust the launchpad URL/branch if 3.1.1 has since been moved to a different series' download
page - the `3.0/3.1.x` path reflects where it lived at the time of writing.)

### 9.2. Set up a durable `--local` HEPToolsInstaller copy

**Problem:** `install <tool>` inside `mg5_aMC` does *not* use anything bundled with the MG5
release. Every single time it's called, it re-downloads a "maintained online" installer script
(as of writing: `http://madgraph.phys.ucl.ac.be//Downloads/HEPToolsInstaller/HEPToolsInstaller_V168.tar.gz`)
into `MG5_PATH/HEPTools/HEPToolsInstallers/`, completely overwriting whatever was there before -
so this installer is **not** version-pinned to MG5 3.1.1, and any patch made directly to that
downloaded copy is silently wiped out by the next `install` call (found the hard way, twice).

Two of the patches this toolchain actually needs (9.3 below) have to survive across repeated
`install` retries. `mg5_aMC`'s `install` command supports a `--local` flag for exactly this: with
`--local`, instead of using the freshly re-downloaded copy, it copies the installer from a fixed
sibling directory of `MG5_PATH` itself - `pjoin(MG5_PATH, os.path.pardir, 'HEPToolsInstallers')`,
i.e. `<MG5_PATH>/../HEPToolsInstallers` - which is **not** touched by the normal re-download/
overwrite behavior. This only works if that directory already exists, though (`--local` copies
*from* it, it does not create it) - so it has to be seeded once, manually:

```bash
# from outside MG5_aMC_v3_1_1, i.e. the same directory MG5_aMC_v3_1_1 itself lives in
wget http://madgraph.phys.ucl.ac.be//Downloads/HEPToolsInstaller/HEPToolsInstaller_V168.tar.gz
tar xzf HEPToolsInstaller_V168.tar.gz   # extracts to ./HEPToolsInstallers/
rm HEPToolsInstaller_V168.tar.gz
```

Every `install <tool>` call against this MG5 install should then use `--local` (and `--force` to
reinstall over an existing copy), e.g. `install pythia8 --local --force` - never a bare
`install pythia8`, or the fixes below get lost.

### 9.3. Patch the durable installer copy

Edit `<jetclass_root>/HEPToolsInstallers/HEPToolInstaller.py` (the sibling directory from 9.2, NOT
anything under `MG5_aMC_v3_1_1/`) with the following, before ever running `install pythia8
--local`:

**a. Pin the Pythia8 version.** The installer's own default pythia8 version at the time of
writing is too recent to be the version actually bundled with MG5 3.1.1 at release (2021-05-28),
and separately, an old version contemporary with MG5 3.1.1 (8.244, Dec 2019) turns out to be too
*old*: its LHE reader predates MG5 3.1.1 itself by ~1.5 years, and can't parse the LHEF 3.0 output
this MG5 version's gridpacks produce - `Pythia::init()` hard-fails with "Les Houches initialization
failed", and the interface then loops forever calling `next()` on the uninitialized instance
(looks like a hang, not a crash - burned 30+ minutes of wall time before being diagnosed via
`gdb -p <pid> -batch -ex "bt"` on the stuck process). The version actually used here, verified to
build and run cleanly against this MG5 version with no source patches needed, is **8.306**
(~Sep 2021, genuinely post-dates MG5 3.1.1). In the `_HepTools['pythia8']` dict, set:
```python
'version': '8306',
```

**b. Add back the missing compiler optimization flags.** `install_pythia8()`'s own construction of
Pythia8's `./configure --cxx-common=...` (search for `cxx_common = ['-ldl','-fPIC',_cpp_standard_lib]`)
omits **any** optimization flag - no `-O2`, no `-std=c++11`, no `-pthread` - unlike the (different/
newer) online installer that MG5 3.7.2 uses, whose own `--cxx-common` includes all three. With no
`-O` flag at all, gcc defaults to `-O0`: the resulting Pythia8 build is unoptimized, and since the
parton shower/hadronization code is CPU-bound C++, this cost a **~3-10x slowdown** in practice
(caught only because production jobs were taking hours where the reference MG5 3.7.2 toolchain
took tens of minutes - see the `output_jetclass1_5M_sync_mg311` validation history). Fix:
```python
cxx_common = ['-ldl','-fPIC',_cpp_standard_lib,'-std=c++11','-O2','-pthread']
```

With both patches in place:
```bash
cd MG5_aMC_v3_1_1
echo "install pythia8 --local --force" | ./bin/mg5_aMC
```
This one call also cascades straight into rebuilding `mg5amc_py8_interface` against the new
Pythia8 automatically - no separate `install mg5amc_py8_interface` call needed. Verify both took
effect:
```bash
grep -o "\-\-cxx-common='[^']*'" HEPTools/pythia8/pythia8_install.log
# should show: -ldl -fPIC -lstdc++ -std=c++11 -O2 -pthread -DHEPMC2HACK
cat HEPTools/MG5aMC_PY8_interface/PYTHIA8_VERSION_ON_INSTALL   # should read 8.306
```

If, instead, you need an *older* Pythia8 version than 8.306 for some other test: two more issues
were hit and fixed along the way while debugging 8.244 specifically, before settling on 8.306 -
kept here in case they resurface for another old version:
- The bundled/offline installer's URL for some older pythia8 tarballs (`http://home.thep.lu.se/
  ~torbjorn/pythia8/pythia8<VVV>.tgz`) is dead; `https://pythia.org/releases/pythia8<major>/
  pythia8<VVV>.tgz` works instead.
- Older Pythia8 releases' own C++ API differs enough (raw `UserHooks*` vs `shared_ptr<UserHooks>`
  for `setUserHooksPtr`, no implicit `<memory>` include) that `MG5aMC_PY8_interface.cc` needs
  small source patches to compile against them at all. Not needed for 8.306.
- `compile.py` (bundled inside the downloaded `MG5aMC_PY8_interface_V1.3.tar.gz`) and
  `Makefile_mg5amc_py8_interface_static` disagree about the expected format of the `HEPMC2_LIB`
  Makefile.inc variable (bare directory vs. full link flags) for versions of HepMC/Pythia8 without
  a shared library - if hit again (error: "The version of HEPMC2 linked to Pythia8 seems not to
  include a static library"), keep `HEPMC2_LIB` bare and use the (otherwise dead-code)
  `CUSTOM_STATIC_HEPMC2_LIB` variable directly in the Makefile recipe instead, plus an explicit
  `-L$(GZIP_LIB) -lz`.

### 9.4. Point the generation pipeline at the new install

`run.sh`'s `MG5_PATH` respects a pre-set environment variable (see its own comment), so the new
install can be used **without editing any repo file**:

```bash
MG5_PATH=/path/to/MG5_aMC_v3_1_1 GRIDPACK_CACHE=/path/to/a/SEPARATE/gridpack/cache \
    ./run.sh jetclass1/TTBarLep/precompiled 1000 1000 999 JetClassI /path/to/test_output false
```

`GRIDPACK_CACHE` must point at a **separate** cache directory from the main one -
`populate_gridpack_cache.sh`/`run_gen_precompiled.sh` short-circuit if a process is already
cached, so reusing the main cache would silently keep serving MG5 3.7.2-built gridpacks. Populate
it once per process before running:
```bash
MG5_PATH=/path/to/MG5_aMC_v3_1_1 GRIDPACK_CACHE=/path/to/a/SEPARATE/gridpack/cache \
    bash gen_configs/populate_gridpack_cache.sh jetclass1/HToBB
```
(repeat per process - this changes the MG5 install path baked into the gridpack's own
`me5_configuration.txt`, not the physics/process definition itself, so it's a like-for-like
comparison against the same processes in the main cache.)

For actual condor production runs (rather than one-off local tests), `run_condor.py`/
`run_condor_loop.py`'s `--extra-env MG5_PATH=...,GRIDPACK_CACHE=...` flag does the same thing per
job, e.g.:
```bash
python run_condor_loop.py --procs jetclass1/HToBB/precompiled --njobs 10 --nevents-per-job 50000 \
    --output-path /path/to/output --batch-size 12500 --delphes-cards JetClassI \
    --extra-env MG5_PATH=/path/to/MG5_aMC_v3_1_1,GRIDPACK_CACHE=/path/to/a/SEPARATE/gridpack/cache
```

