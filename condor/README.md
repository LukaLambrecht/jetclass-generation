# HTCondor submission

Convenience submitters for running a full production on HTCondor, as a
backup to (or replacement for) the CRAB/grid route in [`crab/`](../crab/).

Same chain, same settings, same output schema - only the batch system differs.

Note: these convenience scripts currently only support the `fullsim`-backend.
They have not been used with the `delphes`-backend, but could be extended if needed.

| | condor (here) | CRAB (`../crab/`) |
|---|---|---|
| needs a grid proxy | no | yes (`voms-proxy-init -voms cms`) |
| needs a simpack | no, runs from the repo | yes, built per task |
| conditions | CVMFS, or fetched over xrootd | same |
| MG5 for signal | your own install (see below) | fetched from a staged tarball |

## Quick start

```bash
# QCD: ten pThat bins, 7,000 jobs, 2M events, ~3.89M jets
./submit_production_qcd.sh --dry-run   # inspect first
./submit_production_qcd.sh

# signal: 4,000 jobs, 2M events, ~1.5M useful jets - NEEDS AN MG5 INSTALL
MG5_PATH=/path/to/MG5_aMC_v3_7_2 ./submit_production_higgs2p.sh
```

Both take `--dry-run` (print every command, run nothing), and the usual knobs:
`--output`, `--max-running`, `--jobflavour`, `--condordir`. The QCD one also takes
`--bins` (submit a subset of the pT-binned samples) and `--scale` (multiply every `njobs` - see the invariant
below). The signal one takes `--njobs`, `--nevents`, `--batch-size`.

## What you need beyond this repo

**For QCD (`jetclass2sb/*`): nothing.** Those are CMSSW GEN fragments, so CMSSW
generates the events itself. The fullsim backend needs only CVMFS and `apptainer`.
Conditions come from `/cvmfs/cms-opendata-conddb.cern.ch`, or are fetched over xrootd from the CERN Open
Data portal if that is not mounted.

**For the signal (`jetclass2/*`): a MadGraph5 install.** These are `hepmc` processes:
MadGraph5 + Pythia8 run *before* CMSSW and hand over `events.hepmc`. Install per
[`../INSTALL.md`](../INSTALL.md) steps 2-3, then pass `MG5_PATH`. The submitter checks
for it up front and refuses to submit if not found.

## Keeping the pT mixture flat

`njobs x nev/job = 200,000` must hold for every bin. Equal events per bin is what
makes the jet pT spectrum flat; it is the whole point of the `jetclass2sb` setup. To
scale the sample, change `--scale` (or every `njobs` by the same factor) and leave
`nev/job` alone - `nev/job` sets the job length, which is what keeps jobs inside the
wall-time limit. Changing one without the other silently skews the mixture.

## Known characteristics

* **Wall-time losses.** The default flavour is `tomorrow` (24 h). Jobs are sized for
  a p90 of ~7-8 h, from the per-event cost measured on the completed 2026-10-09 round.
  With `workday` (8 h) the tail is lost - an earlier round lost 88 of 975 jobs that way.
* **Per-event cost as a function of pThat not yet clear.** Measured wildly different values
  depending on too many factors to draw any systematic conclusions yet.
* **Output layout.** is `<output>/<family>/<proc>/<backend opts>/ntuple_*.root`, which
  `validation/print_njets.py` and the plotting scripts read directly.
* **Submit files and job logs.** go to `condor_jetclass2sb/` and
  `condor_jetclass2_higgs2p/` at the repository root (override with `--condordir`).
