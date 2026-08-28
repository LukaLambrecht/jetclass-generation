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

`calorimeters/` is a separate subfolder (own README) holding the
measurement/closure-check/granularity-scan tools used to investigate
whether ECal/HCal could be retuned the same data-driven way - kept apart
from the files here to avoid clutter, since that investigation ended up
concluding "no" and feeding hand-set numbers into `generate_hlt_card.py`
instead (see "Scope" below) rather than a routine part of regenerating the
card.

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

The offline card has 37 `module` blocks, in four groups:
- **8 tuned directly from data** (the table below).
- **2 tuned from a hand-set "reasonable guess"** (`ECal`, `HCal` - see below).
- **3 that plausibly need tuning too but aren't attempted here**:
  `TrackPileUpSubtractor` (its `ZVertexResolution`), `RunPUPPIBase` (PUPPI
  itself), `JetEnergyScalePUPPIAK15` - see "Known limitations" for why each
  is out of scope *for now* rather than because it doesn't matter.
- **24 that don't need tuning at all** - mergers/filters/geometry/truth-level
  modules with no offline-vs-HLT physics distinction to make (`PileUpMerger`,
  `ParticlePropagator`, `TrackMerger`, `ElectronFilter`, `RecoPuFilter`,
  `TowerMerger`, `NeutralEFlowMerger`, `EFlowMerger`, `LeptonFilterNoLep`,
  `LeptonFilterLep`, `RunPUPPIMerger`, `RunPUPPI`, `EFlowFilterPuppi`,
  `MissingET`, `PuppiMissingET`, `GenPileUpMissingET`, `ScalarHT`,
  `NeutrinoFilter`, `GenJetFinderAK8`, `GenJetFinderAK15`, `GenMissingET`,
  `FastJetFinderPUPPIAK8`, `FastJetFinderPUPPIAK15`, `TreeWriter`).

(8 + 2 + 3 + 24 = 37 - every module accounted for exactly once.)

The 8 data-driven modules:

| Module | Quantity | Combination |
|---|---|---|
| `ChargedHadronTrackingEfficiency` | charged hadron tracking efficiency | multiplicative, data-driven |
| `ElectronTrackingEfficiency` | electron tracking efficiency | multiplicative, data-driven |
| `MuonTrackingEfficiency` | muon tracking efficiency | multiplicative, data-driven |
| `ChargedHadronMomentumSmearing` | charged hadron pT resolution | quadrature, data-driven |
| `ElectronMomentumSmearing` | electron pT resolution | quadrature, data-driven |
| `MuonMomentumSmearing` | muon pT resolution | quadrature, data-driven |
| `TrackSmearing` (both `D0ResolutionFormula` and `DZResolutionFormula`) | dxy/dz impact-parameter resolution | quadrature, data-driven |
| `JetEnergyScalePUPPIAK8` | jet energy scale | multiplicative, data-driven |

And the 2 hand-set ("plan B") modules:

| Module | Quantity | Combination |
|---|---|---|
| `ECal` (`ResolutionFormula` + tower grid) | photon energy resolution + granularity | multiplicative + grid coarsening, **hand-set ("plan B")** |
| `HCal` (`ResolutionFormula` + tower grid) | neutral hadron energy resolution + granularity | multiplicative + grid coarsening, **hand-set ("plan B")** |

`ECal`/`HCal` don't get a genuine data-driven retuning like the other 8,
because they have no `Efficiency` module to begin with - a neutral
particle's "reconstructed or not" only exists implicitly, as whatever
fraction of its smeared energy clears the (unchanged) `EnergyMin`/
`EnergySignificanceMin` thresholds. Investigating whether that's still
retunable via `ResolutionFormula`/tower-granularity alone is what
`calorimeters/` is for - see `calorimeters/README.md` for the full
investigation and why it ended in hand-set numbers rather than a
measurement.

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
absolute-GeV). This measurement does NOT feed the actual ECal/HCal card
generation (that uses hand-set "plan B" values instead - see "Scope") - it
only fed the closure check that led to that decision, in
`calorimeters/check_calo_closure.py`.

### 2. `generate_hlt_card.py` - translate into a Delphes card

Takes `curves_qcd.json` and the offline Delphes card
(`delphes_cards/delphes_card_CMS_JetClassII_onlyFatJet.tcl`, treated as a
given, not duplicated) and, for each of the 8 modules in scope:
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

### 3. `apply_calo_plan_b()` (inside `generate_hlt_card.py`) - hand-set ECal/HCal

`ECal`/`HCal` are handled entirely differently from the other 8 modules,
because the data-driven approach was investigated in depth and doesn't work
for them (matched-pair measurement, closure checks, and a tower-granularity
scan - see `calorimeters/README.md` for the full investigation and why it
concluded with hand-set numbers). What's actually applied to the card:
- `ResolutionFormula` (both `ECal` and `HCal`): the offline formula's literal
  text is wrapped as `(offline formula) * --calo-resolution-degradation`
  (default 1.5, i.e. a 50% degradation) - no data-driven table involved.
- `HCal`'s tower grid (`EtaPhiBins`) is additionally coarsened by
  `--hcal-granularity-factor` (default 2) in both eta and phi, using
  `calo_grid.py` (parses the offline grid, downsamples its eta/phi edge
  lists by the factor per region, regenerates valid Tcl).
- `EnergyMin`/`EnergySignificanceMin` (the zero-suppression thresholds) are
  left untouched in both modules.

These are documented placeholder assumptions, not measurements - see
`calorimeters/README.md` for why, and revisit if a better-founded approach
becomes available.

## Usage

```bash
# from the jetclass-generation directory, with an LCG/ROOT+uproot environment sourced, e.g.:
source /cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh

# 1. measure (takes a while - reads real ntuples off /eos; ~a few hundred
#    jets/s, so a few hundred thousand jets is a few tens of minutes)
python hlteff/derive_curves.py --n-files 3 --max-jets 250000

# 2. translate into the Delphes card(s) - also applies the hand-set ECal/HCal
#    "plan B" (see Method step 3); tune with --calo-resolution-degradation /
#    --hcal-granularity-factor if you want to revisit those numbers
python hlteff/generate_hlt_card.py

# 3. (optional) visualize: offline vs generated-HLT vs raw data curves,
#    one figure per module, one panel per |eta| bin, saved to hlteff/plots/
python hlteff/plot_curves.py
```

`derive_curves.py`'s `--input-dir`/`--n-files`/`--max-jets`/`--dr-max` and
`generate_hlt_card.py`'s `--min-count`/`--min-pairs`/`--max-sigma` are all
worth revisiting if you want tighter statistics, a different matching
window, or different trust thresholds - nothing about the pipeline is
QCD-specific except the default `--input-dir`.

See `calorimeters/README.md` for that subfolder's own usage (the
measurement/closure-check/granularity-scan tools that informed the ECal/HCal
plan-B numbers above - not needed for routine card regeneration).

## Notable findings

Worth flagging since they weren't obvious going in, and shaped what the
generated card looks like:

- **ECal/HCal: the data-driven approach doesn't work, hence the hand-set
  "plan B" (see Scope and Method step 3).** In short: a closure check found
  resolution-only retuning workable-but-imprecise for photons and broken
  for neutral hadrons (the matched-pair measurement itself blows up at
  higher energy - most likely lost-charged-track calorimeter energy
  reappearing online as extra, unmatchable neutral hadron candidates,
  not a resolution effect); a follow-up tower-granularity scan confirmed
  no coarsening factor reproduces the real pattern either (real scouting
  has *more* neutral hadron candidates than offline through most of the
  spectrum - merging can only ever produce fewer). Full investigation,
  plots, and reasoning in `calorimeters/README.md` - this is what
  motivated the hand-set numbers instead of a measurement.
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
- **Neutral particles (ECal/HCal)**: no genuine efficiency/resolution
  retuning - hand-set placeholder values instead (see "Scope",
  `calorimeters/README.md`). No equivalent of the tracking Efficiency
  modules exists for neutrals at all, so this isn't fixable the same way
  even in principle without a fundamentally different measurement.
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
- ECal/HCal: see `calorimeters/README.md` "Next steps" for what a
  fundamentally different (non-particle-matching) measurement could look
  like, if the hand-set plan-B numbers turn out not to be good enough.
- `TrackPileUpSubtractor.ZVertexResolution` and `RunPUPPIBase`: check
  whether this ntuple carries anything usable for the former; the latter
  would need a real design decision (external CMS scouting-PUPPI settings,
  or a multi-parameter fit against substructure observables), not just
  "add another matched-pair measurement."
- Consider deriving a jet-level or eta-extended (>2.5, currently hard cut
  to zero like the offline card) version if the generation pipeline ever
  needs forward jets.
