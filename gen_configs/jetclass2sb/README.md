# `jetclass2sb`: the generation behind the CMS offline+scouting reference dataset

> **The name.** `sb` is for Sebastian, who shared the original reference dataset. The
> processes here are a *jetclass2-style* QCD sample generated the way his dataset was,
> which is why they sit next to `jetclass1` and `jetclass2`. It is all lowercase to
> match them; it was briefly `jetclass2SB`, and before that `scouting_run3` - a
> misleading name, since the fragments are Run-3 McM fragments but nothing here is
> scouting-specific and we run them with Run-2/2018 conditions.
>
> **Datasets produced before the lowercasing** carry `jetclass2SB` as their own
> `<output-path>/<family>/` directory, because a production writes that directory from
> its `--procs` argument. `validation/print_njets.py` therefore matches the family name
> case-insensitively (see its `OURS_FAMILIES`), so those datasets stay readable -
> `output_fullsim_350k_trial_jetclass2sb_qcdonly` is one of them.

These processes reproduce the **generator side** of
`/eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/` — the real CMS
offline+scouting dataset this whole pipeline is being compared against (see
`hlteff/README.md` "Data source"). They exist because our own jetclass2 QCD has a
markedly softer jet pT spectrum than that reference, and the difference turned out to
be entirely in how the samples were generated.

They are **FullSim-only**: `run.sh fullsim`. The Delphes backend refuses them with an
explicit error, because a CMSSW GEN fragment never produces the `events.hepmc` Delphes
needs.

```bash
./run.sh fullsim jetclass2sb/QCD_PT-470to600 16 8 0
```

## Where this came from

| what | where |
|---|---|
| fragments | <https://github.com/colizz/hww-tagging/tree/dev-miniaods/event_producer/cmsconnect_miniaods_scouting_Run3/fragments> |
| job scripts (the mixing!) | `.../cmsconnect_miniaods_scouting_Run3/jdl/train` |
| ntuplizer that made the reference | `colizz/DNNTuples`, branch `dev-nanov15`, `Ntupler/test/DeepNtuplizerAK8Scout.py` |
| dataset owner | Congqiao Li (`coli`) |

The QCD fragments are themselves the **official CMS McM Summer23GS fragments** (each
file carries the McM link in its own first line).

## The key fact: the mixing, not the fragments

Each fragment is an ordinary `HardQCD:all = on` run with a pThat window. What makes
the reference spectrum hard is how the ten bins were **combined**, and that is only
visible in the JDL files:

| | per bin |
|---|---|
| jobs × events | 500 × 500 |
| **events generated** | **250,000 — identical for every one of the ten bins** |

So the sample is **flat in pThat, not cross-section weighted**. Under a physical
weighting the high bins would be vanishingly rare; here they carry equal weight.

This reproduces the reference's measured gen-jet spectrum: flat mixing over these bins
puts the median at the 800-1000 / 1000-1400 boundary, and the reference's measured
`fj_genjet_pt` median is **871 GeV** (p10 315, p90 2517, max 3699 — the `3200toInf`
tail; the 110 minimum is below the lowest pThat cut, as expected for subleading jets).

For comparison, our `jetclass2/train_qcd` draws `PhaseSpace:pTHatMin` log-uniformly
from 200 values over 100-5000 GeV at 13 TeV, which gives a much softer jet spectrum
(median ~523 GeV above 200 GeV, against the reference's 803 GeV).

## How to reproduce the mix

**What fixes the spectrum is the TOTAL number of events per bin** — that is,
`--njobs` x `--nevents-per-job` — being the same for all ten bins. Nothing else about
how those events are packaged into jobs matters to the physics:

```
njobs(bin) x nevents-per-job(bin) = <events per bin>      for every bin
```

The simplest way to satisfy it is identical `--njobs` and `--nevents-per-job`
everywhere:

```bash
OUT=/eos/user/l/llambrec/jetclass/output_jetclass2sb
for b in 170to300 300to470 470to600 600to800 800to1000 \
         1000to1400 1400to1800 1800to2400 2400to3200 3200toInf; do
  python run_condor_loop.py --backend fullsim --procs jetclass2sb/QCD_PT-$b \
      --njobs <N> --nevents-per-job <M> --batch-size <M/2> \
      --output-path $OUT --max-materialize 100 -o condor_jetclass2sb
done
```

But the CPU cost per event rises steeply with pThat (a 3200 GeV event has far more to
simulate than a 200 GeV one), so equal *events* per bin does **not** mean equal *time*
per bin, and one job size for all ten either wastes the cheap bins or gets the
expensive ones killed at the wall-time limit. The fix is to vary the job size per bin
**and compensate with `--njobs` so the product stays constant**:

```
nevents-per-job(bin) ~ (wall-time budget) / (s per event in that bin)
njobs(bin)           = <events per bin> / nevents-per-job(bin)
```

i.e. expensive bins get fewer events per job and proportionally MORE jobs. Varying the
job size without adjusting `--njobs` would change the events per bin and therefore skew
the mixture — the one thing this whole setup exists to get right. See "Timing".

## Adaptation for CMSSW_10_6_30

The fragments are copied **verbatim**, with exactly one change, marked inline in each
file: the Run-3 13.6 TeV CP5 tune module (`Configuration.Generator.MCTunesRun3ECM13p6TeV`)
does not exist in this release, which ships only the 13 TeV `MCTunes2017` variant. The
import therefore falls back to an inlined copy of that block from `cms-sw/cmssw`
(Apache-2.0). The two differ **only** in `SigmaTotal:sigmaEl` (21.89 → 22.08) and
`SigmaTotal:sigmaTot` (100.309 → 101.037).

Beam energy is **13.6 TeV** as in the reference, while the detector conditions are
**2018 / Run 2** — a deliberate choice (the open conditions have no Run-3 option). The
detector simulation does not use the beam energy directly, but the mismatch is real and
should be stated when these samples are compared with the reference.

## The two-prong signal is NOT wired up

The reference's signal sample (`submit_higgs2p.jdl` →
`BulkGravitonToHHTo4QGluLTau_MX-600to6000_MH-15to650`, 2000 × 500 = 1M events) is
**not** a Pythia-only fragment. It declares **3564 `RandomizedParameters` points**
(26 × 54 low-mass + 40 × 54 high-mass), each referencing its own MadGraph gridpack via

```
GridpackPath = cms.string('instMG://BulkGravitonToHH/MG5_aMC_v2.9.18/<MX>:<MH>')
```

`instMG://` is **not a CMSSW feature** — it is absent from both CMSSW_10_6_30 and
CMSSW_13_0_0. The production's `run_and_transfer_2022.sh` shows the mechanism: it
downloads MG5_aMC v2.9.18, copies `GeneratorInterface/{Core,LHEInterface}` into a
developer area, and patches CMSSW to swap the gridpack fetcher for its own script —

```
sed -i "s|run_generic_tarball_cvmfs.sh|run_instMG.sh|g" GeneratorInterface/Core/src/BaseHadronizer.cc
```

— which builds each mass point's gridpack on the fly. It also targets CMSSW_12_4_11
with Run-3 conditions, not our 10_6_30 / 2018.

Nothing there is closed source (MG5 is public, the scripts are in the repository above,
the patch is a `sed` on Apache-2.0 code), so it stays within the open-tooling
requirement — but it is a substantially larger job than the QCD side. Before attempting
it, it is worth asking whether prebuilt gridpacks can be obtained, which would remove
most of the work.

Meanwhile the usable options for a signal sample are `jetclass2/train_higgs2p` (works
today, pure Pythia, different spectrum), or pairing this QCD with it and comparing in
matched pT bins.

## Timing

<details>
<summary><b>Superseded: the original probe-based cost model (WRONG - kept only to show
how it failed)</b></summary>


Per-event cost rises steeply with pThat, so one job size for all ten bins either wastes
the cheap bins or gets the expensive ones killed. Measured with two 8-event probe jobs
(one batch each, so the ~169 s per-batch startup is subtracted):

| probe | total | marginal |
|---|---|---|
| `QCD_PT-170to300` | 255 s / 8 ev | **10.8 s/event** |
| `QCD_PT-3200toInf` | 527 s / 8 ev | **44.8 s/event** |

A factor 4.2 across a pThat factor 15, i.e. **cost ~ pThat^0.52** (close to sqrt), which
is used to interpolate the eight bins in between. Both probes ran on an lxplus
*interactive* node; lxbatch workers are slower, so a **x1.4** correction is applied,
measured from the previous production (45 s/event predicted interactively against
62 s/event actually measured on batch). Other fixed costs: ~169 s per batch (the three
cmsRun startups plus the ntuplizer) and ~240 s per job (scram area + `scram b` +
cmsDriver + building the ntuplizer).

Jet yield scales with pThat too - the probes gave 1.0 jets/event at 170-300 (most jets
there fall below the 200 GeV offline cut) and 2.1 at 3200-Inf - interpolated the same
way, giving **~1.54 jets/event averaged over the ten bins**. That estimate rests on
only 8 + 17 probe jets, so treat it as +-30% and leave margin when sizing for a jet
target.

</details>

### Measured cost model (use this one)

The first trial
(2026-10-08) measured the real cost over 217 completed jobs, and the per-event cost is
much higher than the probes suggested and only *weakly* dependent on pThat:

| bin | nev/job | jobs | median | p90 | max | **s/event (med)** | s/event (p90) | predicted | ratio |
|---|---|---|---|---|---|---|---|---|---|
| `170to300` | 800 | 0/30 | - | - | >8.0 h | (>36, all killed) | - | 3.5 h | - |
| `300to470` | 500 | 39/48 | 7.3 h | 7.9 h | 8.0 h | **52.5** | 57.1 | 2.9 h | 2.5x |
| `470to600` | 500 | 36/48 | 5.9 h | 7.8 h | 7.9 h | **42.4** | 56.5 | 3.4 h | 1.7x |
| `600to800` | 400 | 53/60 | 5.2 h | 7.6 h | 8.0 h | **47.0** | 68.7 | 3.1 h | 1.7x |
| `800to1000` | 400 | 22/60 | 6.1 h | 7.9 h | 8.0 h | **54.7** | 70.7 | 3.6 h | 1.7x |
| `1000to1400` | 250 | 46/96 | 5.8 h | 6.8 h | 7.0 h | **84.0** | 97.8 | 2.6 h | 2.2x |
| `1400to1800` | 250 | - | 4.9 h | 6.1 h | 6.1 h | **71.0** | 88.5 | 3.0 h | 1.6x |
| `1800to2400` | 250 | - | 5.1 h | 5.5 h | 5.5 h | **73.2** | 78.7 | 3.4 h | 1.5x |
| `2400to3200` | 200 | - | 4.2 h | 5.1 h | 5.1 h | **75.6** | 91.0 | 3.2 h | 1.3x |

Three lessons:

1. **Use a flat ~55 s/event for the low five bins and ~85 s/event for the high five**,
   not a power law. The measured spread across the whole pThat range is only 42 -> 85
   s/event (factor 2 over a pThat factor 15, i.e. an exponent of ~0.25, not 0.52), and
   the low bins are *4-5x* more expensive than the probes claimed. This is consistent
   with the previous jetclass2 production's 62 s/event batch median, which was the
   better number all along.
2. **Two 8-event probe jobs are not a usable measurement.** Subtracting an assumed
   169 s fixed cost from a 255 s total leaves a marginal rate dominated by the
   assumption, not by the data. Size from a real production, or from probes of >=100
   events.
3. **Size on the max, not the median.** Within a single bin at fixed `nev/job` the
   runtime spreads by a factor ~2 (e.g. 3.8 - 8.0 h for `300to470`), from worker-node
   speed alone. p90/median ~ 1.3 and max/median ~ 1.4, so a 5 h *median* job still
   loses its tail to the 8 h `workday` limit.

**Sizing rule that follows:** pick `nev/job` so that `nev x (p90 s/event) <= 5.5 h`.
That gives roughly 300 events/job for the low five bins and 200 for the high five.

## Production log

### 2026-10-12 - OUTCOME of the 2026-10-09 round: **success**

**973 usable files, 199,520 events, 387,711 jets** (target 350k) in
`/eos/user/l/llambrec/jetclass/output_jetclass2sb_trial`, 1.5 GB.
**974 of 975 jobs completed (99.9%), 1 killed at the wall limit.**

Runtime over all 974: median **3.57 h**, p90 **5.70 h**, max **7.81 h**. The 5.0 h p90
sizing target was slightly exceeded (5.70 h) but the 8 h limit was never a systematic
problem - against 88 wall-time kills in the previous round. Per-bin medians ran 2.58 -
4.97 h.

**Correction to the in-flight report of 2026-10-09:** at the time I read 2.5 h median
and 30-36 s/event off the first ~110 completions and concluded the pool was running
faster than during the probe round. That was wave bias - those 110 were the fastest
nodes of the cheapest five bins. The final figures are 37-112 s/event, i.e. *the same
as or worse than* the probe round's 42-55 s/event. **The pool was not faster; the
sizing margin is what removed the kills.** Keep the margin.

Final measured **jets/event** (use these, they are the whole production now):

| bin | jets/ev | sized with |
|---|---|---|
| `QCD_PT-170to300` | **0.67** | 1.30 (bad) |
| `QCD_PT-300to470` | **1.85** | 1.68 |
| `QCD_PT-470to600` | **2.00** | 1.87 |
| `QCD_PT-600to800` | **2.02** | 1.79 |
| `QCD_PT-800to1000` | **2.15** | 1.73 |
| `QCD_PT-1000to1400` | **2.18** | 2.22 |
| `QCD_PT-1400to1800` | **2.17** | 2.13 |
| `QCD_PT-1800to2400` | **2.13** | 2.13 |
| `QCD_PT-2400to3200` | **2.22** | 2.26 |
| `QCD_PT-3200toInf` | **2.05** | 2.30 |

Ten-bin sum **19.44 jets per event-per-bin**, so `jets ~ 19.4 x (events per bin)`.
Note `170to300` really is half what was assumed (0.67) - with the 200 GeV offline cut
that bin rarely yields an accepted AK8 jet - while the four bins above it beat their
assumptions, which is why the total still came out above plan.

**Mixture: flat as intended.** Every bin returned 100% of its 20,000 events except
`QCD_PT-3200toInf` at 98% (124/125 jobs, then 123 after the bad file below). This was
the entire point of redoing the round.

#### Two defects found, one fixed

1. **Job 406255.108** (`3200toInf`) hung: 8 h wall, resident size frozen at 630 MB
   from 5 minutes in (a healthy job sits near 1.4 GB), one execute attempt, no
   checkpoint written, so it never finished even its first 80-event batch. The stall
   watchdog did not fire. 1 in 975; not chased.
2. **Job 406255.45** (`3200toInf`) exposed a real bug, now fixed. Its ntuplizer threw
   `ProductNotFound` on event 1 of *both* batches - a `reco::TrackRef` into a
   `std::vector<reco::Track>` that is not kept in `reco.root` (the impact-parameter
   path). `backend_run_batch` correctly declined to count either batch ("0 of 2
   batches reconstructed successfully"), **but the failed ntuplizer leaves an
   811-byte keyless `ntuple.root` behind**, and both merge paths globbed
   `batch_*/ntuple.root`, so the checkpoint published it, `hadd` merged two garbage
   files, and the job **exited 0** with an unreadable file on EOS. At 975 jobs that
   cost one file; at production scale it would silently seed the dataset with
   unreadable ntuples.

   Fixed in `backends/fullsim.sh`: a failed batch's `ntuple.root` is deleted, and both
   `backend_intermediate_merge()` and `backend_finalize()` now gate on
   `NTUPLES_PRODUCED` rather than on the glob, so a job in which every batch fails
   exits non-zero instead of publishing an empty file. The bad file was deleted from
   the dataset (hence 973, not 974).

   The underlying `ProductNotFound` is **not** fixed - it is rare (1/975) and was not
   reproduced. If it becomes common, the ntuplizer's track dereference needs a
   `.isAvailable()` guard, or `reco.root` needs `generalTracks` in its keep list.

### 2026-10-09 - QCD-only trial, resized (`output_jetclass2sb_trial`)

Resubmitted from scratch after cancelling the 2026-10-08 round. Sized from that
round's **measured** p90 s/event (section above), not from probes.

**20,000 events per bin** (the flat-mixture invariant: `njobs` x `nev/job` = 20,000 for
all ten). `nev/job` is the largest even divisor of 20,000 whose p90 job time stays
under **5.0 h** - 3 h of headroom against the 8 h `workday` limit, chosen because
within one bin the runtime spreads by a factor ~2 on worker-node speed alone.

| bin | p90 s/ev | nev/job | batch | njobs | p90 job | jets/ev | jets |
|---|---|---|---|---|---|---|---|
| `QCD_PT-170to300` | 57.0* | 250 | 125 | 80 | 4.03 h | 1.30* | 26,000 (actual: 0.68 -> 13,600) |
| `QCD_PT-300to470` | 57.1 | 250 | 125 | 80 | 4.03 h | 1.68 | 33,600 |
| `QCD_PT-470to600` | 56.5 | 250 | 125 | 80 | 3.99 h | 1.87 | 37,400 |
| `QCD_PT-600to800` | 68.7 | 250 | 125 | 80 | 4.84 h | 1.79 | 35,800 |
| `QCD_PT-800to1000` | 70.7 | 250 | 125 | 80 | 4.98 h | 1.73 | 34,600 |
| `QCD_PT-1000to1400` | 97.8 | 160 | 80 | 125 | 4.41 h | 2.22 | 44,400 |
| `QCD_PT-1400to1800` | 88.5 | 200 | 100 | 100 | 4.98 h | 2.13 | 42,600 |
| `QCD_PT-1800to2400` | 78.7 | 200 | 100 | 100 | 4.44 h | 2.13 | 42,600 |
| `QCD_PT-2400to3200` | 91.0 | 160 | 80 | 125 | 4.11 h | 2.26 | 45,200 |
| `QCD_PT-3200toInf` | 100.0* | 160 | 80 | 125 | 4.51 h | 2.30* | 46,000 |

`*` = extrapolated, no completed jobs in the probe round (`170to300` lost all 30 jobs,
`3200toInf` never started).

**975 jobs, 200,000 events, ~3,600 CPU-hours, ~9 h wall at 400 concurrent.**
Expected **~388,000 jets** (target was 350k; the margin covers the extrapolated
jets/event for the two bins without data). Output
`/eos/user/l/llambrec/jetclass/output_jetclass2sb_trial`, submission files in
`condor_jetclass2sb`, clusters **406246-406255** in the bin order of the table.

```bash
OUT=/eos/user/l/llambrec/jetclass/output_jetclass2sb_trial
while read b nj nev batch; do
  python3 run_condor_loop.py --backend fullsim --procs jetclass2sb/QCD_PT-$b \
      --njobs $nj --nevents-per-job $nev --batch-size $batch \
      --output-path $OUT --max-running 400 --max-materialize 80 \
      -o condor_jetclass2sb
done <<'EOF'
170to300 80 250 125
300to470 80 250 125
470to600 80 250 125
600to800 80 250 125
800to1000 80 250 125
1000to1400 125 160 80
1400to1800 100 200 100
1800to2400 100 200 100
2400to3200 125 160 80
3200toInf 125 160 80
EOF
```

`--max-running 400` is the global cross-cluster cap (it becomes the concurrency limit
`llambrec_jetclass:5770`, since 2308032/5770 = 400). `--max-materialize 80` only bounds
each cluster's idle-queue footprint; with ten clusters it would allow 800 concurrent on
its own, so it is never the throttle.

**Measured in flight (2026-10-09, first ~110 completed jobs, 0 killed):** jobs are
finishing in **2.5 h median** against the 4.0-5.0 h p90 prediction, at 30-36 s/event
instead of the 42-55 s/event the probe round measured - the lxbatch pool was simply
running faster than it did overnight on 10-08, when it was heavily oversubscribed
(13.4k idle against 2.4k running pool-wide). Smaller batches here (80-125 events
against 100-400) amortise the ~169 s per-batch fixed cost *worse*, so none of the
speedup comes from the resizing. The conservative 5 h target means that factor-2
node-speed spread now shows up as headroom rather than as kills.

**One real correction, important for the next round:** `QCD_PT-170to300` yields
**0.68 jets/event**, not the 1.30 extrapolated for it - with the 200 GeV offline jet
cut, pThat 170-300 rarely produces an accepted AK8 jet. Every other measured bin met
or beat its assumption (`300to470` 1.84, `470to600` 1.83, `600to800` 1.95,
`800to1000` 2.23). Net effect on this round: ~381,500 jets instead of 388,200, still
comfortably over the 350k target. **Use 0.68 for `170to300` when sizing**, which drops
the ten-bin sum from 19.4 to **18.8 jets per event-per-bin**.

**To scale a future round:** keep `nev/job` and `batch` (they set the job length, which
is what keeps jobs inside the wall limit) and scale every `njobs` by the same factor.
That preserves the flat mixture and the per-bin job length. Jets scale linearly at
**~18.8 jets per event-per-bin** (19.4 as planned, corrected for `170to300`),
i.e. `jets ~ 18.8 x (events per bin)`.

### 2026-10-08 - first QCD-only trial - **CANCELLED, treat as a probe**

Sized with the (wrong) probe cost model. 88 of 774 jobs were killed at the 8 h wall
limit, all in the five lowest pThat bins, and the lowest bin `QCD_PT-170to300` lost
**all 30** of its jobs with zero output. The surviving 224 jobs gave 155k jets from
84k events, so the *jet* target was on track, but the flat-in-pThat mixture was
destroyed at the low end (0% / 81% / 73% / 88% / 50% of the intended events for the
five lowest bins against 100% for the five highest), which is exactly where the jet pT
spectrum gets its statistics. The whole round was cancelled and its output deleted;
its only lasting value is the timing measurement in the section above.

Two things were fixed as a result:

* **Sizing** now comes from the measured p90 s/event, not from probes (next entry).
* **`backend_intermediate_merge()` in `backends/fullsim.sh`** now checkpoints a valid
  partial ntuple to EOS after every batch but the last, under the same final
  `ntuple_$JOBNUM.root` name. Previously `copy_to_eos` ran only in
  `backend_finalize`, so a wall-time kill discarded every *completed* batch - which is
  why those 30 jobs produced nothing at all despite ~8 h of finished reconstruction
  each.

<details>
<summary>Original (cancelled) settings</summary>

#### 2026-10-08 - first QCD-only trial (`output_jetclass2sb_trial`)

Sized to beat the previous jetclass2 trial's **338k QCD jets**; target 350k, submitted
for ~370k expected to leave margin on the jets/event uncertainty above.

**24,000 events per bin** (the invariant: `njobs` x `nev/job` is identical for all ten,
so the mixture stays flat), with the job size tuned per bin to land every job at
2.6-3.6 h - roughly half the previous trial's 5.5 h median, which is what caused its
20% wall-time losses.

| bin | njobs | nev/job | batch | predicted job time |
|---|---|---|---|---|
| `QCD_PT-170to300` | 30 | 800 | 400 | 3.5 h |
| `QCD_PT-300to470` | 48 | 500 | 250 | 2.9 h |
| `QCD_PT-470to600` | 48 | 500 | 250 | 3.4 h |
| `QCD_PT-600to800` | 60 | 400 | 200 | 3.1 h |
| `QCD_PT-800to1000` | 60 | 400 | 200 | 3.6 h |
| `QCD_PT-1000to1400` | 96 | 250 | 125 | 2.6 h |
| `QCD_PT-1400to1800` | 96 | 250 | 125 | 3.0 h |
| `QCD_PT-1800to2400` | 96 | 250 | 125 | 3.4 h |
| `QCD_PT-2400to3200` | 120 | 200 | 100 | 3.2 h |
| `QCD_PT-3200toInf` | 120 | 200 | 100 | 3.6 h |

**774 jobs, 240,000 events, ~2,500 CPU-hours, ~12.5 h wall at 200 concurrent.**
Output `/eos/user/l/llambrec/jetclass/output_jetclass2sb_trial`, submission files in
`validation/../condor_jetclass2sb`, condor clusters 404377-404386 (in the bin order
of the table).

Submitted with:

```bash
OUT=/eos/user/l/llambrec/jetclass/output_jetclass2sb_trial
while read b nj nev batch; do
  python3 run_condor_loop.py --backend fullsim --procs jetclass2sb/QCD_PT-$b \
      --njobs $nj --nevents-per-job $nev --batch-size $batch \
      --output-path $OUT --max-running 200 --max-materialize 50 \
      -o condor_jetclass2sb
done <<'EOF'
170to300 30 800 400
300to470 48 500 250
470to600 48 500 250
600to800 60 400 200
800to1000 60 400 200
1000to1400 96 250 125
1400to1800 96 250 125
1800to2400 96 250 125
2400to3200 120 200 100
3200toInf 120 200 100
EOF
```

`--max-running 200` is the one that matters for the concurrency target: it is a
concurrency limit, enforced by the negotiator **across all ten clusters**.
`--max-materialize` is per cluster, so on its own ten clusters would allow ten times
the intended number; it is kept only to bound the idle-queue footprint.

</details>

**To scale a future round:** keep `nev/job` and `batch` as above (they set the job
length, which is what keeps jobs inside the wall limit) and scale every `njobs` by the
same factor - that preserves both the flat mixture and the per-bin job length. Jets
scale linearly: ~15.4 jets per event-per-bin, i.e. `jets ~ 15.4 x (events per bin)`.
