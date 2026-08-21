#!/usr/bin/env python3

'''
Generate the HLT-like Delphes card from the offline-like Delphes card plus
the data-driven curves produced by derive_curves.py. No hand-picked numbers
live in this script: every number written into the output card is either
read out of the offline card (treated as the given baseline) or read out of
curves_qcd.json (treated as the measurement) - see README.md for the method.

For each of ChargedHadronTrackingEfficiency, ElectronTrackingEfficiency,
MuonTrackingEfficiency:
    HLT efficiency(pt,eta bin) = offline efficiency(pt,eta bin) * data ratio(pt,eta bin)
      where "data ratio" = (offline candidates matched at scouting level)
                            / (all offline candidates), in that bin.

For ChargedHadronMomentumSmearing:
    HLT resolution(pt,eta bin) = sqrt(offline resolution(pt,eta bin)^2
                                       + data-driven extra smearing(pt,eta bin)^2)
      i.e. the extra spread of (pt_scout - pt_offline)/pt_offline for matched
      pairs is added in quadrature on top of whatever resolution the offline
      formula already has in that bin.

Both are written out as an explicit (eta bin x pt bin) piecewise-constant
table, in the same style already used elsewhere in these cards (e.g. the
TrackSmearing D0/DZ tables) - not as a symbolic rescaling of the offline
formula, so the resulting card is self-contained and human-inspectable.

Bins with too little data to trust (below --min-count offline candidates,
or - for resolution - fewer than --min-pairs matched pairs, or a
suspiciously large sigma - see --max-sigma) fall back to the nearest bin
in the same eta row with usable data (pT bins are ordered, so this is a
simple forward/backward fill); if an entire eta row has no usable data the
fallback is "no measured degradation" (ratio 1, extra sigma 0), and a
warning is printed - this can happen at very high pT where statistics run
out.

TrackSmearing (D0/DZ impact-parameter resolution) and Electron/MuonMomentumSmearing
are NOT touched by this script - left exactly as inherited from the offline
card. See README.md ("Known limitations / not yet data-driven").

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

HLTEFF_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(HLTEFF_DIR)

DEFAULT_CURVES = os.path.join(HLTEFF_DIR, 'curves_qcd.json')
DEFAULT_OFFLINE_CARD = os.path.join(REPO_DIR, 'delphes_cards', 'delphes_card_CMS_JetClassII_onlyFatJet.tcl')
DEFAULT_OUTPUT = os.path.join(REPO_DIR, 'delphes_cards', 'delphes_card_CMS_JetClassII_onlyFatJet_HLT.tcl')
DEFAULT_OUTPUT_NOPU = os.path.join(REPO_DIR, 'delphes_cards', 'delphes_card_CMS_JetClassII_onlyFatJet_HLT_noPU.tcl')

# category -> Delphes module name for its tracking-efficiency Efficiency module
EFFICIENCY_MODULES = {
    'chargedHadron': 'ChargedHadronTrackingEfficiency',
    'electron': 'ElectronTrackingEfficiency',
    'muon': 'MuonTrackingEfficiency',
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


def build_efficiency_table(curves, cat, offline_formula, eta_edges, pt_edges, min_count):
    ne, npt = len(eta_edges) - 1, len(pt_edges) - 1
    data = curves['categories'][cat]
    table = [[0.0] * npt for _ in range(ne)]
    for ie in range(ne):
        eta_c = 0.5 * (eta_edges[ie] + eta_edges[ie + 1])
        ratios = []
        valid = []
        for ip in range(npt):
            n_off = data['n_offline'][ie][ip]
            r = data['efficiency_ratio'][ie][ip]
            ok = (r is not None) and (n_off >= min_count)
            ratios.append(r if ok else 1.0)
            valid.append(ok)
        filled, any_valid = fill_missing(ratios, valid)
        if not any_valid:
            print('WARNING: no usable {} efficiency data for eta bin [{},{}) - '
                  'falling back to the offline value unmodified there'.format(
                      cat, eta_edges[ie], eta_edges[ie + 1]), file=sys.stderr)
        for ip in range(npt):
            pt_c = 0.5 * (pt_edges[ip] + pt_edges[ip + 1])
            offline_val = evaluate_formula(offline_formula, pt_c, eta_c)
            table[ie][ip] = max(0.0, min(1.0, offline_val * filled[ip]))
    return table


def build_resolution_table(curves, offline_formula, eta_edges, pt_edges, min_pairs, max_sigma):
    ne, npt = len(eta_edges) - 1, len(pt_edges) - 1
    data = curves['categories']['chargedHadron']
    table = [[0.0] * npt for _ in range(ne)]
    for ie in range(ne):
        eta_c = 0.5 * (eta_edges[ie] + eta_edges[ie + 1])
        extras = []
        valid = []
        for ip in range(npt):
            n_pairs = data['n_matched_pairs'][ie][ip]
            sigma = data['sigma_extra_pt'][ie][ip]
            ok = (sigma is not None) and (n_pairs >= min_pairs) and (sigma <= max_sigma)
            extras.append(sigma if ok else 0.0)
            valid.append(ok)
        filled, any_valid = fill_missing(extras, valid)
        if not any_valid:
            print('WARNING: no usable momentum-resolution data for eta bin [{},{}) - '
                  'falling back to the offline resolution unmodified there'.format(
                      eta_edges[ie], eta_edges[ie + 1]), file=sys.stderr)
        for ip in range(npt):
            pt_c = 0.5 * (pt_edges[ip] + pt_edges[ip + 1])
            offline_sigma = evaluate_formula(offline_formula, pt_c, eta_c)
            table[ie][ip] = float(np.hypot(offline_sigma, filled[ip]))
    return table


def make_header(curves_path, curves, offline_card_path):
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
# Method (see hlteff/README.md for full details):
#   For each of ChargedHadronTrackingEfficiency, ElectronTrackingEfficiency,
#   MuonTrackingEfficiency: HLT efficiency(pt,eta) = offline efficiency(pt,eta)
#   * (fraction of offline CMS "regular PF + lost track" candidates that have
#   a geometrically-matched scouting candidate of the same particle type, in
#   real paired offline/scouting CMS data), binned in (pt, |eta|).
#   For ChargedHadronMomentumSmearing: HLT resolution(pt,eta) = offline
#   resolution(pt,eta) combined in quadrature with the extra (pt_scouting -
#   pt_offline)/pt_offline spread measured for matched pairs in that bin.
#   Everything else (calorimeter response, PUPPI, jet clustering, softdrop,
#   TrackSmearing D0/DZ impact-parameter resolution, Electron/MuonMomentumSmearing)
#   is UNCHANGED from the offline card - see README.md for why, and for
#   what's a documented candidate for future extension.
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
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--curves', default=DEFAULT_CURVES)
    parser.add_argument('--offline-card', default=DEFAULT_OFFLINE_CARD)
    parser.add_argument('--output', default=DEFAULT_OUTPUT)
    parser.add_argument('--output-nopu', default=DEFAULT_OUTPUT_NOPU)
    parser.add_argument('--min-count', type=int, default=200,
        help='minimum offline candidate count in a bin to trust its efficiency ratio (default: 200)')
    parser.add_argument('--min-pairs', type=int, default=200,
        help='minimum matched-pair count in a bin to trust its resolution measurement (default: 200)')
    parser.add_argument('--max-sigma', type=float, default=1.0,
        help='reject a bin\'s resolution measurement if the extra relative-pT sigma exceeds this'
             ' (guards against low-efficiency bins where matches are mostly combinatorial noise; default: 1.0)')
    args = parser.parse_args()

    with open(args.curves) as f:
        curves = json.load(f)
    eta_edges = curves['binning']['eta_edges']
    pt_edges = curves['binning']['pt_edges']

    with open(args.offline_card) as f:
        offline_text = f.read()

    text = offline_text
    for cat, module in EFFICIENCY_MODULES.items():
        offline_formula = extract_formula_block(offline_text, module, 'EfficiencyFormula')
        table = build_efficiency_table(curves, cat, offline_formula, eta_edges, pt_edges, args.min_count)
        new_formula = format_piecewise_table(eta_edges, pt_edges, table, var_prefix='  ')
        text = replace_formula_block(text, module, 'EfficiencyFormula', new_formula)

    offline_res_formula = extract_formula_block(offline_text, 'ChargedHadronMomentumSmearing', 'ResolutionFormula')
    res_table = build_resolution_table(curves, offline_res_formula, eta_edges, pt_edges, args.min_pairs, args.max_sigma)
    new_res_formula = format_piecewise_table(eta_edges, pt_edges, res_table, var_prefix='  ')
    text = replace_formula_block(text, 'ChargedHadronMomentumSmearing', 'ResolutionFormula', new_res_formula)

    header = make_header(args.curves, curves, args.offline_card)
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
