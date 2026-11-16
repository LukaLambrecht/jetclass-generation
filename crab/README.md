# CRAB submission for the fullsim backend

Submission tools using CRAB instead of HTCondor.

## How it works

CRAB normally runs `cmsRun <psetName>`. `JobType.scriptExe` overrides that with an
arbitrary script, which is what lets the three-step chain plus the standalone
ntuplizer run as one job. `pset.py` stays as a formal requirement - and because CRAB
reads the output file name from it, its `ntuple.root` must stay in sync with what
`run_job.sh` leaves behind.

**Simpack:** A self-contained directory holding everything a job needs, because
`JobType.inputFiles` has to be an explicit closed set:

```
<simpack>/
    crab_config.py        rendered by build_simpack.py
    crab_submit.sh        sets up a CRAB environment and submits
    pset.py               dummy; CRAB takes the output file name from it
    run_in_container.sh   scriptExe - runs on the worker node, launches the container
    run_job.sh            inside the container - run_chain.sh setup + batches + hadd
    payload/cfg/          patch_*.py, run_chain.sh, <fragment>.py
    payload/ana/          ntuplizer sources, incl. the headers shared with Delphes
```

~200 kB, far under the CRAB sandbox limit.

**Container:** The standard `cmssw-el7` wrapper from `/cvmfs/cms.cern.ch`.

**Conditions:** The conditions can be read directly from the CERN Open Data portal via `xrootd`:
| file | size | record |
|---|---|---|
| `root://eospublic.cern.ch//eos/opendata/cms/conddb/102X_upgrade2018_design_v9.db` | 1.00 GB | [1807](https://opendata.cern.ch/record/1807) |
| `root://eospublic.cern.ch//eos/opendata/cms/conddb/106X_mcRun2_asymptotic_v17.db` | 664 MB | [1819](https://opendata.cern.ch/record/1819) |

On some sites, these conditions are already present (via CVMFS), which avoids a 1.7 GB download, so that is attempted first;
the download over `xrootd` is only done if needed.

## The FrameworkJobReport

All CRAB jobs must write a FrameworkJobReport, else they crash before stageout even if the job ran completely fine.
Since the last step is a custom ntuplizer (and not `cmsRun`), a dummy FrameworkJobReport must be provided manually.

The report declares an `<AnalysisFile>`, the same output type as what `cmsRun` emits for a `TFileService` output,
i.e. for an ordinary ROOT file such as the one produced by our ntuplizer.
Note: don't use `<File>`, which expects output in EDM format and crashes in this workflow.

The same distinction has to hold in `pset.py`:
- Use `TFileService`, and not `PoolOutputModule` (which also expects EDM format and crashes here).
- `JobType.outputFiles` is deliberately left unset, since CRAB already infers the file from the pset.

## Memory and number of cores

Measured over past runs: 1616-1849 MB average, 3958 MB peak.
CRAB refuses more than 3000 MB for a 1-core task, hence `--cores 2 --memory 4000`.
The chain is single-threaded, so the second core is bought for its memory allowance rather than for speed.
Maybe to be improved later.
