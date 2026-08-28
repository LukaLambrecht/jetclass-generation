#!/usr/bin/env python3

'''
Generate the HLT-like Delphes card from the offline-like Delphes card plus
the data-driven curves produced by derive_curves.py. Almost every number
written into the output card is either read out of the offline card
(treated as the given baseline) or read out of curves_qcd.json (treated as
the measurement) - see README.md for the method. The one exception is
ECal/HCal, which use a small number of explicit, documented hand-set
placeholder values instead ("plan B" - see apply_calo_plan_b() and
hlteff/calorimeters/README.md for why the data-driven approach doesn't work
there).

Two combination rules are used, chosen per module by what physically makes
sense for that quantity:

Multiplicative (a 0-1 efficiency, or a scale factor with no natural bound):
    HLT value(pt,eta bin) = offline value(pt,eta bin) * data ratio(pt,eta bin)
  Applies to: ChargedHadronTrackingEfficiency, ElectronTrackingEfficiency,
  MuonTrackingEfficiency (data ratio = fraction of offline candidates matched
  at scouting level), and JetEnergyScalePUPPIAK8 (data ratio = real
  scoutfj_pt/fj_pt).

Quadrature (a resolution/spread, where the data measures an *extra*,
independent smearing on top of whatever the offline formula already has):
    HLT value(pt,eta bin) = sqrt(offline value(pt,eta bin)^2 + extra(pt,eta bin)^2)
  Applies to: ChargedHadronMomentumSmearing, ElectronMomentumSmearing,
  MuonMomentumSmearing (extra = spread of (pt_scout-pt_offline)/pt_offline
  for matched pairs of that category), and TrackSmearing's D0/DZResolutionFormula
  (extra = spread of (dxy_scout-dxy_offline) / (dz_scout-dz_offline) for
  matched pairs, pooled across categories, in mm).

Every generated table is written as an explicit (eta bin x pt bin)
piecewise-constant table, in the same style already used elsewhere in these
cards (e.g. the hand-written TrackSmearing D0/DZ tables) - not as a symbolic
rescaling of the offline formula, so the resulting card is self-contained
and human-inspectable.

Bins with too little data to trust (below --min-count/--min-pairs, or - for
resolution - a suspiciously large sigma, see --max-sigma) fall back to the
nearest bin in the same eta row with usable data (pT bins are ordered, so
this is a simple forward/backward fill); if an entire eta row has no usable
data the fallback is "no measured degradation" (ratio 1, extra 0), and a
warning is printed - this can happen at very high pT where statistics run
out, or for electrons (see README "Notable findings").

ECal/HCal ResolutionFormula are set to (offline formula) *
--calo-resolution-degradation (default 1.5, i.e. a 50% degradation), and
both modules' tower grids are additionally coarsened by
--calo-granularity-factor (default 1.5, in both eta and phi) - hand-set
assumptions, not measurements; see apply_calo_plan_b() and
hlteff/calorimeters/README.md. Everything else
(PUPPI itself, TrackPileUpSubtractor.ZVertexResolution,
JetEnergyScalePUPPIAK15) is still genuinely untouched - see README.md
("Known limitations / not yet data-driven").

Usage:
  python generate_hlt_card.py [--curves PATH] [--offline-card PATH]
                               [--output PATH] [--output-nopu PATH]
'''

import os
import sys
import json
import argparse

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from delphes_formula import evaluate_formula, extract_formula_block, replace_formula_block, format_piecewise_table
from calo_grid import parse_regions, coarsen_regions, replace_grid

HLTEFF_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(HLTEFF_DIR)

DEFAULT_CURVES = os.path.join(HLTEFF_DIR, 'curves_qcd.json')
DEFAULT_OFFLINE_CARD = os.path.join(REPO_DIR, 'delphes_cards', 'delphes_card_CMS_JetClassII_onlyFatJet.tcl')
DEFAULT_OUTPUT = os.path.join(REPO_DIR, 'delphes_cards', 'delphes_card_CMS_JetClassII_onlyFatJet_HLT.tcl')
DEFAULT_OUTPUT_NOPU = os.path.join(REPO_DIR, 'delphes_cards', 'delphes_card_CMS_JetClassII_onlyFatJet_HLT_noPU.tcl')

# category -> Delphes module name for its tracking-efficiency / momentum-
# resolution modules (same category names key both, since the offline card
# names them consistently)
EFFICIENCY_MODULES = {
    'chargedHadron': 'ChargedHadronTrackingEfficiency',
    'electron': 'ElectronTrackingEfficiency',
    'muon': 'MuonTrackingEfficiency',
}
RESOLUTION_MODULES = {
    'chargedHadron': 'ChargedHadronMomentumSmearing',
    'electron': 'ElectronMomentumSmearing',
    'muon': 'MuonMomentumSmearing',
}


def fill_missing(values, valid):
    '''
    Forward/backward-fill `values` (a 1D list, one entry per pT bin, for a
    fixed eta bin) at positions where `valid` is False, using the nearest
    valid neighbor in pT. If no position in the row is valid at all, every
    entry falls back to its (unmodified) input value and False is returned;
    otherwise the filled list and True are returned.
    '''
    n = len(values)
    if not any(valid):
        return list(values), False

    out = list(values)
    filled_valid = list(valid)
    for i in range(n):
        if not filled_valid[i] and i > 0 and filled_valid[i - 1]:
            out[i] = out[i - 1]
            filled_valid[i] = True
    for i in range(n - 1, -1, -1):
        if not filled_valid[i] and i < n - 1 and filled_valid[i + 1]:
            out[i] = out[i + 1]
            filled_valid[i] = True
    return out, True


def build_ratio_table(ratio_grid, n_grid, offline_formula, eta_edges, pt_edges,
                       min_count, label, clip=None):
    '''
    Multiplicative combination: HLT = offline_formula(pt,eta) * data ratio,
    with per-row fallback (see fill_missing). `clip`, if given, is an
    (lo, hi) pair the final value is clamped into (used for efficiencies;
    left None for scale factors, which have no natural bound).
    '''
    ne, npt = len(eta_edges) - 1, len(pt_edges) - 1
    table = [[0.0] * npt for _ in range(ne)]
    for ie in range(ne):
        eta_c = 0.5 * (eta_edges[ie] + eta_edges[ie + 1])
        ratios, valid = [], []
        for ip in range(npt):
            n = n_grid[ie][ip]
            r = ratio_grid[ie][ip]
            ok = (r is not None) and (n >= min_count)
            ratios.append(r if ok else 1.0)
            valid.append(ok)
        filled, any_valid = fill_missing(ratios, valid)
        if not any_valid:
            print('WARNING: no usable {} data for eta bin [{},{}) - '
                  'falling back to the offline value unmodified there'.format(
                      label, eta_edges[ie], eta_edges[ie + 1]), file=sys.stderr)
        for ip in range(npt):
            pt_c = 0.5 * (pt_edges[ip] + pt_edges[ip + 1])
            offline_val = evaluate_formula(offline_formula, pt=pt_c, eta=eta_c)
            val = offline_val * filled[ip]
            if clip is not None:
                val = max(clip[0], min(clip[1], val))
            table[ie][ip] = val
    return table


def build_quadrature_table(sigma_grid, n_grid, offline_formula, eta_edges, pt_edges,
                            min_pairs, max_sigma, label):
    '''
    Quadrature combination: HLT = sqrt(offline_formula(pt,eta)^2 + extra^2),
    with per-row fallback (see fill_missing).
    '''
    ne, npt = len(eta_edges) - 1, len(pt_edges) - 1
    table = [[0.0] * npt for _ in range(ne)]
    for ie in range(ne):
        eta_c = 0.5 * (eta_edges[ie] + eta_edges[ie + 1])
        extras, valid = [], []
        for ip in range(npt):
            n = n_grid[ie][ip]
            sigma = sigma_grid[ie][ip]
            ok = (sigma is not None) and (n >= min_pairs) and (sigma <= max_sigma)
            extras.append(sigma if ok else 0.0)
            valid.append(ok)
        filled, any_valid = fill_missing(extras, valid)
        if not any_valid:
            print('WARNING: no usable {} data for eta bin [{},{}) - '
                  'falling back to the offline resolution unmodified there'.format(
                      label, eta_edges[ie], eta_edges[ie + 1]), file=sys.stderr)
        for ip in range(npt):
            pt_c = 0.5 * (pt_edges[ip] + pt_edges[ip + 1])
            offline_sigma = evaluate_formula(offline_formula, pt=pt_c, eta=eta_c)
            table[ie][ip] = float(np.hypot(offline_sigma, filled[ip]))
    return table


# ECal/HCal: unlike every other module above, this is NOT derived from
# curves_qcd.json. Two closure checks (see hlteff/calorimeters/README.md)
# found the matched-pair approach doesn't work for the calorimeters the way
# it does for tracking - ECal's is workably-close-but-imprecise, HCal's
# breaks down outright (a real energy-attribution effect, most likely
# offline-lost charged tracks' calo deposits reappearing online as "extra"
# neutral hadron candidates with no clean 1-to-1 offline counterpart, not a
# resolution or granularity effect - see hlteff/calorimeters/README.md
# "Findings"). A tower-granularity scan (also documented there) confirmed
# that coarsening HCal's grid does not reproduce the observed real-data
# multiplicity pattern either (it can only ever reduce candidate count, but
# real scouting has *more* candidates than offline through most of the
# spectrum) - so these are deliberate, hand-set placeholder assumptions
# ("plan B"), not a fit to data, applied identically to both modules for
# consistency even though the granularity scan itself only tested HCal.
# Revisit if a better-founded measurement becomes available.
CALO_MODULES = ['ECal', 'HCal']


def apply_calo_plan_b(text, resolution_factor, calo_granularity_factor):
    for module in CALO_MODULES:
        offline_formula = extract_formula_block(text, module, 'ResolutionFormula')
        new_formula = '({}) * {:.6g}'.format(offline_formula.strip(), resolution_factor)
        text = replace_formula_block(text, module, 'ResolutionFormula', new_formula)

    if calo_granularity_factor != 1:
        for module in CALO_MODULES:
            regions = parse_regions(text, module)
            coarsened = coarsen_regions(regions, calo_granularity_factor)
            text = replace_grid(text, module, coarsened)
    return text


def make_header(curves_path, curves, offline_card_path, calo_resolution_degradation, calo_granularity_factor):
    src = curves['source']
    return '''\
##############################################################################
# Approximate CMS Phase-2 HLT ("scouting")-like reconstruction - GENERATED,
# do not hand-edit. Produced by hlteff/generate_hlt_card.py from:
#   - the offline card as baseline: {offline_card}
#   - data-driven degradation curves: {curves_path}
#     (generated {generated_at} by hlteff/derive_curves.py, reading
#      {n_jets} QCD jets, deltaR match window {dr_max}, from:
#      {input_dir}
#      files: {files})
#
# Method (see hlteff/README.md for full details): two combination rules,
# chosen per module by what physically makes sense for that quantity.
#   Multiplicative (ChargedHadronTrackingEfficiency, ElectronTrackingEfficiency,
#   MuonTrackingEfficiency, JetEnergyScalePUPPIAK8): HLT(pt,eta) =
#   offline(pt,eta) * (a data-driven ratio measured in real paired
#   offline/scouting CMS data, binned in (pt,|eta|) for tracking, or jet
#   (pT,|eta|) for JES).
#   Quadrature (ChargedHadronMomentumSmearing, Electron/MuonMomentumSmearing,
#   TrackSmearing D0/DZResolutionFormula): HLT(pt,eta) = sqrt(offline(pt,eta)^2
#   + extra(pt,eta)^2), where extra is the additional smearing/spread
#   measured for matched offline-scouting pairs in that bin.
#   PUPPI, jet clustering, softdrop, TrackPileUpSubtractor.ZVertexResolution,
#   and JetEnergyScalePUPPIAK15 are UNCHANGED from the offline card - see
#   README.md for why.
#
#   ECal/HCal ResolutionFormula are hand-set to (offline formula) *
#   {calo_resolution_degradation:g} ("plan B": data-driven closure checks found the
#   matched-pair approach doesn't work for calorimeters the way it does for
#   tracking - see hlteff/calorimeters/README.md - so this is a documented
#   placeholder assumption, not a measurement). Both modules' tower grids
#   are additionally coarsened by a factor {calo_granularity_factor:g} in both eta and phi
#   (each tower {calo_granularity_factor:g}x wider in each dimension, {calo_granularity_factor_sq:g}x the area) - also a
#   hand-set assumption (a data-driven granularity scan found no coarsening
#   factor actually reproduces the measured effect, see
#   hlteff/calorimeters/README.md, but a modest coarsening is retained as a
#   physically-motivated guess given degraded upstream tracking efficiency
#   independently increases the neutral-hadron rate). Both ECal/HCal
#   thresholds (EnergyMin/EnergySignificanceMin) are left at their offline
#   values.
#
# To regenerate after new data or a change to the offline card:
#   python hlteff/derive_curves.py       # only if the input data changed
#   python hlteff/generate_hlt_card.py
##############################################################################
'''.format(
        offline_card=os.path.relpath(offline_card_path, REPO_DIR),
        curves_path=os.path.relpath(curves_path, REPO_DIR),
        generated_at=src.get('generated_at', 'unknown time'),
        n_jets=src['n_jets_processed'],
        dr_max=src['dr_max'],
        input_dir=src['input_dir'],
        files=', '.join(os.path.basename(f) for f in src['files']),
        calo_resolution_degradation=calo_resolution_degradation,
        calo_granularity_factor=calo_granularity_factor,
        calo_granularity_factor_sq=calo_granularity_factor ** 2,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--curves', default=DEFAULT_CURVES)
    parser.add_argument('--offline-card', default=DEFAULT_OFFLINE_CARD)
    parser.add_argument('--output', default=DEFAULT_OUTPUT)
    parser.add_argument('--output-nopu', default=DEFAULT_OUTPUT_NOPU)
    parser.add_argument('--min-count', type=int, default=200,
        help='minimum offline candidate (or jet) count in a bin to trust its ratio (default: 200)')
    parser.add_argument('--min-pairs', type=int, default=200,
        help='minimum matched-pair count in a bin to trust its resolution measurement (default: 200)')
    parser.add_argument('--max-sigma', type=float, default=1.0,
        help='reject a bin\'s pT-resolution measurement if the extra relative-pT sigma exceeds this'
             ' (guards against low-efficiency bins where matches are mostly combinatorial noise; default: 1.0)')
    parser.add_argument('--max-sigma-dxy', type=float, default=1.0,
        help='same as --max-sigma, in mm, for the D0 (dxy) impact-parameter measurement (default: 1.0)')
    parser.add_argument('--max-sigma-dz', type=float, default=2.0,
        help='same as --max-sigma, in mm, for the DZ (dz) impact-parameter measurement'
             ' (looser than dxy by default: dz genuinely has a wider physical spread; default: 2.0)')
    parser.add_argument('--calo-resolution-degradation', type=float, default=1.5,
        help='ECal/HCal ResolutionFormula HAND-SET multiplier ("plan B", not data-driven - see'
             ' hlteff/calorimeters/README.md): HLT sigma = offline sigma * this (default: 1.5, i.e. a 50%%'
             ' resolution degradation)')
    parser.add_argument('--calo-granularity-factor', type=float, default=1.5,
        help='ECal/HCal tower-grid coarsening factor, HAND-SET ("plan B", see hlteff/calorimeters/README.md -'
             ' a data-driven scan found no factor actually reproduces the measured effect): each tower'
             ' this many times wider in both eta and phi (need not be an integer; 1 = unchanged; default: 1.5)')
    args = parser.parse_args()

    with open(args.curves) as f:
        curves = json.load(f)
    eta_edges = curves['binning']['eta_edges']
    pt_edges = curves['binning']['pt_edges']
    jet_pt_edges = curves['binning']['jet_pt_edges']

    with open(args.offline_card) as f:
        offline_text = f.read()

    text = offline_text

    # --- tracking efficiency (multiplicative) ---
    for cat, module in EFFICIENCY_MODULES.items():
        data = curves['categories'][cat]
        offline_formula = extract_formula_block(offline_text, module, 'EfficiencyFormula')
        table = build_ratio_table(data['efficiency_ratio'], data['n_offline'], offline_formula,
                                   eta_edges, pt_edges, args.min_count, '{} efficiency'.format(cat), clip=(0.0, 1.0))
        new_formula = format_piecewise_table(eta_edges, pt_edges, table, var_prefix='  ')
        text = replace_formula_block(text, module, 'EfficiencyFormula', new_formula)

    # --- momentum resolution (quadrature) ---
    for cat, module in RESOLUTION_MODULES.items():
        data = curves['categories'][cat]
        offline_formula = extract_formula_block(offline_text, module, 'ResolutionFormula')
        table = build_quadrature_table(data['sigma_extra_pt'], data['n_matched_pairs'], offline_formula,
                                        eta_edges, pt_edges, args.min_pairs, args.max_sigma,
                                        '{} momentum-resolution'.format(cat))
        new_formula = format_piecewise_table(eta_edges, pt_edges, table, var_prefix='  ')
        text = replace_formula_block(text, module, 'ResolutionFormula', new_formula)

    # --- track impact parameter resolution (quadrature), D0 and DZ ---
    tip = curves['trackImpactParameter']
    for formula_name, sigma_key, max_sigma, label in (
        ('D0ResolutionFormula', 'sigma_extra_dxy', args.max_sigma_dxy, 'dxy impact-parameter'),
        ('DZResolutionFormula', 'sigma_extra_dz', args.max_sigma_dz, 'dz impact-parameter'),
    ):
        offline_formula = extract_formula_block(offline_text, 'TrackSmearing', formula_name)
        table = build_quadrature_table(tip[sigma_key], tip['n_pairs'], offline_formula,
                                        eta_edges, pt_edges, args.min_pairs, max_sigma, label)
        new_formula = format_piecewise_table(eta_edges, pt_edges, table, var_prefix='  ')
        text = replace_formula_block(text, 'TrackSmearing', formula_name, new_formula)

    # --- jet energy scale (multiplicative), AK8 only - see README for why not AK15 ---
    jes = curves['jetEnergyScale']
    offline_scale_formula = extract_formula_block(offline_text, 'JetEnergyScalePUPPIAK8', 'ScaleFormula')
    jes_table = build_ratio_table(jes['scout_over_offline_ratio'], jes['n_jets_scout_over_offline'],
                                   offline_scale_formula, eta_edges, jet_pt_edges, args.min_count,
                                   'jet energy scale', clip=None)
    new_jes_formula = format_piecewise_table(eta_edges, jet_pt_edges, jes_table, var_prefix='  ')
    text = replace_formula_block(text, 'JetEnergyScalePUPPIAK8', 'ScaleFormula', new_jes_formula)

    # --- ECal/HCal (hand-set "plan B", not data-driven - see function docstring) ---
    text = apply_calo_plan_b(text, args.calo_resolution_degradation, args.calo_granularity_factor)

    header = make_header(args.curves, curves, args.offline_card,
                          args.calo_resolution_degradation, args.calo_granularity_factor)
    text = header + '\n' + text

    with open(args.output, 'w') as f:
        f.write(text)
    print('Wrote', args.output)

    text_nopu = text.replace('set MeanPileUp 50', 'set MeanPileUp 0')
    if text_nopu == text:
        print('WARNING: "set MeanPileUp 50" not found in generated text - '
              'noPU variant may not differ from the PU variant', file=sys.stderr)
    with open(args.output_nopu, 'w') as f:
        f.write(text_nopu)
    print('Wrote', args.output_nopu)


if __name__ == '__main__':
    main()
