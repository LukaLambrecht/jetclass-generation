# JetClass generation: installation notes

Setup instructions for the JetClass dataset generation pipeline (MadGraph + Pythia8 + Delphes/Geant).

**Requirements for different generation setups and detector backends**  
Note that depending on the workflow, not all these installation steps might be needed.
- For the generation step, some processes (e.g. QCD background) use pure Pythia8 and do not need Madgraph.
  This depends purely on the generated process independent of the detector backend.
- For the detector simulation , the `delphes` option needs a Delphes installation while the `fullsim` option does not.
- Moreover, for the `fullsim` backend, depending on how the generation and simulation are wired together,
  a Pythia8 installation might not be needed as it is implicit in CMSSW.
- See [`fullsim_configs/README.md`](fullsim_configs/README.md) for more information on installing and using the `fullsim` backend itself.

## 1. Clone the generation repo

```bash
git clone https://github.com/LukaLambrecht/jetclass-generation.git
```
Make sure to get and switch to the `offline-and-hlt` branch!

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

Note: the example file provided here requires CERN EOS access, but any other file containing pileup events will do.

The symlink must be created inside your Delphes install directory
itself (i.e. `$DELPHES_PATH/`), named exactly `MinBias_100k.pileup`:

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
# ./run.sh <backend> [process_name] [num_tot_events] [num_events_per_gen_step] [job_num]
./run.sh delphes jetclass2/train_higgs2p 10 10 0
```

Note the process name is relative to `gen_configs/` and must not include a `gen_configs/`
prefix — `./run.sh gen_configs/jetclass2/train_higgs2p ...` fails with a
`cp: cannot stat '.../gen_configs/gen_configs/jetclass2/train_higgs2p/*'` error, because `run.sh`
already resolves `$PROC` under its own `gen_configs/` directory.

A successful run produces, under `$OUTPUT_PATH/$PROC/<backend options>/`:
- `ntuple_$JOBNUM.root` — the flat, jet-based ntuple (see step 8).
- `events_delphes_$JOBNUM.root` — the raw Delphes output, only with
  `keep_intermediate` (`run.sh`'s 8th argument) set to `true`.

## 8. Ntuple production (built into run.sh)

`run.sh` now runs an ntuplizer as its last step, converting
the Delphes ROOT file (or equivalently, an AODSIM ROOT file in the `fullsim` backend)
into the flat ntuple format described in the
[sophon README](https://github.com/jet-universe/sophon?tab=readme-ov-file#variable-details).

No extra action is needed — it's part of step 7 above, but in case manual running of this step is needed,
this is how it goes:

```bash
cd delphes_analyzers
source /cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh
export ROOT_INCLUDE_PATH=$ROOT_INCLUDE_PATH:/cvmfs/sft.cern.ch/lcg/releases/delphes/3.5.1pre09-9fe9c/x86_64-el9-gcc13-opt/include
root -b -q 'makeNtuples.C++("events_delphes.root", "ntuple.root", "JetPUPPIAK8", "GenJetAK8", true)'
```

## 9. The FullSim backend (CMSSW)

In case your machine has CVMFS and `apptainer` installed, nothing extra is needed.

```bash
./run.sh fullsim jetclass2/train_qcd 4 2 0
```

It pulls CMSSW_10_6_30 and an SLC7 userland from the open-data container image on
`/cvmfs/unpacked.cern.ch`, and the conditions from `/cvmfs/cms-opendata-conddb.cern.ch`.

To run somewhere without CVMFS, you can instead fetch the container from Docker Hub
(`cmsopendata/cmssw_10_6_30-slc7_amd64_gcc700`) and the two condition databases
from the CERN Open Data portal, and point `FULLSIM_CONTAINER` / `FULLSIM_CONDDB`
at your copies. The databases are published as ordinary xrootd-readable files.

```bash
xrdcp root://eospublic.cern.ch//eos/opendata/cms/conddb/102X_upgrade2018_design_v9.db .  # 1.00 GB, record 1807
xrdcp root://eospublic.cern.ch//eos/opendata/cms/conddb/106X_mcRun2_asymptotic_v17.db .  #  664 MB, record 1819
```

See [`fullsim_configs/README.md`](fullsim_configs/README.md) for more information.

## 10. Installing an alternate MG5/Pythia8 toolchain (e.g. MG5 3.1.1, for toolchain-comparison tests)

Outdated and no longer needed, but kept here for later reference.

### 10.1. Install MG5 3.1.1 itself

Same as step 2, but into its own directory (e.g. `MG5_aMC_v3_1_1` next to `MG5_aMC_v3_7_2`),
and do not run `install pythia8`/`install lhapdf6` yet.

```bash
wget https://launchpad.net/mg5amcnlo/3.0/3.1.x/+download/MG5_aMC_v3.1.1.tar.gz
tar xzf MG5_aMC_v3.1.1.tar.gz
```

### 10.2. Set up a durable local HEPToolsInstaller copy

Problem: `install <tool>` inside `mg5_aMC` does not use anything bundled with the MG5
release. Every single time it's called, it re-downloads a "maintained online" installer script,
overwriting whatever was there before, so this installer is not version-pinned to MG5 3.1.1.
Any patches applied would be overwritten.

`mg5_aMC`'s `install` command supports a `--local` flag for exactly this.
This only works if that directory already exists, so it has to be seeded once:

```bash
# from outside MG5_aMC_v3_1_1, i.e. the same directory MG5_aMC_v3_1_1 itself lives in
wget http://madgraph.phys.ucl.ac.be//Downloads/HEPToolsInstaller/HEPToolsInstaller_V168.tar.gz
tar xzf HEPToolsInstaller_V168.tar.gz   # extracts to ./HEPToolsInstallers/
rm HEPToolsInstaller_V168.tar.gz
```

Every `install <tool>` call against this MG5 install should then use `--local`
(and `--force` to reinstall over an existing copy).

### 10.3. Patch the durable installer copy

Edit `<jetclass_root>/HEPToolsInstallers/HEPToolInstaller.py`, before installing pythia.

**a. Pin the Pythia8 version.** The installer's own default pythia8 version at the time of
writing is too recent for MG5 3.1.1, and separately, an old version contemporary with MG5 3.1.1 (8.244)
turns out to be too old: its LHE reader predates MG5 3.1.1 itself by ~1.5 years, and crashes.
A suitable version seems to be **8.306**.
```python
'version': '8306',
```

**b. Add back the missing compiler optimization flags.** `install_pythia8()` omits any optimization flag,
unlike the (different/newer) online installer that MG5 3.7.2 uses.
```python
cxx_common = ['-ldl','-fPIC',_cpp_standard_lib,'-std=c++11','-O2','-pthread']
```

With both patches in place:
```bash
cd MG5_aMC_v3_1_1
echo "install pythia8 --local --force" | ./bin/mg5_aMC
```
Verify:
```bash
grep -o "\-\-cxx-common='[^']*'" HEPTools/pythia8/pythia8_install.log
# should show: -ldl -fPIC -lstdc++ -std=c++11 -O2 -pthread -DHEPMC2HACK
cat HEPTools/MG5aMC_PY8_interface/PYTHIA8_VERSION_ON_INSTALL   # should read 8.306
```

### 10.4. Point the generation pipeline at the new install

`run.sh`'s `MG5_PATH` can be a pre-set environment variable, so the new
install can be used without editing the file:

```bash
MG5_PATH=/path/to/MG5_aMC_v3_1_1 GRIDPACK_CACHE=/path/to/a/SEPARATE/gridpack/cache \
    ./run.sh jetclass1/TTBarLep/precompiled 1000 1000 999 JetClassI /path/to/test_output false
```

`GRIDPACK_CACHE` must point at a separate cache directory from the main one -
reusing the main cache would silently keep serving MG5 3.7.2-built gridpacks.

For actual condor production runs (rather than one-off local tests), `run_condor.py`/
`run_condor_loop.py`'s `--extra-env MG5_PATH=...,GRIDPACK_CACHE=...` flag does the same thing per
job, e.g.:
```bash
python run_condor_loop.py --procs jetclass1/HToBB/precompiled --njobs 10 --nevents-per-job 50000 \
    --output-path /path/to/output --batch-size 12500 --delphes-cards JetClassI \
    --extra-env MG5_PATH=/path/to/MG5_aMC_v3_1_1,GRIDPACK_CACHE=/path/to/a/SEPARATE/gridpack/cache
```
