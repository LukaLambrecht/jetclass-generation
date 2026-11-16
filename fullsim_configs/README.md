# FullSim backend: CMS full simulation

This directory holds everything the `fullsim` backend of `run.sh` needs to run CMS full simulation inside CMSSW.
The workflow implemented here uses only open-data and open-conditions tools.

**Example use**
```
./run.sh fullsim jetclass2/train_qcd 20 10 0            # 20 events, 2 batches
python run_condor.py --backend fullsim --proc jetclass2/train_qcd --nevent 20 \
    --batch-size 10 --jobnum 0 --output-path /eos/user/.../output_fullsim_test
```

**What it costs**  
About 1-2 minutes of CPU per event without pile-up (GEN,SIM ~70 s, DIGI+L1+HLT ~30 s, RECO ~38 s), i.e. three to four orders of magnitude more than Delphes.

### 1. Software: the open-data CMSSW container

`cmsopendata/cmssw_10_6_30-slc7_amd64_gcc700` from Docker Hub.
It provides the SLC7 container CMSSW_10_6_30 needs.

As an optional equivalent, in case CVMFS is available, the container can be taken from the CVMFS unpacked mirror
(`/cvmfs/unpacked.cern.ch/registry.hub.docker.com/cmsopendata/cmssw_10_6_30-slc7_amd64_gcc700:latest`),
and CMSSW itself can be taken from `/cvmfs/cms.cern.ch`.

### 2. Conditions: two open condition databases

| global tag | portal record | file | size |
|---|---|---|---|
| `102X_upgrade2018_design_v9` (2018 MC, main) | [opendata.cern.ch/record/1807](https://opendata.cern.ch/record/1807) | `102X_upgrade2018_design_v9.db` | 1.00 GB |
| `106X_mcRun2_asymptotic_v17` (2016 UL MC, backup) | [opendata.cern.ch/record/1819](https://opendata.cern.ch/record/1819) | `106X_mcRun2_asymptotic_v17.db` | 0.66 GB |

Both are served over plain HTTPS at `https://opendata.cern.ch/eos/opendata/cms/conddb/<file>.db`.
See also [condition database guide](https://opendata.cern.ch/docs/cms-guide-for-condition-database) for more info.

As an optional equivalent, in case CVMFS is available, they are mirrored on `/cvmfs/cms-opendata-conddb.cern.ch/`.

### 3. Generator: external events

`patch_gen.py` replaces the internal Pythia8 generator by `MCFileSource` reading
the `events.hepmc` that `gen_configs/` already produces.

## How two global tags are used at once

Some items are missing in the 2018 global tag, that are required in the used CMSSW release.
This is circumvented by `patch_cond.py`, which finds the missing payloads and replaces them by the ones from the 2016 UL global tag.
This concerns only minor payloads needed for technical reasons; no geometry, alignment or channel-status payload ever comes from a different year.

## Generator sources

A process under `gen_configs/` produces its generator-level events in one of two ways:
| kind | how events are made | supported backends |
|---|---|---|
| `hepmc` | standalone MG5_aMC + Pythia8 writes `events.hepmc`, fed to CMSSW via `MCFileSource` (`patch_gen.py`) | delphes **and** fullsim |
| `cmssw_fragment` | CMSSW runs the Pythia8 fragment itself, inside the GEN step - no external generator, no HepMC file | **fullsim only** |

For a fragment process the backend creates a scram developer area and installs the
fragment as `Configuration/GenProduction/python/<name>.py`, which is how cmsDriver
expects to import it.

Every batch gets a fresh random seed for all random-number modules (generator,
vertex smearing, GEANT4, mixing) via CMSSW's `RandomNumberServiceHelper`, logged as
`seed: <n>`.

## Pile-up

No pileup at GEN-SIM level, then mix at the DIGI step.
The 2018 pile-up distribution is available in the CMSSW release, but the minimum-bias events have to be supplied externally, something like this:
```
cmsDriver.py ... --step DIGI,L1,DIGI2RAW,HLT:GRun --era Run2_2018 \
    --pileup 2018_25ns_JuneProjectionFull18_PoissonOOTPU \
    --pileup_input file:minbias.root
```

**What it costs:** the configured window is `minBunch -12 .. maxBunch +3` (16 bunch
crossings) with a distribution mean of about 35, i.e. about 560 minimum-bias overlays per
hard-scatter event**. The DIGI+HLT step cost roughly +70% in a very small test.

**Todo before running this:** the release only ships `MinBias_13TeV_pythia8_TuneCUETP8M1_cfi`,
while our hard-scatter fragments use CP5. Need to build a CP5 minimum-bias fragment.

**Status:** keep open as backup option if needed, but not run yet.

Note: a centrally provided premixed dataset is available here:
`/Neutrino_E-10_gun/RunIISummer20ULPrePremix-UL16_106X_mcRun2_asymptotic_v13-v1/PREMIX`
([record 30595](https://opendata.cern.ch/record/30595)).
It is generated with CMSSW_10_6_30 and 106X_mcRun2_asymptotic_v17.
However, it cannot currently be used here, for two independent reasons:
1. It is UL2016, and this release has no 2016 HLT menu.
2. Missing record: the `PreMixingModule` throws `NoRecord` for
   `SiPixelStatusScenarioProbabilityRcd`, which is in neither open conditions tag.

## Caveats

1. **2018 is the latest open year**, and its open conditions are *design*
   conditions (ideal alignment, no misalignment or noise, zero-emittance beam).
   The 2018 HLT reconstruction is not identical to the Run-3 one.
2. **`jet_sdmass` and `jet_tau1..4` are recomputed** by the ntuplizer with
   fastjet, because AODSIM does not store them for AK8 and they do not exist at
   all for HLT jets. However, these variables are not really used anywhere downstream.
3. **Jet energies are uncorrected on both sides.** `ak8PFJetsCHS` in AODSIM and
   `hltAK8PFJets` are raw jets; no JEC is applied.
