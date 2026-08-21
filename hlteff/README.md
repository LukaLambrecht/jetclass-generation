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

Only the modules that plausibly need HLT-specific retuning are touched:
`ChargedHadronTrackingEfficiency`, `ElectronTrackingEfficiency`,
`MuonTrackingEfficiency` (all `Efficiency` modules), and
`ChargedHadronMomentumSmearing` (pT resolution). Everything else in the
generated card - calorimeter response, PUPPI, jet clustering, softdrop,
`TrackSmearing` (D0/DZ impact-parameter resolution), and
`Electron`/`MuonMomentumSmearing` - is copied unchanged from the offline
card. See "Known limitations" for why those are out of scope *for now*
rather than because they don't matter.

Neutral particles (photons, neutral hadrons) aren't retuned either: Delphes
doesn't have an `Efficiency` module for them in this card (`ECal`/`HCal`
always produce a tower deposit above their energy thresholds), so there's
no equivalent knob to turn - only their calorimeter resolution formulas
would be a lever, which is out of scope here for the same reason as
`TrackSmearing` below.

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

Output: `curves_qcd.json` (binning, per-category grids of the above, plus
provenance metadata: which files, how many jets, what deltaR window).

### 2. `generate_hlt_card.py` - translate into a Delphes card

Takes `curves_qcd.json` and the offline Delphes card
(`delphes_cards/delphes_card_CMS_JetClassII_onlyFatJet.tcl`, treated as a
given, not duplicated) and, for each of the four modules in scope:
- reads the *actual* offline formula out of the offline `.tcl` file (via
  brace-matching text extraction, not a hardcoded copy - see
  `delphes_formula.py`) and evaluates it at each bin's center using a small
  restricted expression evaluator (translates Delphes' pT/eta formula
  syntax, e.g. `^` for power vs. Tcl's native bitwise-XOR meaning, so this
  is *not* just handing the string to a real Tcl interpreter),
- combines it with the matching data-driven curve from `curves_qcd.json`
  (efficiency: multiply; resolution: add in quadrature),
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
```

`derive_curves.py`'s `--input-dir`/`--n-files`/`--max-jets`/`--dr-max` and
`generate_hlt_card.py`'s `--min-count`/`--min-pairs`/`--max-sigma` are all
worth revisiting if you want tighter statistics, a different matching
window, or different trust thresholds - nothing about the pipeline is
QCD-specific except the default `--input-dir`.

## Notable findings

Worth flagging since they weren't obvious going in, and shaped what the
generated card looks like:

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

## Known limitations / not yet data-driven

- **TrackSmearing (D0/DZ impact-parameter resolution)**: not retuned here.
  The offline ntuples do carry `dxy`/`dz` (and their uncertainties) for
  both offline and scouting candidates, so the same matched-pair approach
  used for pT resolution could extend to these - it just wasn't done yet,
  partly because of unit-consistency risk between the ntuple's stored units
  and the Delphes card's (needs to be checked explicitly, not assumed)
  before trusting a quadrature combination the way this script does for pT.
- **Electron/MuonMomentumSmearing**: left inherited from the offline card.
  Electrons and muons are rare in QCD/hadronic jets, so there's limited
  statistical leverage in this sample either way; revisit if a
  lepton-enriched use case needs it.
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
- Extend to D0/DZ (see above) once units are confirmed.
- Consider deriving a jet-level or eta-extended (>2.5, currently hard cut
  to zero like the offline card) version if the generation pipeline ever
  needs forward jets.
