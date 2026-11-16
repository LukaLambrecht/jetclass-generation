# HTCondor submission

Convenience submitters for running a full production on HTCondor.

Note: these convenience scripts currently only support the `fullsim`-backend.
They have not been used with the `delphes`-backend, but could be extended if needed.

## Quick start

```bash
# QCD: ten pThat bins, 7,000 jobs, 2M events, ~3.89M jets
./submit_production_qcd.sh --dry-run   # inspect first
./submit_production_qcd.sh

# signal: 4,000 jobs, 2M events, ~1.5M useful jets
MG5_PATH=/path/to/MG5_aMC_v3_7_2 ./submit_production_higgs2p.sh
```

**Additional arguments:**
- Both: `--dry-run` (print every command, run nothing), plus the usual knobs: `--output`, `--max-running`, `--jobflavour`, `--condordir`.
- QCD only: `--bins` (submit a subset of the pT-binned samples) and `--scale` (multiply every `njobs`; see below).
- Signal only: `--njobs`, `--nevents`, `--batch-size`.

## Prerequisites

**For QCD from `jetclass2sb/*`: nothing beyond this repo.** 
Those are CMSSW GEN fragments, so CMSSW generates the events itself with its internal Pythia installation.
The fullsim backend needs only CVMFS and `apptainer` for access to CMSSW.
Conditions come from the CERN Open Data portal.

**For the signal from `jetclass2/*`: a MadGraph5 install.**
These are `hepmc` processes: MadGraph5 + Pythia8 run *before* CMSSW and hand over `events.hepmc`.
Install per [`../INSTALL.md`](../INSTALL.md) steps 2-3, then pass `MG5_PATH`.
The submitter checks for it up front and refuses to submit if not found.

## Keeping the pT mixture flat in the QCD samples

`njobs x nev/job` must give the same number of events for every pT bin.
To scale the sample, change `--scale` (or every `njobs` by the same factor) and do not change `nev/job`.
`nev/job` also sets the job length, which is what keeps jobs inside the wall-time limit.

## Other notes, features and issues

* **Wall-time.**
  The default job flavour is `tomorrow` (24 h).
  Jobs are sized such that most fit within 7-8 h, but job flavour `workday` cuts off a significant tail of longer running jobs.
* **Per-event cost as a function of pThat not yet clear.**
  Measured wildly different values depending on too many factors to draw any systematic conclusions yet.
* **Output layout.**
  The output goes to `<output>/<family>/<proc>/<backend opts>/ntuple_*.root`.
* **Submit files and job logs.**
  These go to `condor_jetclass2sb/` and `condor_jetclass2_higgs2p/` at the repository root (override with `--condordir`).
