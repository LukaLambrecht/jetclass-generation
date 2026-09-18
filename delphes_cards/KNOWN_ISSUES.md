# Known issues in the Delphes cards

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
