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
rc=...` line to a shared results file once it finishes, and writes its
detector output to a dedicated directory kept separate from routine
production output (`--output-path`, default
`/eos/user/l/llambrec/jetclass/output_timing_test`) so these throwaway runs
never mix into real output.

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

**Fit: `elapsed_sec ≈ 290 + 0.069 × NEVENT`** (R² = 0.987 across all 10
points, from 10 to 10000 events).

- **~290 s of fixed, per-job overhead, independent of NEVENT.** This
  dominates runtime for small/moderate jobs - at NEVENT=1000, the fixed cost
  is still ~85% of the total (359 s predicted, only ~69 s of which is the
  NEVENT-dependent term). It comes from things that happen once per job
  regardless of how many events are generated: sourcing the LCG software
  stack, MG5/Pythia8 startup and copying the precompiled gridpack into
  `proc_base`, and - likely the single largest piece - ACLiC compiling
  `makeNtuples.C++` from scratch (deliberately done in an isolated per-job
  copy of `delphes_analyzers/`, see `run.sh`'s own comment on why, but that
  means every job pays the full C++ compile cost no matter how few events it
  processes).
- **~0.069 s of marginal cost per event**, covering the actual MG5 event
  generation, Pythia8 showering, Delphes reconstruction, and ntupling work
  that *does* scale with NEVENT. Small compared to the fixed cost through
  this whole tested range - it only starts to dominate once NEVENT reaches
  the tens of thousands.
- Residuals are a mix of real job-to-job variance (EOS I/O, batch-node
  contention - up to ~30-35 s, i.e. ~10% at the smallest NEVENT values where
  that's a larger fraction of the total) and mild curvature at the low end,
  but the linear model is a good description overall (R²=0.987).

**Practical implication**: prefer fewer, larger jobs over many small ones
when planning a production run. The fixed ~290 s overhead is paid once per
job no matter its size, so splitting a fixed total event count into more,
smaller jobs multiplies how many times that cost is paid, for no benefit
beyond parallelism/job-slot turnover. Concretely: 10 jobs of 1000 events each
cost ~10 × 359 s ≈ 3590 s of total (serial-equivalent) compute, while 1 job
of 10000 events costs ~981 s (predicted) to ~1005 s (measured) - roughly a
3.5x reduction in total compute for the same output, at the cost of losing
some parallelism. The right balance in practice depends on how much
wall-clock parallelism is actually needed versus available job slots.
