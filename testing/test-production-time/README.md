# testing/test-generation-time

A timing scan of the full `run.sh` chain (event generation + Delphes
reconstruction + ntupling), to check how per-job runtime scales with the
number of events requested - relevant for planning how to split a large
production run into condor jobs.

## Tools

### `run_timing_scan.py`

Submits one condor job per NEVENT value (parallel, independent jobs), each
running `run.sh` for a given process/card and timing the whole call with the
bash builtin `time`. Each job appends a `NEVENT=... JOBNUM=... elapsed_sec=...
rc=...` line to a shared results file.

```bash
python3 run_timing_scan.py --nevents 10,20,50,100,200,500,1000,2000,5000,10000
```

### `plot_timing.py`

Reads a `run_timing_scan.py` results file, fits
`elapsed_sec = intercept + slope * NEVENT` by ordinary least squares, and
saves a scatter+fit plot to `output_plots/timing_scan.png`.

```bash
python3 plot_timing.py
```

## Notes on timing

Ran the scan above for `jetclass1/HToBB/precompiled` with the
`onlyFatJetNoPU` card, at `NEVENT` = 10, 20, 50, 100, 200, 500, 1000, 2000,
5000, 10000 (`timing_results.txt`, `output_plots/timing_scan.png`).

**Findings**:
- `elapsed_sec ≈ 290 + 0.069 × NEVENT`.
- ~290 s of fixed, per-job overhead, independent of NEVENT.
  This dominates runtime for small/moderate jobs.
- ~0.069 s of marginal cost per event, covering the actual MG5 event
  generation, Pythia8 showering, Delphes reconstruction, and ntupling work
  that does scale with NEVENT.
