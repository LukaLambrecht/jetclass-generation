# lxplus HTCondor submission

Convenience submitters for running a full production on **lxplus HTCondor**, as a
backup to (or replacement for) the CRAB/grid route in [`../crab/`](../crab/).

Same chain, same settings, same output schema - only the batch system differs. The
job splitting here is byte-for-byte the splitting used for the CRAB submissions, so
the two routes produce an equivalent dataset.

| | lxplus condor (here) | CRAB (`../crab/`) |
|---|---|---|
| where jobs run | lxbatch | CMS grid, many sites |
| parallelism | your lxbatch share | thousands of slots |
| needs a grid proxy | no | yes (`voms-proxy-init -voms cms`) |
| needs a simpack | no, runs from the repo | yes, built per task |
| conditions | CVMFS, or fetched over xrootd | same |
| MG5 for signal | **your own install** (see below) | fetched from a staged tarball |

## Quick start

```bash
module load lxbatch/eossubmit          # required when submitting from EOS

# QCD: ten pThat bins, 7,000 jobs, 2M events, ~3.89M jets
./submit_production_qcd.sh --dry-run   # inspect first
./submit_production_qcd.sh

# signal: 4,000 jobs, 2M events, ~1.5M useful jets - NEEDS AN MG5 INSTALL
MG5_PATH=/path/to/MG5_aMC_v3_7_2 ./submit_production_higgs2p.sh
```

Both take `--dry-run` (print every command, run nothing), and the usual knobs:
`--output`, `--max-running`, `--jobflavour`, `--condordir`. The QCD one also takes
`--bins` (submit a subset) and `--scale` (multiply every `njobs` - see the invariant
below). The signal one takes `--njobs`, `--nevents`, `--batch-size`.

## What you need beyond this repo

**For QCD (`jetclass2sb/*`): nothing.** Those are CMSSW GEN fragments, so CMSSW
generates the events itself. The fullsim backend needs only CVMFS and `apptainer`,
both present on lxplus/lxbatch. Conditions come from
`/cvmfs/cms-opendata-conddb.cern.ch`, or are fetched over xrootd from the CERN Open
Data portal if that is not mounted.

**For the signal (`jetclass2/*`): a MadGraph5 install.** These are `hepmc` processes:
MadGraph5 + Pythia8 run *before* CMSSW and hand over `events.hepmc`. Install per
[`../INSTALL.md`](../INSTALL.md) steps 2-3, then pass `MG5_PATH`. The submitter checks
for it up front and refuses to submit 4,000 jobs that would each die on a missing
binary - including the specific `bin/HEPTools`-vs-`HEPTools` layout trap that
INSTALL.md step 2 describes, because it is easy to hit and produces a confusing error
much later.

Nothing here needs Delphes. That is only for the `delphes` backend (INSTALL.md
steps 4-6), which these submitters do not use.

## The one rule when changing the QCD numbers

`njobs x nev/job = 200,000` must hold for **every** bin. Equal events per bin is what
makes the jet pT spectrum flat; it is the whole point of the `jetclass2sb` setup. To
scale the sample, change `--scale` (or every `njobs` by the same factor) and leave
`nev/job` alone - `nev/job` sets the job length, which is what keeps jobs inside the
wall-time limit. Changing one without the other silently skews the mixture.

## Monitoring

```bash
module load lxbatch/eossubmit
condor_q
```

`condor_q` returns nothing at all if that module is not loaded - it queries a
different schedd. The CRAB-based monitoring in `../crab/monitoring/` does not apply
here; these are ordinary condor jobs.

## Known characteristics

* **Wall-time losses.** The default flavour is `tomorrow` (24 h). Jobs are sized for
  a p90 of ~7-8 h, from the per-event cost measured on the completed 2026-10-09 round.
  With `workday` (8 h) the tail is lost - an earlier round lost 88 of 975 jobs that way.
* **Per-event cost is roughly flat in pThat** (37-112 s/event measured), not the steep
  power law an early probe suggested. Do not re-derive it from small probe jobs; two
  8-event probes were wrong by a factor 2.5.
* **Output layout** is `<output>/<family>/<proc>/<backend opts>/ntuple_*.root`, which
  `validation/print_njets.py` and the plotting scripts read directly.
* **Submit files and job logs** go to `condor_jetclass2sb/` and
  `condor_jetclass2_higgs2p/` at the repository root (override with `--condordir`) -
  deliberately *not* inside this `condor/` directory, which is tracked source. The
  `condor_*` name also matches the `.gitignore` job-directory pattern. For the same
  reason `run_condor.py` / `run_condor_loop.py` / `download_gridpack.py` default to
  `-o condor_jobs` rather than the old `-o condor`.
