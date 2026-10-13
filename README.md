# JetClass dataset generation for offline vs HLT studies

### General information
For general information on JetClass dataset production, see the [main branch](https://github.com/LukaLambrecht/jetclass-generation) of this repository (which is forked from [jet-universe/jetclass2_generation](https://github.com/jet-universe/jetclass2_generation/tree/main)).

### Detector backends
`run.sh`'s first argument selects how the generated events are turned into a
detector-level dataset:

| backend | what it is |
|---|---|
| `delphes` | fast parameterised simulation — every dataset so far was made with this |
| `fullsim` | CMS full simulation, reconstruction and HLT in CMSSW, using only openly available software and conditions — see [`fullsim_configs/README.md`](fullsim_configs/README.md) |

Both write the same ntuple schema, so downstream code does not need to know which
one produced its input.

```bash
./run.sh delphes jetclass2/train_qcd 1000 100 0
./run.sh fullsim jetclass2/train_qcd 4 2 0        # ~2 min of CPU per event

python run_condor.py --backend delphes --proc jetclass2/train_qcd --nevent 1000 \
    --batch-size 100 --jobnum 0 --output-path <...>
```

### Running a full production
Two interchangeable submission routes, with identical job splitting and identical
output, so a dataset made with one matches a dataset made with the other:

| route | where | needs |
|---|---|---|
| [`condor/`](condor/README.md) | lxplus HTCondor | nothing for QCD; an MG5 install for the signal |
| [`crab/`](crab/README.md) | CMS grid, via CRAB | CMS VO membership and a grid proxy |

```bash
# lxplus HTCondor
module load lxbatch/eossubmit
./condor/submit_production_qcd.sh --dry-run        # then without --dry-run
MG5_PATH=/path/to/MG5_aMC_v3_7_2 ./condor/submit_production_higgs2p.sh

# CRAB
voms-proxy-init -voms cms -valid 192:00
./crab/submit_production_qcd.sh
./crab/submit_production_higgs2p.sh
```

Each script takes `--dry-run`, which prints every command it would run without
running any of them - worth doing first, since a full production is thousands of jobs.

### Installation
See the dedicated [installation instructions](INSTALL.md).

Short version: the `fullsim` backend needs **nothing** beyond CVMFS and `apptainer`
(both on lxplus), *except* for the `jetclass2/*` processes, which generate their
events with MadGraph5 + Pythia8 before CMSSW starts and therefore need an MG5 install
(INSTALL.md steps 2-3). The `delphes` backend additionally needs Delphes (steps 4-6).
