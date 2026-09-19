# Known issues in the Delphes cards (and the ntuples made from them)

## Soft charged-hadron momenta are replaced by the HCal energy (all JetClassII cards)

**Status:** known, deliberately left as is for now (found 2026-09-18).

### What happens

Every JetClassII card in this directory (inherited unchanged from the upstream
jetclass2_generation initial commit, so central JetClass-II most likely has
the same behaviour) contains:

```
module TrackSmearing TrackSmearing {
  ...
  set PResolutionFormula { 0.0 }
```

`TrackSmearing` unconditionally sets `candidate->TrackResolution = pError / p`
(`modules/TrackSmearing.cc`), so this overwrites the realistic value set
upstream by `ChargedHadron/Electron/MuonMomentumSmearing` with **0** for every
track.

`SimpleCalorimeter::FinalizeTower()` then uses that resolution to combine the
track and calorimeter measurements in any tower *without* a significant
neutral excess:

```
weightTrack = (fTrackSigma > 0.0) ? 1 / (fTrackSigma * fTrackSigma) : 0.0;   // -> 0
weightCalo  = 1 / (sigma * sigma);
bestEnergyEstimate = (weightTrack * fTrackEnergy + weightCalo * energy) / (weightTrack + weightCalo);
rescaleFactor = bestEnergyEstimate / fTrackEnergy;                          // = calo / track
track->Momentum.SetPtEtaPhiM(track->Momentum.Pt() * rescaleFactor, ...);
```

With a track weight of 0 every such track is rescaled to the **smeared HCal
tower energy**. HCal resolution is ~150% at 1 GeV, and a tower that fluctuates
below its threshold gets `energy = 0`, i.e. `rescaleFactor = 0` and a track
with pT = 0 (dropped by the ntuplizer, which skips `pt <= 0` constituents).
Charged hadrons are affected (HCal energy fraction 1); electrons/photons in
ECal are not, as they deposit in a different calorimeter.

### Evidence

A/B test on identical events: 300 `jetclass2/train_qcd` events, fixed
`RandomSeed`, offline card as-is (A) vs the same card with only
`set PResolutionFormula { 1.0e-4 }` (B; negligible extra smearing, but tracks
now dominate the track+calo combination):

| charged hadrons per AK8 jet, by jet pT | A (as-is) | B | truth (hard event, pT>0.1, dR<0.8) |
|---|---|---|---|
| 200-300 GeV | 15.1 | 18.2 | 24-26 |
| 300-400 GeV | 15.7 | 19.9 | 26 |
| 400-500 GeV | 16.4 | 21.6 | 27-28 |
| 500-700 GeV | 16.5 | 22.7 | 27-29 |

- Reco/gen pT for charged hadrons with gen pT 1-2 GeV: median **2.3**, 2% within
  2% of gen pT (A) vs median 1.00, 100% within 2% (B).
- The per-jet charged-hadron pT spectrum in A is hollowed out at 0.5-2 GeV and
  piles up below 0.5 GeV (rescaled-down tracks). In the production (A) there
  are ~0.5 charged hadrons per jet at 0.5-1 GeV vs ~4.7 in the CMS FullSim
  (ScoutingAK8) sample for the same jet pT.
- The ntuplizer is not involved (no unresolved constituent references; counts
  match between the Delphes jets and the ntuple).

### Why it is left as is

- Changing it breaks the (currently very good) agreement of our offline sample
  with central JetClass-II, which presumably has the same artifact.
- The HLT card's data-driven tuning (`hlteff/`) was derived on top of the
  current offline behaviour and would need re-checking.
- It does not explain most of the charged-hadron gap w.r.t. FullSim: even the
  *truth-level* count of hard-event charged particles in our sample is below
  FullSim's reconstructed count (FullSim additionally has ~3.7 lost tracks per
  jet, loosely vertex-associated tracks, and material-induced secondaries).

### How to fix, if wanted

Set `PResolutionFormula` in `TrackSmearing` to a small nonzero value in both the
offline and HLT cards (for the HLT card: in the offline baseline it is generated
from, then regenerate). Note that the exact string `"0.0"` is **not** a "no
formula" option: it makes `TrackSmearing` read the resolution from a histogram
file (`errors.root`) instead, and crashes when that file doesn't exist.

## Impact parameters: units and sign differ from CMS FullSim (offline and HLT)

**Status:** known, not changed (found 2026-09-18). Matters whenever a model or
comparison mixes our ntuples with CMS (DNNTuples / ScoutingAK8) ones.

Our `part_d0val`/`part_d0err`/`part_dzval`/`part_dzerr` (and the `hlt_part_*`
versions) are Delphes' `D0`/`ErrorD0`/`DZ`/`ErrorDZ`, written unchanged
(`delphes_analyzers/ParticleInfo.h`). Compared to FullSim's
`cpfcandlt_dxy`/`cpfcandlt_dz` (offline) and `scoutpfcand_dxy`/`scoutpfcand_dz` (HLT):

| | ours (Delphes) | FullSim (CMS) |
|---|---|---|
| units | **mm** (`ParticlePropagator.cc`: `D0 = d0 * 1.0E3`, positions in m) | **cm** |
| transverse IP sign | `d0 = (x*py - y*px)/pt` (`ParticlePropagator.cc:298`) | `dxy = (-x*py + y*px)/pt` - **opposite sign** |
| stored uncertainty | error (`*_d0err`, `*_dzerr`) | significance (`*_dxysig`, `*_dzsig`) |
| dz reference | primary vertex (offline; HLT only in ntuples made after 2026-09-18, earlier paired productions have HLT dz w.r.t. the detector origin) | primary vertex |

Evidence:

- Units: for charged hadrons in QCD jets (|eta|<1) our median |d0|, |dz| and
  their errors are 6-12x FullSim's in every track-pT bin; dividing ours by 10
  brings the errors to within ~10-20% of FullSim's. The unit-free significances
  are comparable (median |d0/err| 0.7-0.8 ours vs 0.8-1.3 FullSim).
- Sign: for a track from a decay displaced along the jet axis, CMS's convention
  gives sign(dxy) = -sign(phi_track - phi_jet). Fraction of significantly
  displaced charged hadrons (|IP significance| > 3 / > 10) with
  sign(IP) == sign(phi_track - phi_jet):

  | | FullSim | ours |
  |---|---|---|
  | QCD, offline | 0.31 / 0.25 | 0.70 / 0.73 |
  | QCD, HLT | 0.39 / 0.32 | 0.69 / 0.73 |
  | signal (H0HpHm / higgs2p), offline | 0.35 / 0.30 | 0.64 / 0.67 |
  | signal, HLT | 0.44 / 0.40 | 0.65 / 0.68 |

To bring ours onto the CMS convention: `dxy_cm = -part_d0val / 10`,
`dz_cm = part_dzval / 10` (errors: `/ 10`, no sign flip). Central JetClass(-II)
uses the same Delphes convention as ours (mm, Delphes sign), so ours is
consistent with the central datasets as is.

The transverse IP needs no vertex subtraction in Delphes: `PileUpMerger` places
the hard-scatter vertex at x = y = 0 and only smears it in z (and t), so a `D0`
measured from the origin is already measured from the primary vertex.

## Required Delphes patch: per-event reseeding in `PileUpMerger` (`PerEventSeed`)

**Status:** applied to our Delphes install on 2026-09-18 (on top of Delphes
commit `fb4d95b`). **Must be re-applied on any fresh Delphes install** - see
`INSTALL.md`.

### Why

The offline and HLT Delphes runs of a batch read the same `events.hepmc`, but
stock Delphes seeds its global random generator only once, at start-up
(`modules/Delphes.cc`, `gRandom->SetSeed(RandomSeed)`), and `PileUpMerger` -
the first module of every event - draws the hard-scatter vertex position, the
number of pile-up interactions, which minimum-bias events to overlay and their
vertices from that one generator. Since the two cards' detector modules consume
different numbers of random numbers per event, the two runs desynchronise from
the second event on even with the same `RandomSeed` (with the previous default,
no `RandomSeed`, they were independent from the first event on). So the same
generated event got a different vertex and a different pile-up overlay offline
and at HLT, and every offline-vs-HLT difference mixed detector effects with
pile-up differences.

### What the patch does

`delphes_patches/PileUpMerger_PerEventSeed.patch` adds an opt-in parameter to
`PileUpMerger` (default off = stock behaviour):

```
module PileUpMerger PileUpMerger {
  ...
  set PerEventSeed true
}
```

When on, `PileUpMerger` reseeds `gRandom` at the start of every event with a
hash of (global `RandomSeed`, event index), so two runs over the same input with
the same `RandomSeed` get identical vertices and pile-up for every event (the
detector modules then diverge within the event, as they should). It throws if
`RandomSeed` is 0 (time-based), so a missing seed can't silently undo it.

How it is used here:

- `delphes_card_CMS_JetClassII_onlyFatJet.tcl` and `..._onlyFatJet_noPU.tcl`
  set `PerEventSeed true`; the HLT cards inherit it via
  `hlteff/generate_hlt_card.py`. (The `lite`/full/`JetClassI` cards don't.)
- `run.sh` draws one random nonzero seed per batch, logs it
  (`Batch <i>: Delphes RandomSeed <seed>`), and prepends it as
  `set RandomSeed <seed>` to a per-batch copy of every card of that batch.
- `run.sh` refuses to run (exit 1) if a card sets `PerEventSeed true` but
  `$DELPHES_PATH/libDelphes.so` doesn't contain the patch: an **unpatched Delphes
  silently ignores unknown parameters**, so without that check a fresh install
  would quietly fall back to independent overlays.

### Validation

300 `jetclass2/train_qcd` events, offline vs HLT card, same `RandomSeed`:

| | hard-vertex z equal | all vertex z equal | pile-up MET equal | first differing event |
|---|---|---|---|---|
| patched, `PerEventSeed true` | 100% | 100% | 100% | none |
| patched, `PerEventSeed true`, noPU cards | 100% | 100% | 100% | none |
| same seed, `PerEventSeed false` (stock behaviour) | 0.3% | 0.3% | 0.3% | event 1 |

Hard-vertex z spread 53.9 mm (card formula: 53 mm), 50.9 vertices per event
(MeanPileUp 50 + 1), all 300 events distinct. Full `run.sh` chain (200 events,
2 batches, paired cards): every vertex identical between the offline and HLT
Delphes outputs, different seeds and vertices per batch.

Ntuples produced before this (all productions up to and including
`output_jetclass2_10M_20260917_puppinocharged`) have independent vertices and
pile-up overlays in their offline and HLT versions of each event.

## HLT tracking efficiency should depend on the impact parameters

**Status:** found 2026-09-18; **implemented 2026-09-19** in the HLT card used
from `output_jetclass2_10M_20260919_nopuppi` on (see "Implemented version"
at the end of this section). The subsections "What the HLT card does now"
and "How it could be implemented" describe the state and plan before that.

### What FullSim HLT (ScoutingAK8) actually does

- Neither PUPPI nor CHS is applied: the scouting AK8 jets are reclustered in
  the ntuple production (DNNTuples `dev/AK15Scout`,
  `Ntupler/test/DeepNtuplizerAK8Scout.py`) from *all* scouting particles via
  CMSSW's `PhysicsTools/NanoAOD/python/run3scouting_cff.py`
  (`scoutingPFCandidate` with `CHS = cms.bool(False)`, then plain anti-kT
  R=0.8). Scouting particles have pT > 0.6 GeV (`HLTScoutingPFProducer`).
- Instead, the **HLT tracking itself** barely reconstructs tracks that are far
  from the leading vertex, in z or in the transverse plane. HLT matching
  efficiency of FullSim offline charged hadrons (QCD, not lost tracks,
  pT > 1 GeV; match: same charge, dR < 0.02, |pT ratio - 1| < 0.3; IPs w.r.t.
  the offline PV):

  | offline track class | per jet | HLT-matched |
  |---|---|---|
  | prompt (\|dxy\| < 0.1 mm), \|dz\| < 1 mm | 19.2 | 84% |
  | prompt, \|dz\| 1-10 mm | 0.16 | 52% |
  | prompt, \|dz\| > 10 mm (pile-up-like) | 0.25 | 0.8% |
  | \|dxy\| 0.1-1 mm | 2.4 | 47% |
  | \|dxy\| 1-10 mm | 2.0 | 2.6% |
  | \|dxy\| > 10 mm | 2.5 | 0.3% |
  | by CMS association: `fromPV==3` / `2` / `1` / `0` | 16.9 / 4.7 / 4.7 / 0.2 | 86% / 53% / 3% / 85% |

  i.e. HLT only finds tracks within roughly 1 cm of the leading vertex in z
  (the pile-up vertex spread is ~5 cm, so most pile-up tracks are never
  reconstructed - which *looks* like CHS although none is run), and almost no
  tracks with more than ~1 mm transverse displacement. (Presumably HLT tracking
  is seeded only around the leading pixel vertices; not verified against the
  2024 HLT menu.) Consistently, FullSim HLT jets contain only 0.09 prompt
  charged hadrons per jet with |dz| > 10 mm (pT > 0.5 GeV, jets 200-700 GeV),
  vs 2.4 in a Delphes HLT variant without any pile-up track removal.
- Scouting `dz`/`dxy` are w.r.t. the leading pixel vertex
  (`HLTScoutingPFProducer.cc`: `dz = trk->dz(pv.position())`,
  `pv = (*vertexCollection)[0]`, `vertexCollection = hltPixelVertices`).

### What the HLT card does now

The two effects above are emulated only indirectly:

- **Tracks far from the PV in z (pile-up):** removed by the CHS step that is
  built into our `RunPUPPI` (charged weights are hard-set to 1/0 from the
  truth-based `TrackPileUpSubtractor` association, `ApplyCHS` being hardcoded to
  true in `RunPUPPI.cc`), i.e. by running (a modified version of) PUPPI
  instead of never reconstructing them in the first place. With
  `ZVertexResolution {0.0001}` (0.1 mm) this removes essentially *all* pile-up
  tracks, slightly more than HLT (which keeps pile-up within ~1 cm). PUPPI
  additionally reweights/removes neutrals, which FullSim HLT does not do.
- **Transversely displaced tracks:** not removed at all. Their HLT loss is only
  absorbed into the flat (IP-independent) data-driven tracking efficiency:
  `hlteff/derive_curves.py` measures n_matched / n_offline over *all* offline
  `cpfcandlt` charged candidates, a population with many displaced tracks
  (|dxy| > 0.1 mm: 7.8 per jet in FullSim offline vs 2.1 in our Delphes offline -
  Delphes has no material interactions/conversions) plus 3.7 lost tracks per
  jet. The resulting average (HLT/offline ~0.59) is therefore too low for
  Delphes' mostly prompt tracks (prompt tracks: ~0.84 above 1 GeV), and there is
  no IP dependence.

For reference, HLT/offline ratios of mean per-jet counts (QCD; 300-event test,
same vertex/pile-up in all runs) for HLT-card variants vs FullSim:

| HLT variant | charged had. | neutral had. | photons | jet pT |
|---|---|---|---|---|
| current (PUPPI, `UseCharged false`) | 0.57 | 2.05 | 1.14 | 1.08 |
| CHS only, no PUPPI | 0.57 | 2.98 | 1.45 | 1.13 |
| no PUPPI, no CHS | 0.80 | 2.98 | 1.45 | 1.16 |
| FullSim | 0.59 | 2.29 | 1.52 | 1.00 |

(The test sample has lower jet pT than FullSim; in matching jet-pT bins
FullSim's neutral-hadron ratio is 2.73 at 200-400 GeV and 2.48 at 400-700 GeV,
so "CHS only" overshoots neutrals by ~10%.)

### How it could be implemented (card-level, no Delphes source change)

1. **Re-derive the tracking efficiency for prompt tracks only:** in
   `hlteff/derive_curves.py`, restrict the offline denominator to
   `cpfcandlt_isLostTrack == 0` and prompt tracks (e.g. |dxy| < 0.1 mm and
   |dz| < 1 mm, or `fromPV >= 2`).
2. **Add the transverse-IP dependence:** Delphes efficiency formulas can use
   `d0` (`classes/DelphesFormula.cc` maps `d0`, `dz`, `ctgTheta`, `radius`), and
   `D0` is already set by `ParticlePropagator`, which runs before the
   `*TrackingEfficiency` modules. Multiply the prompt efficiency by a d0 factor
   measured as above (roughly 1 / ~0.5 / ~0.03 / ~0 for |d0| < 0.1 / 0.1-1 /
   1-10 / > 10 mm relative to prompt; re-measure in pT bins). Note Delphes
   `D0` is in mm and has the opposite sign to CMS `dxy` (see the IP section);
   use `abs(d0)`.
3. **Emulate the z acceptance instead of CHS/PUPPI:** `dz` in the formula is the
   *absolute* z of closest approach (not PV-relative), so it can't express "within
   1 cm of the PV" directly. Instead widen `TrackPileUpSubtractor`'s
   `ZVertexResolution` from `{0.0001}` (0.1 mm) to ~`{0.005}`-`{0.01}`
   (5-10 mm; value in m), which removes (by truth) only pile-up tracks farther than
   that from the PV, and cluster the HLT jets from
   `TrackPileUpSubtractor/eflowTracks` + `ECal/eflowPhotons` +
   `HCal/eflowNeutralHadrons` (one extra `Merger`; rewire
   `FastJetFinderPUPPIAK8/AK15` and the `ParticleFlowCandidate` TreeWriter branch)
   with no PUPPI.
4. Then re-check the neutral hadron/photon ratios (fewer lost tracks means less
   unsubtracted track energy ending up as neutrals, so the neutral excess
   should drop), and re-derive `JetEnergyScalePUPPIAK8` (currently derived for
   PUPPI jets; without PUPPI the HLT jet pT comes out ~13% high).

Scratch scripts used for the numbers above (not in the repo):
`compare.py` (per-type ratios per HLT variant) and `displacement.py`
(HLT matching efficiency by track class).

### Implemented version (HLT card from 2026-09-19, `output_jetclass2_10M_20260919_nopuppi`)

Generated with

```
python hlteff/generate_hlt_card.py --puppi-use-charged false \
    --ip-curves hlteff/curves_ip_qcd.json --no-puppi --pu-track-z-window 2.5 \
    --hlt-pf-pt-min 0.6 --calo-granularity-factor 1.25 \
    --jes-correction hlteff/jes_correction_nopuppi.json
```

- `--ip-curves`: charged-hadron/muon efficiency in (|eta|, pT, |d0|) bins from
  `hlteff/derive_ip_curves.py` (293k FullSim QCD jets; plots via
  `hlteff/plot_ip_curves.py`).
- `--no-puppi --pu-track-z-window 2.5`: HLT jets from all PF candidates, pile-up
  tracks kept only within 2.5 mm of the PV (measured HLT z acceptance: a sharp
  drop between 2 and 3 mm).
- `--hlt-pf-pt-min 0.6`: every scouting candidate has pT >= 0.600 GeV.
- `--calo-granularity-factor 1.25`: hand-tuned; brings the neutral-hadron
  count change close to FullSim (scan of HCal/ECal thresholds and
  granularity, 2026-09-19: HCal thresholds are unusable - raising them also
  destroys charged hadrons through the track-rescale artifact above; ECal
  thresholds cannot fix the jet-pT dependence of the photon excess).
- `--jes-correction`: per-HLT-jet-pT factors (0.83-0.92) on
  JetEnergyScalePUPPIAK8 from `hlteff/derive_hlt_jes_correction.py`
  (12k QCD events), needed because of the offline PUPPI bug below.

Validation on independent QCD events, HLT/offline per-jet change (jet pT
200-400 / 400-700 / >700 GeV) vs FullSim: neutral hadrons +191/+159/+103% vs
+173/+148/+111%; photons +77/+71/+39% vs +56/+52/+50%; charged hadrons
-29/-27/-29% vs -39/-40/-42% (FullSim's offline includes lost and displaced
tracks Delphes doesn't have); displaced (|d0|>1 mm) charged hadrons at HLT
0.1 vs 0.0 per jet; jet pT ratio ~+5-10% above FullSim at 200-500 GeV,
within ~5% above (the remaining offset comes from our wider, skewed
HLT/offline spread, which a scale factor can't remove).

## Delphes PUPPI bug: track charge never passed to PUPPI (offline neutrals over-suppressed)

**Status:** known, deliberately NOT fixed (found 2026-09-19): fixing it would
change the offline sample (and its agreement with central JetClass-II).

In `modules/RunPUPPI.cc`, `curRecoObj.charge` is only set for neutrals
(`= 0`), never for tracks, and `RecoObj`'s constructor
(`external/PUPPI/RecoObj2.hh`) doesn't initialise it - so every track's
charge is uninitialised memory. `PuppiContainer::initialize` derives the
particle's user_index from it (0 neutral, charge for leading-vertex tracks,
charge+5 for pile-up tracks), and `PuppiAlgo::add` treats |user_index| >= 3
as pile-up; with garbage values, leading-vertex tracks end up in PUPPI's
pile-up reference, and genuine neutrals in jets get weights << 1. Still
present in upstream Delphes master (checked 2026-09-19).

Effect on our offline card, even WITHOUT pile-up (1 vertex): pT-weighted
mean PUPPI weight 0.34 for photons, 0.22 for neutral hadrons (weight 0 for
62%/81% of them); offline keeps 266 of 821 GeV of photon pT per event
(truth), and offline AK8 jets come out at 0.82-0.90 of the gen-jet pT
(FullSim offline: ~0.92, with PUPPI weights of in-jet neutrals ~1). Charged
hadrons are unaffected (their weights are hard-set by vertex association).

This is why an HLT card without PUPPI (whose jets don't lose that neutral
energy) shows a large apparent HLT neutral "excess" and HLT/offline jet-pT
ratio of 1.25-1.3 relative to our offline, and why the no-PUPPI HLT card
needs `--jes-correction`. It also explains why `UseCharged false` had such a
large effect on the earlier PUPPI-based HLT card (with it, PUPPI never uses
the broken classification).

Fix (tested in a scratch copy only, 2026-09-19): set
`curRecoObj.charge = candidate->Charge;` for tracks in `RunPUPPI.cc` and add
`charge(0)` to the `RecoObj` constructor. Without pile-up, offline PUPPI then
keeps all neutrals, and our offline photon energy per jet matches FullSim's -
but our offline neutral *counts* per jet then exceed FullSim's, so it was
not adopted.
