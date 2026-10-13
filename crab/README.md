# CRAB submission for the fullsim backend

An alternative to `run_condor.py` / `run_condor_loop.py` for the `fullsim` backend:
the same chain, submitted to the CMS grid instead of HTCondor, for the
parallelism a multi-million-jet production needs. Inspired by
[private-sample-production](https://github.com/LukaLambrecht/private-sample-production).

The HTCondor path is unchanged and remains the right tool for small runs and/or runs with the (much faster) `delphes` backend.

## Files

```
build_simpack.py      assembles a self-contained simpack - the whole workflow
templates/            crab_config.py, crab_submit.sh, pset.py,
                      run_in_container.sh (scriptExe), run_job.sh (in-container)
site-probe/           OPTIONAL: measures which sites avoid the conditions download.
                      Not needed to run a production; see its own README.
```

## How it works

CRAB normally runs `cmsRun <psetName>`. `JobType.scriptExe` overrides that with an
arbitrary script, which is what lets the three-step chain plus the standalone
ntuplizer run as one job. `pset.py` stays as a formal requirement - and because CRAB
reads the output file name from it, its `ntuple.root` must stay in sync with what
`run_job.sh` leaves behind.

**Simpack:** a self-contained directory holding everything a job needs, because
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

`run_job.sh` drives `fullsim_configs/run_chain.sh` exactly as `backends/fullsim.sh`
does locally, so both paths share one chain. It deliberately does *not* go through
`run.sh`/`backends/fullsim.sh`: those call `copy_to_eos` themselves, which is CRAB's
job here.

**Container:** the standard `cmssw-el7` wrapper from `/cvmfs/cms.cern.ch`, not the
open-data Docker image. CMSSW_10_6_30 is an ordinary CMS release present at every
site, so the image would only add an OS - and it bundles only the *106X* conditions,
not `102X_upgrade2018_design_v9`, so it would not have removed the site dependency
below either.

## Conditions: no site whitelist needed

The chain reads open conditions for two global tags. `/cvmfs/cms-opendata-conddb.cern.ch`
is not in the `cvmfs-config.cern.ch` domain list that grid sites auto-mount, and at
~1.67 GB the files cannot be shipped in the CRAB sandbox.
But the same files are published by the CERN Open Data portal as ordinary
xrootd-readable files, which is the route used here.

| file | size | record |
|---|---|---|
| `root://eospublic.cern.ch//eos/opendata/cms/conddb/102X_upgrade2018_design_v9.db` | 1.00 GB | [1807](https://opendata.cern.ch/record/1807) |
| `root://eospublic.cern.ch//eos/opendata/cms/conddb/106X_mcRun2_asymptotic_v17.db` | 664 MB | [1819](https://opendata.cern.ch/record/1819) |

Verified: fetched with `X509_USER_PROXY` unset, **byte-identical** (`cmp`) to the CVMFS
copies, and the full chain runs off them.

`run_job.sh` therefore does CVMFS-first, xrootd-fallback, per file:

* mount present -> nothing fetched, zero cost;
* missing -> `xrdcp` into job scratch and `FULLSIM_CONDDB` repointed there
  (`patch_cond.py` documents that variable as the override for "somewhere without
  CVMFS" - the hook already existed);
* partially present -> symlink what CVMFS has, fetch only the rest.

### What this costs, and how to reduce it

The fetch is **per job**, 1.67 GB each. A 4,615-job production is up to **7.7 TB** from
eospublic - ~45 MB/s averaged over two days. Reasonable for a service hosting a 55 TB
premix library meant to be streamed, but it is public infrastructure, so:

* **Fewer, bigger jobs** halve it directly - the fetch does not scale with events, and
  the 24 h `tomorrow` queue leaves room.
* **Sites that do mount the CVMFS repo pay nothing.** That is what `submit_probe.sh`
  now measures: not whether a site is *usable* (all are), but whether it avoids the
  download. Use the result as a `--whitelist` preference, not a requirement.
* **Slimming the sqlite** to only the tags the chain reads would let it ship in the
  sandbox. Unmeasured - the 1 GB is probably dominated by alignment and calorimeter
  calibrations that reconstruction genuinely needs.

## The site probe (optional)

`site-probe/` measures which sites already mount the conditions and so avoid the
~1.67 GB download. It is a performance preference, not a requirement - the production
does not need it. See `site-probe/README.md`.

## Prerequisites

A valid proxy, which `crab_submit.sh` checks for:

```bash
voms-proxy-init -voms cms -valid 192:00
```

**Memory:** CRAB refuses a 1-core task above **3000 MB**, so the lxplus-condor default
of 4096 does not carry over - `build_simpack.py` defaults to **2500 MB**, above the
~1.4 GB peak measured on lxplus with margin. If a job is ever held for memory, raise
`--cores` (the cap scales with cores) rather than `--memory`.
