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

### Installation
See the dedicated [installation instructions](INSTALL.md).
