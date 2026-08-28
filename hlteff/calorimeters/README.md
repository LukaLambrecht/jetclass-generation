# hlteff/calorimeters

Investigation into whether `ECal`/`HCal` (in `delphes_cards/delphes_card_CMS_JetClassII_onlyFatJet.tcl`)
could be retuned for the HLT-like card the same data-driven way as the 9
tracking/jet-scale modules in `../` (see `../README.md`). Short answer:
**no** - this subfolder is why, and what got hand-set into
`generate_hlt_card.py` instead (`apply_calo_plan_b()`, see `../README.md`
"Scope"/"Method").

Kept separate from `../` on purpose: none of the tools here are needed for
routine card regeneration (`derive_curves.py` + `generate_hlt_card.py` in
the parent directory is the whole production pipeline); everything here is
the one-off investigation that concluded a data-driven approach doesn't
work and picked hand-set numbers instead.

## Why ECal/HCal are different from the tracking modules

Delphes has no `Efficiency` module for neutral particles. A neutral
candidate's "reconstructed or not" only exists implicitly, as whatever
fraction of its Gaussian-smeared energy clears the fixed `EnergyMin`/
`EnergySignificanceMin` zero-suppression thresholds inside
`SimpleCalorimeter`. Since those thresholds are a hardware noise-floor
property (same calorimeter reads the same hits online and offline) rather
than a reconstruction-quality one, the natural first idea was: degrade only
`ResolutionFormula`, leave the thresholds fixed. `check_calo_closure.py`
tests whether that's actually sufficient, rather than just assuming it.

## Tools

### `check_calo_closure.py`

For each (category, |eta|, energy) bin: combines the offline
`ResolutionFormula` with the extra energy-smearing measured for matched
photon/neutralHadron pairs (from `../curves_qcd.json`'s `neutralCalorimeter`
section - matched the same way as the tracking categories, via `npfcand_*`/
`scoutpfcand_*` `isGamma`/`isNeutralHad` flags, but binned by *energy*
rather than pT since that's `ResolutionFormula`'s own variable) in
quadrature, computes what fraction of a Gaussian centered at that energy
would clear `max(EnergyMin, EnergySignificanceMin * sigma)` (a normal-CDF
calculation - approximates, not bit-exact to, Delphes' own C++ accept
logic), and compares that *predicted* efficiency to the neutral efficiency
*directly measured* in the same real data. Purely diagnostic - does not
modify any card. Saves `plots/closure_calo_{photon,neutralHadron}.png`.

```bash
python calorimeters/check_calo_closure.py
```

### `scan_calo_granularity.py` (+ `calo_grid.py` in `../`)

Tests a specific hypothesis for *why* the closure check fails for HCal
(see Findings): that online clustering merges nearby showers that offline
resolves separately, i.e. HCal's tower grid is effectively coarser online.
This is a purely geometric effect - no per-particle matching or Delphes run
needed to test it: for a range of integer coarsening factors (each tower N
times wider in eta *and* phi independently, applied per grid region -
barrel/endcap/forward keep their own relative granularity), it bins real
offline neutralHadron candidates (`npfcand_isNeutralHad`) onto the
N-coarsened grid, sums the energy of candidates sharing a tower within the
same jet ("what would `SimpleCalorimeter` output as one candidate for that
tower"), and compares the resulting predicted multiplicity spectrum to the
*real* scouting spectrum (`scoutpfcand_isNeutralHad`). Reports a
goodness-of-fit ranking and saves `plots/scan_calo_granularity_HCal.png`.
Does not modify any card.

```bash
python calorimeters/scan_calo_granularity.py --max-jets 20000
```

Kept intentionally quick (small default jet count) - the question it
answers ("does *any* coarsening factor reproduce the real pattern") doesn't
need much statistics; a clear qualitative answer emerged already at 20k
jets (see Findings).

`calo_grid.py` (the parser/coarsener/Tcl-regenerator both this scan and
`generate_hlt_card.py`'s `apply_calo_plan_b()` use) lives in `../`, not
here - it graduated from a test-only tool to a production dependency once
HCal's grid coarsening was wired into the actual card generation.

## Findings

**ECal (photons): resolution-only is workable but imprecise.** Run at full
statistics (256k jets). The predicted (resolution-only) and measured
efficiency curves track the same qualitative turn-on shape
(`plots/closure_calo_photon.png`), but not precisely - the model is too
*pessimistic* at very low energy (predicts 10-30% where data shows 40-90%
in the barrel) and slightly too *optimistic* at high energy (predicts
~100% where data plateaus at 94-99% barrel; both lower and more scattered
in the endcap, 60-100%).

**HCal (neutral hadrons): resolution-only does not closure at all**
(`plots/closure_calo_neutralHadron.png`). Measured efficiency rises
smoothly and stays around 85-95% (barrel) across nearly the whole energy
range; the resolution-only prediction instead has a severe, unphysical
*dip* down to ~30% around 30-100 GeV before climbing back up. Root cause:
the raw matched-pair "extra smearing" measurement itself explodes from a
few GeV at ~10-20 GeV particle energy to 100-330 GeV(!) by a few hundred
GeV - bigger than the particle's own energy, which no symmetric Gaussian
resolution widening can represent as a sane "spread."

**Tried tightening the matching to test a mismatch hypothesis - it didn't
help.** `derive_curves.py`'s `match_jet()` can optionally rank candidate
pairs by a combined geometric+energy metric instead of pure deltaR (a soft
tie-break among candidates already within the deltaR window, not a second
hard cut - see its docstring), driven by `--dr-max-neutral`/
`--neutral-use-energy`/`--rel-e-tol` (off by default in the parent
pipeline). Tested at `--dr-max-neutral 0.015 --neutral-use-energy` (half
the default window, plus energy-aware tie-breaking) on 60k jets: the HCal
sigma blowup was **essentially unchanged** (same magnitude, same ~20-25 GeV
onset) - evidence *against* nearest-neighbor mismatching as the cause.
Photon (ECal) got measurably *worse*: the tighter window starts excluding
genuine matches whose shower centroid shifts a bit between offline/HLT
reconstruction, turning a smoothly rising measured efficiency curve into a
dip. **Conclusion: the parent pipeline's default (loose, geometry-only)
matching is the better of the two tested options for both calorimeters.**

**Granularity scan: coarsening the HCal grid does not reproduce the real
pattern either, and reveals why.** `scan_calo_granularity_HCal.png` shows
the real scouting spectrum sitting *above* the real offline spectrum
through 0.7-30 GeV (roughly 1.5-2x more neutral hadron candidates online
than offline in that range), converging above ~30 GeV. Since merging
candidates together can only ever *reduce* their count, no coarsening
factor can push a curve up to match a target that starts out higher - and
indeed the goodness-of-fit score is flat-to-slightly-improving for factors
1-6 (all within noise of each other) and only gets monotonically worse
beyond that (tested 1-20). **This refutes shower-merging as the primary
explanation.**

**Best-supported alternative**: more scouting neutral hadron candidates
than offline, specifically at low-to-mid energy, is exactly consistent
with a mechanism already identified for *charged* particles in the parent
`hlteff/` work: when online tracking fails to reconstruct a charged
hadron, its calorimeter deposit doesn't disappear - with no track left to
subtract via eflow logic, it gets picked up as an *extra* neutral hadron
candidate instead. These reclassified candidates have no genuine offline
counterpart (offline correctly attributed that energy to a charged hadron
and produced no neutral candidate there at all), so when the matching
algorithm is forced to pair them with *some* nearby offline neutral hadron
anyway, it produces spurious pairs with wildly mismatched energies - a much
more coherent explanation for the blowup than shower geometry, and one
that ties directly to the already-measured, already-real charged-tracking
efficiency loss (`../plots/efficiency_chargedHadron.png`) rather than
requiring a new, separate mechanism.

## Decision: hand-set "plan B" (not derived from the above)

Given the above, the user chose deliberate placeholder values over further
chasing a data-driven fit, applied identically to both calorimeters for
consistency and documented explicitly as assumptions rather than
measurements:

- **`ResolutionFormula` (ECal and HCal): offline formula x 1.5** (a 50%
  degradation) - `--calo-resolution-degradation` in `generate_hlt_card.py`
  (default 1.5).
- **HCal tower grid coarsened by a factor of 2** (each tower 2x wider in
  eta *and* phi, so 4x the area) - `--hcal-granularity-factor` (default 2).
  Chosen despite the granularity scan showing no factor actually
  reproduces the measured pattern, on the reasoning that resolution really
  should be somewhat worse online regardless, and that the already-real,
  already-measured degraded charged-tracking efficiency will independently
  push more reclassified candidates into the neutral-hadron count in the
  full pipeline - so a modest coarsening is a reasonable general-purpose
  guess even though it isn't a validated fit.
- **`EnergyMin`/`EnergySignificanceMin`: unchanged** in both modules (the
  zero-suppression-threshold-is-a-hardware-property reasoning from "Why..."
  above still holds; only the *closure* premise built on top of it - that
  resolution-only fully explains the effect - didn't pan out for HCal).

See `../generate_hlt_card.py`'s `apply_calo_plan_b()` for where these are
actually applied, and the generated card's own header comment for the same
explanation inline.

## Next steps (not done here)

- If the plan-B numbers turn out not to be good enough in practice: the
  reclassification hypothesis above is directly testable (e.g. check
  whether "extra" scouting neutral hadrons cluster near tracks that failed
  offline-to-scouting matching) and would point toward a measurement tied
  to the already-measured charged-tracking efficiency loss, rather than a
  calorimeter-specific one.
- A genuinely different measurement strategy - jet/cluster-level rather
  than particle-level, similar in spirit to how `JetEnergyScalePUPPIAK8`
  sidesteps particle-level matching entirely - might succeed where
  particle-matching didn't; not attempted here.
- ECal's residual imprecision (see Findings) could still be improved with
  further work even though it wasn't judged broken enough to block using
  it - not pursued since the user asked to treat both calorimeters the
  same way (plan B) rather than data-driven for one and not the other.
