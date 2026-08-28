# hlteff

Derives the HLT-like Delphes card (`delphes_cards/delphes_card_CMS_JetClassII_onlyFatJet_HLT{,_noPU}.tcl`)
from real paired CMS offline/scouting data, instead of by hand-tuning
numbers to qualitatively match a set of reference plots (which is how the
first version of that card was built).

## Why

CMS's Phase-2 "Scouting" HLT reconstruction runs a lighter version of
particle-flow reconstruction online (fewer tracking iterations, simplified
pileup mitigation, etc.), which is measurably worse than the offline
reconstruction of the same physical jet - particularly for charged-particle
tracking. The first version of `delphes_card_CMS_JetClassII_onlyFatJet_HLT.tcl`
approximated this by hand-adjusting the offline card's `Efficiency`/
`MomentumSmearing`/`TrackSmearing` formulas to qualitatively match a set of
reference comparison plots (particle-pT spectra, jet-constituent counts,
particle-ID composition) built from real CMS offline-vs-scouting data. That
got the right shape but the actual numbers were guesses.

This directory instead measures those same offline-vs-HLT differences
directly from the underlying paired data and turns the measurement into the
new Delphes card automatically, so the card is reproducible and traceable
rather than a black box of chosen numbers.

## Data source

`/eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/` contains
`dnnTuples_nanov15_*.root` files, one row per AK8 jet, with **both** its
offline reconstruction and its scouting (HLT) reconstruction of the *same*
physical jet stored side by side and already geometrically paired (checked:
median deltaR between the offline and scouting jet axes is ~0.005, and the
scouting/offline jet pT ratio is 0.99 +/- 0.17 - consistent with these
being independent reconstructions of the same underlying jet, not
independently selected jets).

Two subdirectories are available: `QCD_PT-mixed_TuneCP5_13p6TeV_pythia8_new/`
and `H0HpHm_mixed_new/` (charged/neutral Higgs signal). **This pipeline
starts from QCD** - it's the more generic, broadly representative sample
(no particular decay topology or mass point biasing the particle content),
and it's easier to justify tuning a generic detector-response
parameterization off of it than off of a specific signal process. The
Higgs sample is there for a cross-check once the QCD-derived card exists
(not yet done here - see "Next steps").

Relevant branches per jet (see `derive_curves.py` for the exact list used):
- `fj_*` / `scoutfj_*`: offline / scouting jet kinematics and class labels
- `cpfcandlt_*`: offline charged PF candidates *and* recovered lost tracks
  (`n_lts` says how many of the total are lost-track recoveries), with
  `isChargedHad`/`isEl`/`isMu` type flags, `px`/`py`/`pz`/`energy`, and
  impact parameters `dxy`/`dxysig`/`dz`/`dzsig`
- `npfcand_*`: offline neutral PF candidates (`isGamma`/`isNeutralHad`) -
  not used by this pipeline (see "Scope" below)
- `scoutpfcand_*`: scouting PF candidates, one combined collection with the
  same property set as the two offline collections together
- `etarel`/`phirel` on all three particle collections: eta/phi relative to
  the particle's own jet axis - used for matching (see Method) since it
  sidesteps reconstructing each particle's absolute eta/phi from px/py/pz
  by hand

Each file is ~3.2 GB and there are ~39 in the QCD directory; this pipeline
reads only a configurable subset of jets from a configurable number of
files (see Usage) - a few hundred thousand jets is enough for good
statistics in every bin except the very highest-pT tail.

## Scope

The offline card has 37 `module` blocks. Of those, 9 have a physics
parameter that plausibly differs between offline and HLT reconstruction
*and* is measurable from this dataset, and are retuned here:

| Module | Quantity | Combination |
|---|---|---|
| `ChargedHadronTrackingEfficiency` | charged hadron tracking efficiency | multiplicative |
| `ElectronTrackingEfficiency` | electron tracking efficiency | multiplicative |
| `MuonTrackingEfficiency` | muon tracking efficiency | multiplicative |
| `ChargedHadronMomentumSmearing` | charged hadron pT resolution | quadrature |
| `ElectronMomentumSmearing` | electron pT resolution | quadrature |
| `MuonMomentumSmearing` | muon pT resolution | quadrature |
| `TrackSmearing` (`D0ResolutionFormula`) | dxy impact-parameter resolution | quadrature |
| `TrackSmearing` (`DZResolutionFormula`) | dz impact-parameter resolution | quadrature |
| `JetEnergyScalePUPPIAK8` | jet energy scale | multiplicative |

Everything else in the generated card - calorimeter response (`ECal`/`HCal`),
`RunPUPPIBase` (PUPPI itself), `TrackPileUpSubtractor.ZVertexResolution`,
`JetEnergyScalePUPPIAK15`, and every merger/filter/geometry/truth-level
module - is copied unchanged from the offline card. See "Known limitations"
for why those are out of scope *for now* rather than because they don't
matter, and the top-level repo README/conversation history for the full
37-module inventory with a difficulty assessment for each remaining one.

Neutral particles (photons, neutral hadrons) aren't retuned: Delphes
doesn't have an `Efficiency` module for them in this card (`ECal`/`HCal`
always produce a tower deposit above their energy thresholds), so there's
no equivalent knob to turn - only their calorimeter resolution formulas
would be a lever, which is out of scope here.

## Method

### 1. `derive_curves.py` - measure

For each jet, and separately for three particle categories (charged
hadron, electron, muon, via each collection's own type flags): every
offline candidate is greedily matched to the geometrically closest scouting
candidate of the *same category* within the same jet (closest deltaR pairs
assigned first, so no scouting candidate is claimed by two offline
candidates), using a configurable `--dr-max` window. Absolute eta/phi for
matching are recovered as `jet_eta/phi + etarel/phirel` for each
collection's own jet axis.

Candidates are binned by (their own pT, |eta|) into bins defined once in
`binning.py` (shared with `generate_hlt_card.py` so both stages agree on
what "the same bin" means). Per bin, per category, we record:
- `n_offline`, `n_matched` -> `efficiency_ratio = n_matched / n_offline`:
  the fraction of offline candidates that scouting also reconstructs (as
  the same particle type) - i.e. what fraction of the offline module's own
  output should additionally survive to represent scouting.
- for matched pairs, the distribution of `(pt_scout - pt_offline) / pt_offline`,
  summarized as a robust sigma (half the 16th-84th percentile width, i.e.
  the usual "1 sigma" definition but far less sensitive than a plain
  standard deviation to the occasional wrong/combinatorial match) - this is
  the *extra* smearing scouting adds on top of whatever the offline pT
  resolution already is for that candidate.

For every matched pair, regardless of category (pooled across chargedHadron/
electron/muon, matching `TrackMerger`'s own species-agnostic pooling
upstream of `TrackSmearing`), we additionally record `scout_dxy - off_dxy`
and `scout_dz - off_dz`, converted from the ntuple's cm to the Delphes
card's mm (see "Notable findings" for how that unit inference was made) -
the same kind of "extra smearing" measurement as pT, but for the impact
parameters `D0`/`DZResolutionFormula` model.

Separately, and needing no per-particle matching at all (the jets
themselves are already paired row-by-row - see "Data source"), each jet's
own reconstructed-pT/gen-jet-pT response is measured on the offline side
(`fj_pt/fj_genjet_pt`) as a validation number, and the direct
`scoutfj_pt/fj_pt` ratio is measured for the actual `JetEnergyScalePUPPIAK8`
correction - see "Notable findings" for why there's no truth-based
measurement on the scouting side in this ntuple production, and "Known
limitations" for the resulting caveat.

Output: `curves_qcd.json` (binning, per-category grids of the above, plus
provenance metadata: which files, how many jets, what deltaR window).

**Neutral particles** (`photon`/`neutralHadron`, via `npfcand_*`/`scoutpfcand_*`
`isGamma`/`isNeutralHad` flags) are matched the same way, but binned by
*energy* (`PT_EDGES` reused as an energy grid, since `ECal`/`HCal`'s
`ResolutionFormula` is a function of energy, not pT) rather than pT, and the
"extra smearing" is an *absolute* energy difference in GeV (not relative -
unlike the fractional pT resolution formulas, these are already
absolute-GeV). This doesn't feed `generate_hlt_card.py` directly (no
Efficiency module exists for neutrals - see "Scope") - it feeds
`check_calo_closure.py` instead.

### 2. `generate_hlt_card.py` - translate into a Delphes card

Takes `curves_qcd.json` and the offline Delphes card
(`delphes_cards/delphes_card_CMS_JetClassII_onlyFatJet.tcl`, treated as a
given, not duplicated) and, for each of the 9 modules in scope:
- reads the *actual* offline formula out of the offline `.tcl` file (via
  brace-matching text extraction, not a hardcoded copy - see
  `delphes_formula.py`) and evaluates it at each bin's center using a small
  restricted expression evaluator (translates Delphes' pT/eta formula
  syntax, e.g. `^` for power vs. Tcl's native bitwise-XOR meaning, so this
  is *not* just handing the string to a real Tcl interpreter),
- combines it with the matching data-driven curve from `curves_qcd.json`,
  using whichever of two rules physically fits that quantity:
  - **multiplicative** (tracking efficiencies, jet energy scale): `HLT = offline * data_ratio`
  - **quadrature** (pT and impact-parameter resolutions): `HLT = sqrt(offline^2 + extra^2)`
- writes the result back out as an explicit `(eta bin) * (pt bin) * (value)`
  piecewise table - the same style already used by this repo's hand-written
  `TrackSmearing` D0/DZ tables - so the generated card is self-contained and
  human-readable, not a symbolic expression referencing the offline file.

Bins with too little data to trust (`--min-count` offline candidates for
efficiency, `--min-pairs` matched pairs or a suspiciously large sigma via
`--max-sigma` for resolution - guards against low-efficiency bins where the
few "matches" that exist are mostly combinatorial, not real) fall back to
the nearest pT bin in the same eta row that does have usable data. If an
eta row has no usable data at all, that row falls back to "no measured
degradation" (the offline value, unmodified) and a warning is printed - in
practice this only happens in the very highest-pT tail bins.

The pileup (`MeanPileUp 50`) and no-pileup (`MeanPileUp 0`) variants are
both written from the same generated text, exactly like the hand-tuned card
before it.

### 3. `check_calo_closure.py` - validate the ECal/HCal simplification

`ECal`/`HCal` have no Efficiency module - a neutral particle's "reconstructed
or not" only exists implicitly, as whatever fraction of its Gaussian-smeared
energy clears the fixed `EnergyMin`/`EnergySignificanceMin` zero-suppression
thresholds. Since those thresholds are a hardware noise-floor property
(same calorimeter reads the same hits online and offline) rather than a
reconstruction-quality one, the natural retuning move is to degrade only
`ResolutionFormula` and leave the thresholds fixed - but that's an
assumption, not a given, so this script checks it rather than just applying
it: for each (category, |eta|, energy) bin, it combines the offline
`ResolutionFormula` with the measured extra energy-smearing in quadrature,
computes what fraction of a Gaussian centered at that energy would clear
`max(EnergyMin, EnergySignificanceMin * sigma)` (a normal-CDF calculation,
approximating - not bit-exact to - Delphes' own C++ accept logic), and
compares that *predicted* efficiency to the neutral efficiency *directly
measured* in the same real data (matched photon/neutralHadron pairs, exactly
like the tracking categories). Prints a per-bin table and saves
`hlteff/plots/closure_calo_{photon,neutralHadron}.png`. Does not modify any
Delphes card - purely diagnostic, see "Notable findings" for the result.

## Usage

```bash
# from the jetclass-generation directory, with an LCG/ROOT+uproot environment sourced, e.g.:
source /cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh

# 1. measure (takes a while - reads real ntuples off /eos; ~a few hundred
#    jets/s, so a few hundred thousand jets is a few tens of minutes)
python hlteff/derive_curves.py --n-files 3 --max-jets 250000

# 2. translate into the Delphes card(s)
python hlteff/generate_hlt_card.py

# 3. (optional) visualize: offline vs generated-HLT vs raw data curves,
#    one figure per module, one panel per |eta| bin, saved to hlteff/plots/
python hlteff/plot_curves.py

# 4. (optional) check whether ECal/HCal could be retuned by degrading only
#    ResolutionFormula, holding EnergyMin/EnergySignificanceMin fixed - a
#    diagnostic only, does not touch any card (see "Method" step 3)
python hlteff/check_calo_closure.py
```

`derive_curves.py`'s `--input-dir`/`--n-files`/`--max-jets`/`--dr-max` and
`generate_hlt_card.py`'s `--min-count`/`--min-pairs`/`--max-sigma` are all
worth revisiting if you want tighter statistics, a different matching
window, or different trust thresholds - nothing about the pipeline is
QCD-specific except the default `--input-dir`.

## Notable findings

Worth flagging since they weren't obvious going in, and shaped what the
generated card looks like:

- **ECal/HCal closure check result (see Method step 3): resolution-only
  works reasonably for photons, does not for neutral hadrons.** Run at full
  statistics (256k jets) via `check_calo_closure.py`:
  - **Photons (ECal)**: the predicted (resolution-only) and measured
    efficiency curves track the same qualitative turn-on shape (see
    `hlteff/plots/closure_calo_photon.png`), but not precisely - the model
    is too *pessimistic* at very low energy (predicts 10-30% where data
    shows 40-90% in the barrel) and slightly too *optimistic* at high
    energy (predicts ~100% where data plateaus at 94-99% barrel, and is
    both lower and more scattered in the endcap, 60-100%). A workable
    first approximation, not a precise one.
  - **Neutral hadrons (HCal)**: does not closure at all
    (`hlteff/plots/closure_calo_neutralHadron.png`). Measured efficiency
    rises smoothly and stays around 85-95% (barrel) across nearly the
    whole energy range; the resolution-only prediction instead has a
    severe, unphysical *dip* down to ~30% around 30-100 GeV before
    climbing back up. The root cause: the raw matched-pair "extra
    smearing" measurement itself explodes from a few GeV at ~10-20 GeV
    particle energy to 100-330 GeV (!) by a few hundred GeV - i.e. bigger
    than the particle's own energy, which a symmetric Gaussian resolution
    widening cannot represent as a sane "spread." This is more likely
    genuine hadronic-shower matching confusion (HCal showers are much
    broader than ECal ones, more prone to overlapping/being mismatched in
    dense high-pT jet cores) and/or a real non-Gaussian online calibration
    difference, than an actual resolution effect - meaning "hold thresholds
    fixed, only widen resolution" is *not* a safe simplification for HCal
    as currently measured, and applying it directly would bake a spurious
    dip into the card.
  - **Tried tightening the matching to test the mismatch hypothesis - it
    didn't help, and is informative on its own.** `match_jet()` (see its
    docstring) can optionally rank candidate pairs by a combined
    geometric+energy metric instead of pure deltaR (a soft tie-break among
    candidates already within the deltaR window, not a second hard cut),
    and `derive_curves.py` gained `--dr-max-neutral`/`--neutral-use-energy`/
    `--rel-e-tol` to drive it (off by default - see below for why). Tested
    at `--dr-max-neutral 0.015 --neutral-use-energy` (half the default
    deltaR window, plus energy-aware tie-breaking) on 60k jets: the HCal
    sigma blowup was **essentially unchanged** (same magnitude, same ~20-25
    GeV onset) - evidence *against* nearest-neighbor mismatching as the
    cause, and *for* a genuine reconstruction-topology difference (e.g.
    offline resolving one large shower into multiple candidates that a
    simpler online clustering merges into one, or vice versa - not
    something any 1-to-1 particle-matching scheme can fix). Photon (ECal)
    got measurably *worse*: a tighter window starts excluding genuine
    matches whose shower centroid shifts a bit between offline/HLT
    reconstruction, turning what had been a smoothly rising measured
    efficiency curve into a dip. **Conclusion: keep the default (loose,
    geometry-only) matching - it's the better of the two tested options for
    both calorimeters. Worth pursuing a real ECal retune (with the
    documented residual imprecision); HCal's matched-pair measurement isn't
    fixable by better matching alone, so it needs either a fundamentally
    different measurement (e.g. jet/cluster-level rather than particle-level,
    similar in spirit to how JetEnergyScalePUPPIAK8 sidesteps particle
    matching entirely) or a set of reasonable hand-set assumptions ("plan
    B") instead of a matched-pair-driven retune.** Not yet acted on for
    either calorimeter - this whole item is the check the user asked for,
    not (yet) a card change.
- **Scouting reconstructs essentially zero electrons in this QCD sample**:
  `scoutpfcand_isEl` is `!= 0` for exactly 0 of ~2.4M scouting candidates
  checked (across a full file) - not "rare", *none*. The generated
  `ElectronTrackingEfficiency` HLT formula is correspondingly flat zero
  everywhere (see `hlteff/plots/efficiency_electron.png`) - this is the
  measurement, not a fallback-to-no-data artifact (most bins have plenty of
  offline candidates, e.g. thousands in the few-GeV range; they just never
  find a scouting match). Muons fare better but are still heavily
  suppressed (~13% of the offline rate matched at scouting level,
  `hlteff/plots/efficiency_muon.png`).
- **Charged-hadron tracking efficiency turns over at high pT, not just low
  pT**: it rises from ~0 below 0.5 GeV to a peak of ~70% (barrel) around
  5-15 GeV, then *declines again* through the hundreds-of-GeV range (see
  `hlteff/plots/efficiency_chargedHadron.png`). This wasn't anticipated by
  the original hand-tuned card (which had efficiency recover to
  near-offline above ~1 GeV and stay there) and is a plausible explanation
  for why the reference comparison plots that motivated this whole
  exercise showed the offline/HLT constituent-count gap *growing* with jet
  pT rather than shrinking - a harder jet has more of its own particles
  landing in this high-pT-per-particle range where efficiency is falling
  again, not just more soft particles near threshold.
- **dxy/dz units**: the ntuple's `cpfcandlt_dxy`/`dz` have a median
  magnitude of ~0.004 (offline), which only makes physical sense as
  centimeters (~43 micron, a typical track's impact-parameter resolution);
  the offline card's own `D0ResolutionFormula` table's endpoints (0.35 at
  very low pT, 0.011 at very high pT) match published CMS d0-resolution
  curves almost exactly *in millimeters*. `derive_curves.py` therefore
  applies an explicit x10 cm-to-mm conversion (`CM_TO_MM`) before combining
  the two - inferred from magnitude, not confirmed by any ntuple metadata,
  so worth double-checking if this ever looks off.
- **Offline jets are not at truth scale either**: `fj_pt/fj_genjet_pt`
  (real gen-jet truth, barrel) ranges from a median of **0.90-0.93** at
  200-1000 GeV jet pT up to **0.95-0.99** at 2-5 TeV - i.e. even offline
  reconstruction (uncorrected PUPPI, no JEC) sits measurably below truth,
  more so at lower jet pT, which is why the offline card's
  `ScaleFormula {1.00}` ("no correction") isn't itself a truth-validated
  choice - it's a simplification the whole pipeline (including this
  extension) inherits rather than re-litigates. The scouting-vs-offline
  ratio actually used for the HLT correction is a much smaller effect by
  comparison: +2.9% at 200-250 GeV, crossing 1.0 around 500-650 GeV, down to
  -1.2% at 3-5 TeV (barrel; see `hlteff/plots/scale_jetEnergyPUPPIAK8.png`).

## Known limitations / not yet data-driven

- **Jet energy scale double-counting risk**: `JetEnergyScalePUPPIAK8`'s
  correction is measured as the direct real-data `scoutfj_pt/fj_pt` ratio
  (see "Notable findings" for why, not a truth-based measurement) and
  applied *on top of* jets built from the already-retuned track-level
  modules. Those upstream modules already shift the simulated HLT jet's pT
  somewhat (fewer/worse-measured constituents feeding PUPPI), so there's a
  real, currently unvalidated risk of the two effects overlapping rather
  than being independent. The clean way to check this is a closure test:
  generate with the new card, measure the *simulated* offline/HLT jet-pT
  ratio, and see whether it already reproduces this real-data ratio on its
  own (in which case this module's correction is redundant / should be
  softened) or falls short of it (in which case it's a genuine residual
  correction) - not done here.
- **`JetEnergyScalePUPPIAK15`**: not retuned - this ntuple production is
  scouting-*AK8* only (`ScoutingAK8` in the very path), so there's no data
  to derive an AK15-specific number from, and jet energy scale is
  genuinely jet-radius-specific (different pileup/UE contamination) so the
  AK8 number shouldn't just be copied over.
- **`TrackPileUpSubtractor.ZVertexResolution`** and **`RunPUPPIBase`** (PUPPI
  itself): not retuned. The former would need a paired primary-vertex
  resolution measurement this ntuple may not carry (not checked); the
  latter is a multi-parameter jet-level algorithm, not a per-particle
  efficiency/resolution curve, so "measure a ratio and multiply" doesn't
  apply the way it does everywhere else - the offline card's own header
  already documents a considered reason to leave it alone (real CMS
  Phase-2 scouting runs the same PUPPI algorithm online; degradation is
  modeled upstream, in the tracks it receives).
- **Neutral particles**: no efficiency retuning (see "Scope"); calorimeter
  resolution retuning for photons/neutral hadrons is a possible future
  extension using `npfcand_*`/the neutral part of `scoutpfcand_*`, not
  attempted here.
- **Statistics thin out at high particle pT** (above ~100-200 GeV per
  particle): the fallback behavior described above keeps the card
  physically sane there (falls back toward the offline value rather than
  extrapolating noise), but the highest-pT bins are correspondingly less
  trustworthy than the bulk of the spectrum. More files/jets via
  `--n-files`/`--max-jets` directly improves this.
- **Matching is geometric only** (deltaR within category), with no
  cross-check against generator truth (these ntuples don't carry
  per-candidate gen-particle links) - an offline candidate that's itself a
  fake, or a genuine but different particle that happens to land within
  `--dr-max` of a scouting candidate, would be counted as a "match". This
  is expected to be a small effect in the well-populated bins (borne out by
  the very tight resulting resolution values there) but is a likelier
  contributor to the noisy/huge sigma values seen in the lowest-pT, near-zero-
  efficiency bins, which is exactly why `--max-sigma` exists.

## Next steps (not done here)

- Cross-check the QCD-derived card against the `H0HpHm_mixed_new/` sample
  (e.g. rerun the `testing/plot_pt.py` / `testing/plot_composition.py`
  comparisons from the main generation pipeline using this card, or run
  `derive_curves.py` pointed at the Higgs sample and compare curves
  directly) - per the original request, QCD is deliberately the *starting*
  point, not necessarily the last word.
- Run the JES closure test described above (see "Known limitations") before
  trusting `JetEnergyScalePUPPIAK8`'s correction as a genuine residual
  rather than a possible double-count.
- `TrackPileUpSubtractor.ZVertexResolution` and `RunPUPPIBase`: check
  whether this ntuple carries anything usable for the former; the latter
  would need a real design decision (external CMS scouting-PUPPI settings,
  or a multi-parameter fit against substructure observables), not just
  "add another matched-pair measurement."
- Consider deriving a jet-level or eta-extended (>2.5, currently hard cut
  to zero like the offline card) version if the generation pipeline ever
  needs forward jets.
