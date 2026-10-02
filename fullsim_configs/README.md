# FullSim backend: CMS full simulation with open tools only

This directory holds everything the `fullsim` backend of `run.sh` needs to run
CMS full simulation, reconstruction **and** the HLT inside CMSSW, starting from
the same generated events (`gen_configs/`) the Delphes backend reconstructs and
writing the same ntuple schema.

Nothing here needs a CERN account or CMS membership. That was the requirement
that shaped every choice below, so each ingredient is named with where it comes
from and how to get a local copy.

```
./run.sh fullsim jetclass2/train_qcd 20 10 0            # 20 events, 2 batches
python run_condor.py --backend fullsim --proc jetclass2/train_qcd --nevent 20 \
    --batch-size 10 --jobnum 0 --output-path /eos/user/.../output_fullsim_test
```

## What it costs

About **2 minutes of CPU per event** without pile-up (GEN,SIM ~70 s, DIGI+L1+HLT
~30 s, RECO ~38 s), i.e. three to four orders of magnitude more than Delphes.
A 10M-jet dataset is of order 20 CPU-years; this backend is for reference samples
and validation, not for replacing the Delphes production.

## The three ingredients, and where they come from

### 1. Software: the open-data CMSSW container

`cmsopendata/cmssw_10_6_30-slc7_amd64_gcc700` on Docker Hub, used here through
the CVMFS unpacked mirror
`/cvmfs/unpacked.cern.ch/registry.hub.docker.com/cmsopendata/cmssw_10_6_30-slc7_amd64_gcc700:latest`.
It provides the SLC7 userland CMSSW_10_6_30 needs. Override with
`FULLSIM_CONTAINER` (and `FULLSIM_CONTAINER_CMD` for `apptainer`/`singularity`).

CMSSW itself is taken from `/cvmfs/cms.cern.ch` (`FULLSIM_CMSSW_DIR`); the
container also bundles its own copy of the release, which is what makes a fully
CVMFS-free installation possible.

### 2. Conditions: two open condition databases

| global tag | portal record | file | size |
|---|---|---|---|
| `102X_upgrade2018_design_v9` (2018 MC, the one in charge) | [opendata.cern.ch/record/1807](https://opendata.cern.ch/record/1807) | `102X_upgrade2018_design_v9.db` | 1.00 GB |
| `106X_mcRun2_asymptotic_v17` (2016 UL MC, gap-filler) | [opendata.cern.ch/record/1819](https://opendata.cern.ch/record/1819) | `106X_mcRun2_asymptotic_v17.db` | 0.66 GB |

Both are served over plain HTTPS at
`https://opendata.cern.ch/eos/opendata/cms/conddb/<file>.db` and are mirrored
byte-identically on `/cvmfs/cms-opendata-conddb.cern.ch/`, which is the default
(`FULLSIM_CONDDB`). To run without CVMFS, download the two files into a directory
and point `FULLSIM_CONDDB` at it. The full index of them is the
[condition database guide](https://opendata.cern.ch/docs/cms-guide-for-condition-database).

Note the container bundles only the 2016 UL file, not the 2018 one.

### 3. Generator: our own events

`patch_gen.py` replaces the internal Pythia8 generator by `MCFileSource` reading
the `events.hepmc` that `gen_configs/` already produces, so both backends start
from literally the same generated events and the physics generation is not
duplicated in CMSSW.

## How two global tags are used at once

Only one global tag is ever active. A global tag is a named mapping
`record -> tag` (with validity intervals), and `process.GlobalTag.toGet` can
override individual records, each with **its own** `connect`. So "2018 with a
2016 fallback" means the 2018 tag plus ~50 per-record overrides pointing at the
2016 file. `patch_cond.py` builds that list automatically by diffing the two
tags' mappings and overriding only records the 2018 tag lacks **entirely**: no
geometry, alignment or channel-status payload ever comes from the wrong year. The
gap-filled records are year-independent detector-response parameterisations
(ECAL pulse shape, SiStrip APV simulation parameters, e/gamma regressions, b-tag
payloads). The one physics-relevant explicit override is the PF calibration,
where the 2018 and 2016 payloads are the same 2017 calibration vintage in two
different encodings and the 2018 one makes this release assert.

## Files

| file | what it does |
|---|---|
| `patch_cond.py` | all the conditions fixes (7 of them, each documented in the file), `set_beamspot()`, `prune_hlt()` |
| `patch_hlt.py` | adds the unconditional HLT AK8-jet and PF-vertex paths, and keeps the HLT products in the AODSIM output |
| `patch_gen.py` | reads the generator-level event from our own HepMC file |
| `run_chain.sh` | the CMSSW side: `setup` (write the configs, build the ntuplizer) and `batch <i>` (GEN,SIM -> DIGI,L1,HLT -> RECO -> ntuple) |

The ntuplizer itself is `fullsim_analyzers/makeNtuplesFullSim.cc`.

## Why HLT, not scouting

The 2018 **scouting** format (`ScoutingParticle`) stores only
`(pt, eta, phi, m, pdgId, vertex)` — it has no impact parameters at all, and its
jets are AK4. But `HLTScoutingPFProducer` is only a packer: it reads
`reco::PFCandidate` from `hltParticleFlow` and throws the rest away to fit the
online bandwidth budget. Since we run the HLT ourselves that budget does not
apply, so `patch_hlt.py` keeps the real HLT objects instead. That gives AK8 jets
natively (`hltAK8PFJets`, which the `HLT_AK8PFJet*` paths use), constituents with
a `reco::TrackRef` and hence full-precision `dxy`/`dz`, and the HLT PF primary
vertex. The scouting products are still written as well, so the two views can be
compared in the same file. Physics-wise they are the same objects: the scouting
stream is a compressed view of exactly these candidates.

## Caveats

1. **No pile-up.** Deliberate (it would multiply an already expensive job), but
   it is the biggest difference from a real CMS sample, and it is what drove the
   offline-vs-HLT differences this whole study is about. Without pile-up
   `ak8PFJetsCHS` is effectively plain anti-kT over all PF candidates, so the
   CHS-vs-PUPPI difference from the Delphes side does not bite either.
2. **2018 is the latest open year**, and its open conditions are *design*
   conditions (ideal alignment, no misalignment or noise, zero-emittance beam).
   The 2018 HLT reconstruction is not identical to the Run-3 one.
3. **`jet_sdmass` and `jet_tau1..4` are recomputed** by the ntuplizer with
   fastjet, because AODSIM does not store them for AK8 and they do not exist at
   all for HLT jets. The parameters are the Delphes cards' ones, so the two
   backends' columns mean the same thing.
4. **Jet energies are uncorrected on both sides.** `ak8PFJetsCHS` in AODSIM and
   `hltAK8PFJets` are raw jets; no JEC is applied, on purpose, so that the
   offline-vs-HLT comparison this sample is for is like-for-like. That differs
   from the Delphes ntuples, whose jets carry the cards' own jet-energy scale,
   so an absolute comparison of `jet_pt` between the two backends is off by a
   JEC factor (~5-10%), and the 120 GeV jet selection is applied to raw pT here.
   The menu does produce a corrected HLT collection with the design-conditions
   JEC (`hltAK8PFJetsCorrected`), and the ntuplizer takes any `reco::PFJet`
   collection, so `NT_JETS`/`NT_HLTJETS` can point at corrected jets instead.
