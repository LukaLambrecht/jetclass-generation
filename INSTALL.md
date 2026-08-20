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

## 4. Build Delphes

```bash
git clone https://github.com/delphes/delphes.git
cd delphes && make -j4 && cd ..
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
