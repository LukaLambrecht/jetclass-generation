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
--calo-resolution-degradation (default 1.1, i.e. a 10% degradation; 1.0
keeps the offline resolution), and both modules' tower grids can additionally
be coarsened by --calo-granularity-factor (default 1.0, i.e. offline
granularity, no coarsening) - hand-set assumptions, not measurements; see
apply_calo_plan_b() and hlteff/calorimeters/README.md.

Charged/Electron/Muon TrackingEfficiency are additionally hard-set to 0 in
every pT bin entirely below --charged-eff-pt-floor (default 0.5 GeV), all
|eta| - a hand override of the data-driven curves, which return a small
nonzero efficiency there that is not trusted.

PUPPI is copied through from the offline card untouched EXCEPT for
RunPUPPIBase's own UseCharged flags, settable via --puppi-use-charged
(default "true" = the offline card's own value, i.e. genuinely untouched).
Setting it "false" scores PUPPI's alpha against ALL particles instead of
leading-vertex CHARGED TRACKS only - a reference population the HLT tracking
retuning above does not deplete - which largely removes the reconstructed
neutral-hadron/photon-per-jet deficit this card otherwise has relative to
real scouting data; see apply_puppi_use_charged() for the full reasoning.

Everything else (the rest of PUPPI, TrackPileUpSubtractor.ZVertexResolution,
JetEnergyScalePUPPIAK15) is still genuinely untouched - see README.md
("Known limitations / not yet data-driven").

FastJetFinderPUPPIAK8/AK15's own JetPTMin is lowered to --hlt-jet-pt-min
(default 1.0 GeV, i.e. effectively "no cut" - see its own --help) instead of
being copied unchanged from the offline card (200/120 GeV). This is not a
data-driven measurement either, but a structural requirement for the
offline<->HLT jet-matching workflow (delphes_analyzers/makeNtuplesPaired.C):
that ntuplizer applies pT/eta selection to the OFFLINE jet only and keeps
whatever HLT jet matches it regardless of the HLT jet's own pT - including
one that fell below any nominal HLT threshold. If this card's own
FastJetFinder silently never constructs/writes a jet that degraded below
200/120 GeV in the first place, that distinction (HLT jet exists but is
soft vs. HLT jet is genuinely gone) is lost before the ntuplizer ever sees
it. JetEnergyScalePUPPIAK8's ScaleFormula is generated to cover this newly-
reachable low-pT region sensibly (extending the lowest measured bin's value
downward - see format_piecewise_table()'s own docstring) rather than the
phantom-zero it would otherwise evaluate to below JET_PT_EDGES[0] (200 GeV,
itself just this measurement's own data baseline, not a physical floor).

Usage:
  python generate_hlt_card.py [--curves PATH] [--offline-card PATH]
                               [--output PATH] [--output-nopu PATH]
'''

import os
import re
import sys
import json
import argparse

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from delphes_formula import (evaluate_formula, extract_formula_block, replace_formula_block, format_piecewise_table,
                             format_piecewise_table_3d, replace_scalar)
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


# lower edges (GeV) of the coarse track-pT groups whose |d0| SHAPE is used as
# the fallback for (eta, pt, d0) bins with too few offline tracks (see
# build_ip_ratio_table); fine pT bins below the first edge join the first group
IP_PT_GROUP_EDGES = [0.5, 1.2, 3.0, 10.0, 40.0]


def build_ip_ratio_table(n_off, n_match, offline_formula, eta_edges, pt_edges, d0_edges, min_count, label,
                         fallback_2d=None, fallback_shapes=None):
    '''
    Multiplicative combination with a third, |d0| axis (see derive_ip_curves.py):
    HLT(pt,eta,d0) = offline_formula(pt,eta) * ratio(eta,pt,d0), clipped to [0,1].
    ratio is n_matched/n_offline of the (eta,pt,d0) bin itself when that bin has at
    least min_count offline tracks; otherwise the product of
      - the bin's d0-INCLUSIVE ratio (same denominator; pT gaps filled from the
        nearest valid pT bin, as fill_missing() does elsewhere) - or, for an eta
        row with no usable d0-inclusive data at all, the (eta, pt) ratio row of
        fallback_2d = (ratio_grid, n_grid) from curves_qcd.json (what the
        default card uses), rather than a blind ratio of 1; and
      - the |d0| SHAPE of the bin's coarse pT group (IP_PT_GROUP_EDGES):
        ratio(eta,group,d0) / ratio(eta,group,inclusive), itself filled along d0
        from the nearest valid d0 bin where the group is also short of data - or,
        for a group with no usable d0 data at all, fallback_shapes[eta][group]
        (e.g. the charged-hadron shapes, for muons) if given.
    Using the offline formula as the base assumes the offline efficiency is
    uniform in d0 (the same assumption the measurement needs).
    Returns (table, shapes), shapes[eta][group] being the d0 shapes used.
    '''
    n_off = np.asarray(n_off, dtype=float)
    n_match = np.asarray(n_match, dtype=float)
    ne, npt, nd0 = n_off.shape
    group_of = []
    for ip in range(npt):
        g = 0
        for k, lo in enumerate(IP_PT_GROUP_EDGES):
            if pt_edges[ip] >= lo - 1e-9:
                g = k
        group_of.append(g)

    table = [[[0.0] * nd0 for _ in range(npt)] for _ in range(ne)]
    all_shapes = []
    n_direct = n_fallback = 0
    for ie in range(ne):
        eta_c = 0.5 * (eta_edges[ie] + eta_edges[ie + 1])
        incl_n, incl_m = n_off[ie].sum(axis=1), n_match[ie].sum(axis=1)
        incl_valid = [bool(n >= min_count) for n in incl_n]
        incl_vals = [float(m / n) if ok else 1.0 for m, n, ok in zip(incl_m, incl_n, incl_valid)]
        incl_filled, any_incl = fill_missing(incl_vals, incl_valid)
        if not any_incl:
            if fallback_2d is not None:
                r2, n2 = fallback_2d
                v2 = [bool(r2[ie][ip] is not None and n2[ie][ip] >= min_count) for ip in range(npt)]
                incl_filled, any2 = fill_missing([r2[ie][ip] if v2[ip] else 1.0 for ip in range(npt)], v2)
                print('WARNING: no usable {} d0-inclusive data for eta bin [{},{}) - using the (eta, pt) '
                      'ratio from --curves there{}'.format(label, eta_edges[ie], eta_edges[ie + 1],
                                                          '' if any2 else ' (itself empty: ratio 1)'), file=sys.stderr)
            else:
                print('WARNING: no usable {} data for eta bin [{},{}) - ratio 1 there'.format(
                    label, eta_edges[ie], eta_edges[ie + 1]), file=sys.stderr)

        shapes = {}
        for g in sorted(set(group_of)):
            sel = [ip for ip in range(npt) if group_of[ip] == g]
            gn, gm = n_off[ie, sel, :].sum(axis=0), n_match[ie, sel, :].sum(axis=0)
            g_incl = gm.sum() / gn.sum() if gn.sum() > 0 else 0.0
            valid = [bool(n >= min_count and g_incl > 0) for n in gn]
            vals = [float(m / n / g_incl) if ok else 1.0 for m, n, ok in zip(gm, gn, valid)]
            shape, any_shape = fill_missing(vals, valid)
            if not any_shape:
                if fallback_shapes is not None:
                    shape = list(fallback_shapes[ie][g])
                    print('WARNING: no usable {} d0 shape for eta bin [{},{}), pT group {} - using the '
                          'fallback (charged-hadron) shape there'.format(label, eta_edges[ie], eta_edges[ie + 1], g),
                          file=sys.stderr)
                else:
                    print('WARNING: no usable {} d0 shape for eta bin [{},{}), pT group {} - '
                          'no d0 dependence there'.format(label, eta_edges[ie], eta_edges[ie + 1], g), file=sys.stderr)
            shapes[g] = shape
        all_shapes.append(shapes)

        for ip in range(npt):
            pt_c = 0.5 * (pt_edges[ip] + pt_edges[ip + 1])
            offline_val = evaluate_formula(offline_formula, pt=pt_c, eta=eta_c)
            for i0 in range(nd0):
                if n_off[ie, ip, i0] >= min_count:
                    r = n_match[ie, ip, i0] / n_off[ie, ip, i0]
                    n_direct += 1
                else:
                    r = incl_filled[ip] * shapes[group_of[ip]][i0]
                    n_fallback += 1
                table[ie][ip][i0] = max(0.0, min(1.0, offline_val * r))
    print('{}: {} (eta,pt,d0) bins measured directly, {} from the fallback (min {} tracks)'.format(
        label, n_direct, n_fallback, min_count))
    return table, all_shapes


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


PUPPI_MODULE = 'RunPUPPIBase'


def apply_puppi_use_charged(text, use_charged):
    '''
    Set RunPUPPIBase's own UseCharged flags (one per eta bin) on the generated HLT card.
    PUPPI is otherwise copied through from the offline card untouched (see the module
    docstring) - this is the ONE PUPPI setting the HLT card is allowed to differ in.

    What it does, and why it is an HLT knob at all: with UseCharged true (the offline
    card's own value) each candidate's PUPPI "alpha" is computed against LEADING-VERTEX
    CHARGED TRACKS only, and the median/RMS calibration is built from pileup-charged
    candidates only. That reference population is exactly what our HLT tracking
    retuning depletes (~40% of charged tracks are lost), so jet-core NEUTRALS look
    artificially isolated, score pileup-like, and get weighted to ~0 - measured as a
    large deficit of reconstructed neutral hadrons/photons per jet relative to offline,
    where real scouting data shows a large EXCESS (see validation/compare-hlt-to-offline/
    plot_nparticles.py). With UseCharged false the alpha reference becomes ALL particles
    instead, a population tracking losses do not deplete (neutrals are unaffected).

    Only the flags inside the RunPUPPIBase module block are touched (the offline card is
    the input and is never written), and the number of flags is preserved, since
    RunPUPPI::Init() requires every per-eta-bin list to be the same length.
    '''
    module_pat = re.compile(r'^module\s+RunPUPPI\s+' + re.escape(PUPPI_MODULE) + r'\s*\{', re.MULTILINE)
    m = module_pat.search(text)
    if not m:
        raise ValueError('module {} not found in the card'.format(PUPPI_MODULE))
    depth, end = 0, None
    for i in range(m.end() - 1, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        raise ValueError('module {}: unterminated block'.format(PUPPI_MODULE))

    block = text[m.start():end]
    line_pat = re.compile(r'^(\s*add\s+UseCharged\s+)(.*)$', re.MULTILINE)
    matches = line_pat.findall(block)
    if len(matches) != 1:
        raise ValueError('module {}: expected exactly one "add UseCharged" line, found {}'.format(
            PUPPI_MODULE, len(matches)))
    prefix, values = matches[0]
    wanted = 'true' if use_charged else 'false'
    existing = values.split()
    # no-op (byte-exact, preserving the offline card's own spacing) when the card
    # already says what was asked for - so the default leaves the card untouched
    if all(v == wanted for v in existing):
        return text
    new_line = prefix + ' '.join([wanted] * len(existing))
    new_block = line_pat.sub(lambda _: new_line, block, count=1)
    return text[:m.start()] + new_block + text[end:]


HLT_JET_INPUT_MERGER = 'HLTEFlowMerger'


def _module_span(text, module_type, module_name):
    '''(start, end) of a "module <type> <name> { ... }" block, end = index of its closing brace.'''
    m = re.search(r'^module\s+' + re.escape(module_type) + r'\s+' + re.escape(module_name) + r'\s*\{',
                  text, re.MULTILINE)
    if not m:
        raise ValueError('module {} {} not found in the card'.format(module_type, module_name))
    depth = 0
    for i in range(m.end() - 1, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return m.start(), i
    raise ValueError('module {} {}: unterminated block'.format(module_type, module_name))


def _replace_in_module(text, module_type, module_name, old, new):
    start, end = _module_span(text, module_type, module_name)
    block = text[start:end]
    if block.count(old) != 1:
        raise ValueError('module {}: expected exactly one "{}", found {}'.format(module_name, old, block.count(old)))
    return text[:start] + block.replace(old, new) + text[end:]


HLT_JET_INPUT_PT_FILTER = 'HLTEFlowPtFilter'


def apply_no_puppi(text, z_window_mm=None, pf_pt_min=None):
    '''
    Build the HLT jets WITHOUT PUPPI (and without CHS): real scouting AK8 jets are
    plain anti-kT over all scouting particles (see delphes_cards/KNOWN_ISSUES.md).
    Adds a Merger (HLT_JET_INPUT_MERGER) of the energy-flow tracks + ECal photons +
    HCal neutral hadrons, and points FastJetFinderPUPPIAK8/AK15 and the
    ParticleFlowCandidate TreeWriter branch at it instead of RunPUPPI/PuppiParticles.
    (The module/branch names keep their "PUPPI" labels, so the ntuplizer and
    run.sh work unchanged; PUPPI itself still runs, but nothing uses its output.)

    z_window_mm None: the tracks are ALL energy-flow tracks (HCal/eflowTracks), i.e.
    every pile-up track the tracking-efficiency modules let through.
    z_window_mm given: emulates HLT tracking's limited z acceptance around the
    leading vertex, which a Delphes formula can't express (its dz is absolute): the
    tracks are TrackPileUpSubtractor/eflowTracks with ZVertexResolution set to that
    window, i.e. pile-up tracks farther than z_window_mm from the primary vertex are
    dropped (by truth) and nearer ones kept - not CHS in the sense of an
    algorithm run on reconstructed tracks, but a stand-in for tracks HLT never
    reconstructs.

    pf_pt_min given: additionally drop every candidate (charged or neutral) with
    reconstructed pT below it before jet clustering / writing, as the scouting
    producer does (HLTScoutingPFProducer stores only candidates with pT > 0.6 GeV;
    all ScoutingAK8 scouting candidates have pT >= 0.600). Implemented as a
    PdgCodeFilter (HLT_JET_INPUT_PT_FILTER) with only a PTMin (no PDG codes listed,
    so nothing else is filtered).
    '''
    tracks = 'TrackPileUpSubtractor/eflowTracks' if z_window_mm is not None else 'HCal/eflowTracks'
    merger = ('module Merger {name} {{\n'
              '  add InputArray {tracks}\n'
              '  add InputArray ECal/eflowPhotons\n'
              '  add InputArray HCal/eflowNeutralHadrons\n'
              '  set OutputArray eflow\n'
              '}}\n\n').format(name=HLT_JET_INPUT_MERGER, tracks=tracks)
    new_modules = [HLT_JET_INPUT_MERGER]
    new_input = HLT_JET_INPUT_MERGER + '/eflow'
    if pf_pt_min is not None:
        merger += ('module PdgCodeFilter {name} {{\n'
                   '  set InputArray {inp}\n'
                   '  set OutputArray eflow\n'
                   '  set PTMin {pt:g}\n'
                   '}}\n\n').format(name=HLT_JET_INPUT_PT_FILTER, inp=new_input, pt=pf_pt_min)
        new_modules.append(HLT_JET_INPUT_PT_FILTER)
        new_input = HLT_JET_INPUT_PT_FILTER + '/eflow'
    start, _ = _module_span(text, 'Merger', 'EFlowMerger')
    text = text[:start] + merger + text[start:]

    # run them right after EFlowMerger
    text, n = re.subn(r'(set ExecutionPath \{.*?\n)(\s*)EFlowMerger\n',
                      lambda m: m.group(1) + m.group(2) + 'EFlowMerger\n' +
                      ''.join(m.group(2) + mod + '\n' for mod in new_modules),
                      text, count=1, flags=re.S)
    if n != 1:
        raise ValueError('EFlowMerger not found in the ExecutionPath')

    for module in ('FastJetFinderPUPPIAK8', 'FastJetFinderPUPPIAK15'):
        text = _replace_in_module(text, 'FastJetFinder', module,
                                  'set InputArray RunPUPPI/PuppiParticles', 'set InputArray ' + new_input)
    text = _replace_in_module(text, 'TreeWriter', 'TreeWriter',
                              'add Branch RunPUPPI/PuppiParticles ParticleFlowCandidate',
                              'add Branch {} ParticleFlowCandidate'.format(new_input))
    if z_window_mm is not None:
        # value in m (TrackPileUpSubtractor compares formula * 1e3 against mm)
        text = _replace_in_module(text, 'TrackPileUpSubtractor', 'TrackPileUpSubtractor',
                                  'set ZVertexResolution {0.0001}',
                                  'set ZVertexResolution {{{:g}}}'.format(z_window_mm / 1000.0))
    return text


def _wrap_comment(text, width=76, indent='#   '):
    '''Word-wrap `text` for a Tcl "#"-comment block. Returns the lines joined
    by "\\n<indent>", with NO leading indent and no trailing newline - the
    header template supplies the first line's own "#   ".'''
    words, lines, cur = text.split(), [], ''
    for w in words:
        cand = (cur + ' ' + w).strip()
        if cur and len(indent) + len(cand) > width:
            lines.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return ('\n' + indent).join(lines)


def make_header(curves_path, curves, offline_card_path, calo_resolution_degradation, calo_granularity_factor,
                 hlt_jet_pt_min, charged_eff_pt_floor, puppi_use_charged,
                 ip_curves_path=None, ip_curves=None, ip_categories=(), no_puppi=False, z_window_mm=None,
                 pf_pt_min=None, jes_correction_path=None, jes_correction=None):
    src = curves['source']

    # extra paragraphs for the opt-in options only (empty by default, so the
    # default card stays byte-identical)
    extra_note = ''
    if ip_curves is not None:
        isrc = ip_curves['source']
        extra_note += '#   ' + _wrap_comment(
            'IMPACT-PARAMETER-DEPENDENT tracking efficiency for {cats}: the EfficiencyFormula is '
            'a (|eta|, pT, |d0|) table, offline(pt,eta) * ratio(eta,pt,d0), with the ratio from '
            '{path} (hlteff/derive_ip_curves.py, generated {gen}, {nj} QCD jets; denominator '
            'without lost and pile-up-like tracks), assuming the offline efficiency is uniform in '
            'd0; see derive_ip_curves.py and delphes_cards/KNOWN_ISSUES.md.'.format(
                cats='/'.join(ip_categories), path=os.path.relpath(ip_curves_path, REPO_DIR),
                gen=isrc.get('generated_at', 'unknown time'), nj=isrc['n_jets_processed'])) + '\n#\n'
    if no_puppi:
        if z_window_mm is None:
            tracks = ('ALL energy-flow tracks (HCal/eflowTracks, incl. every pile-up track that passes the '
                      'tracking efficiency)')
        else:
            tracks = ('TrackPileUpSubtractor/eflowTracks with ZVertexResolution set to {:g} mm, i.e. pile-up '
                      'tracks farther than that from the primary vertex are dropped by truth - a stand-in for '
                      'HLT tracking\'s limited z acceptance, which a Delphes formula cannot express'.format(z_window_mm))
        extra_note += '#   ' + _wrap_comment(
            'NO PUPPI and NO CHS for the HLT jets (as real scouting AK8 jets): FastJetFinderPUPPIAK8/AK15 and '
            'the ParticleFlowCandidate branch use {m}/eflow = {t}, plus ECal photons and HCal neutral hadrons. '
            'Module/branch names keep "PUPPI" for compatibility. JetEnergyScalePUPPIAK8 was NOT re-derived '
            'for this.{pt}'.format(m=HLT_JET_INPUT_MERGER, t=tracks,
                                   pt='' if pf_pt_min is None else ' All HLT candidates with reconstructed pT below '
                                   '{:g} GeV are dropped first ({}), as in the scouting producer.'.format(
                                       pf_pt_min, HLT_JET_INPUT_PT_FILTER))) + '\n#\n'

    if jes_correction is not None:
        extra_note += '#   ' + _wrap_comment(
            'JetEnergyScalePUPPIAK8 is additionally multiplied by per-HLT-jet-pT factors ({lo:.3f}-{hi:.3f}) from '
            '{path} (hlteff/derive_hlt_jes_correction.py, generated {gen}, {n} matched QCD jets), which bring '
            'our HLT/offline jet-pT ratio onto FullSim\'s for this card\'s settings.'.format(
                lo=min(jes_correction['factors']), hi=max(jes_correction['factors']),
                path=os.path.relpath(jes_correction_path, REPO_DIR), gen=jes_correction['generated_at'],
                n=jes_correction['n_matched_jets'])) + '\n#\n'

    if puppi_use_charged:
        # kept verbatim (not re-wrapped) so that generating with the default settings
        # reproduces the pre-existing card byte-for-byte
        puppi_note = ('#   PUPPI, jet clustering, softdrop, TrackPileUpSubtractor.ZVertexResolution,\n'
                      '#   and JetEnergyScalePUPPIAK15 are UNCHANGED from the offline card - see\n'
                      '#   README.md for why.')
    else:
        puppi_note = '#   ' + _wrap_comment(
            'RunPUPPIBase.UseCharged is set to FALSE (the offline card\'s own value is true) '
            '- see --puppi-use-charged. This makes PUPPI score each candidate against ALL '
            'particles rather than against leading-vertex CHARGED TRACKS only, because that '
            'charged reference population is exactly what the HLT tracking retuning above '
            'depletes, which otherwise drives reconstructed neutral hadrons/photons per jet '
            'far BELOW offline when real scouting data shows them well above it. Jet '
            'clustering, softdrop, TrackPileUpSubtractor.ZVertexResolution and '
            'JetEnergyScalePUPPIAK15 remain UNCHANGED from the offline card - see README.md. '
            'NOTE: JetEnergyScalePUPPIAK8 above was derived against the UseCharged=true '
            'behaviour and has NOT been re-derived for this setting.')
    puppi_note += '\n'

    if charged_eff_pt_floor > 0:
        charged_eff_note = '#   ' + _wrap_comment(
            'Charged/Electron/Muon TrackingEfficiency are additionally HARD-SET to 0 in every '
            'pT bin entirely below {:g} GeV, all |eta| (--charged-eff-pt-floor) - a hand override, '
            'not data-driven: the measured curves return a small nonzero efficiency there that '
            'is not trusted.'.format(charged_eff_pt_floor)) + '\n#\n'
    else:
        charged_eff_note = ''

    calo_sentences = []
    if calo_resolution_degradation != 1:
        calo_sentences.append(
            'ECal/HCal ResolutionFormula are hand-set to (offline formula) * {:g} ("plan B": '
            'data-driven closure checks found the matched-pair approach does not work for '
            'calorimeters the way it does for tracking - see hlteff/calorimeters/README.md - '
            'so this is a documented placeholder assumption, not a measurement).'.format(
                calo_resolution_degradation))
    else:
        calo_sentences.append('ECal/HCal ResolutionFormula are left UNCHANGED at their offline values.')
    if calo_granularity_factor != 1:
        calo_sentences.append(
            'Both modules\' tower grids are additionally coarsened by a factor {g:g} in both '
            'eta and phi (each tower {g:g}x wider in each dimension, {g2:g}x the area) - also a '
            'hand-set assumption (a data-driven granularity scan found no coarsening factor '
            'actually reproduces the measured effect, see hlteff/calorimeters/README.md).'.format(
                g=calo_granularity_factor, g2=calo_granularity_factor ** 2))
    else:
        calo_sentences.append('Both modules\' tower grids are left at their offline granularity.')
    calo_sentences.append(
        'Both ECal/HCal thresholds (EnergyMin/EnergySignificanceMin) are left at their offline values.')
    calo_paragraph = _wrap_comment(' '.join(calo_sentences))

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
{puppi_note}#
{extra_note}{charged_eff_note}#   {calo_paragraph}
#
#   FastJetFinderPUPPIAK8/AK15's own JetPTMin is HAND-SET to {hlt_jet_pt_min:g} GeV
#   (not copied from the offline card's 200/120 GeV, unlike every other
#   untouched module) - a structural requirement, not a measurement: the
#   offline<->HLT jet-matching ntuplizer (delphes_analyzers/makeNtuplesPaired.C)
#   needs Delphes to actually construct/write a jet that degraded below the
#   offline analysis threshold, rather than silently dropping it here first -
#   see generate_hlt_card.py's own module docstring. JetEnergyScalePUPPIAK8's
#   ScaleFormula covers this newly-reachable low-pT region by extending the
#   lowest measured bin's value downward (see format_piecewise_table() in
#   delphes_formula.py), not a phantom zero.
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
        charged_eff_note=charged_eff_note,
        extra_note=extra_note,
        puppi_note=puppi_note,
        calo_paragraph=calo_paragraph,
        hlt_jet_pt_min=hlt_jet_pt_min,
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
    parser.add_argument('--calo-resolution-degradation', type=float, default=1.1,
        help='ECal/HCal ResolutionFormula HAND-SET multiplier ("plan B", not data-driven - see'
             ' hlteff/calorimeters/README.md): HLT sigma = offline sigma * this (default: 1.1, i.e. a 10%%'
             ' resolution degradation; 1.0 = keep the offline resolution unchanged)')
    parser.add_argument('--calo-granularity-factor', type=float, default=1.0,
        help='ECal/HCal tower-grid coarsening factor, HAND-SET ("plan B", see hlteff/calorimeters/README.md -'
             ' a data-driven scan found no factor actually reproduces the measured effect): each tower'
             ' this many times wider in both eta and phi (need not be an integer; 1 = unchanged/offline'
             ' granularity; default: 1.0)')
    parser.add_argument('--charged-eff-pt-floor', type=float, default=0.5,
        help='HARD OVERRIDE (not data-driven): force Charged/Electron/Muon TrackingEfficiency to exactly'
             ' 0 in every pT bin that lies entirely below this value (GeV), for all |eta|. The data-driven'
             ' curves return a small nonzero tracking efficiency below ~0.5 GeV that is not trusted;'
             ' 0 disables this override (default: 0.5)')
    parser.add_argument('--puppi-use-charged', choices=['true', 'false'], default='true',
        help='RunPUPPIBase UseCharged on the GENERATED (HLT) card - see apply_puppi_use_charged().'
             ' "true" (default) leaves PUPPI exactly as the offline card has it, i.e. alpha scored'
             ' against leading-vertex CHARGED TRACKS only; "false" scores against ALL particles'
             ' instead, a reference population the HLT tracking retuning does not deplete, which'
             ' largely removes the reconstructed neutral-hadron/photon deficit per jet. NOTE:'
             ' JetEnergyScalePUPPIAK8 is derived assuming the "true" behaviour and is NOT'
             ' re-derived when this is set to "false" (default: true)')
    parser.add_argument('--hlt-jet-pt-min', type=float, default=1.0,
        help='FastJetFinderPUPPIAK8/AK15 JetPTMin on the GENERATED (HLT) card, HAND-SET - NOT copied'
             ' unchanged from the offline card (200/120 GeV) the way most modules are. Needs to be low'
             ' enough that a genuinely degraded jet is still constructed/written by Delphes rather than'
             ' silently dropped before the offline<->HLT jet-matching ntuplizer'
             ' (delphes_analyzers/makeNtuplesPaired.C) ever sees it - see this module\'s own docstring.'
             ' Default 1.0 GeV is effectively "no cut" (well below any realistic analysis threshold) while'
             ' avoiding the degenerate JetPTMin=0 edge case; lower further only if jets keep vanishing'
             ' below 1 GeV in practice, which should not happen for AK8/AK15 jets built from real activity.')
    parser.add_argument('--ip-curves', default=None,
        help='OPT-IN: JSON from derive_ip_curves.py; if given, the tracking efficiency of --ip-categories'
             ' becomes a (|eta|, pT, |d0|) table (HLT tracking loses displaced tracks) instead of the'
             ' (|eta|, pT) one from --curves - see build_ip_ratio_table() (default: off)')
    parser.add_argument('--ip-categories', default='chargedHadron,muon',
        help='comma-separated categories to apply --ip-curves to (default: chargedHadron,muon; electrons'
             ' have ~0 HLT efficiency anyway)')
    parser.add_argument('--ip-min-count', type=int, default=100,
        help='minimum offline tracks in an (eta, pt, d0) bin to use its own ratio (default: 100)')
    parser.add_argument('--no-puppi', action='store_true',
        help='OPT-IN: build the HLT jets (and the written ParticleFlowCandidates) without PUPPI or CHS,'
             ' as real scouting jets - see apply_no_puppi() (default: off)')
    parser.add_argument('--pu-track-z-window', type=float, default=None,
        help='with --no-puppi: drop (by truth) pile-up tracks farther than this many mm from the primary'
             ' vertex, emulating HLT tracking\'s z acceptance - see apply_no_puppi() (default: off, i.e.'
             ' keep all pile-up tracks)')
    parser.add_argument('--hlt-pf-pt-min', type=float, default=None,
        help='with --no-puppi: drop every HLT candidate (charged or neutral) with reconstructed pT below'
             ' this (GeV) before jet clustering/writing, as the scouting producer does (0.6 GeV in'
             ' ScoutingAK8) - see apply_no_puppi() (default: off)')
    parser.add_argument('--jes-correction', default=None,
        help='OPT-IN: JSON from derive_hlt_jes_correction.py; its per-HLT-jet-pT factors are multiplied onto'
             ' the JetEnergyScalePUPPIAK8 table (needed with --no-puppi, see that script) (default: off)')
    args = parser.parse_args()
    if args.pu_track_z_window is not None and not args.no_puppi:
        parser.error('--pu-track-z-window requires --no-puppi')
    if args.hlt_pf_pt_min is not None and not args.no_puppi:
        parser.error('--hlt-pf-pt-min requires --no-puppi')

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
        # hard override (see --charged-eff-pt-floor): the data-driven method
        # returns a small nonzero tracking efficiency below ~0.5 GeV that we
        # don't trust - force it to exactly 0 in every pT bin entirely below
        # the floor, for every eta bin.
        if args.charged_eff_pt_floor > 0:
            for ie in range(len(eta_edges) - 1):
                for ip in range(len(pt_edges) - 1):
                    if pt_edges[ip + 1] <= args.charged_eff_pt_floor + 1e-9:
                        table[ie][ip] = 0.0
        new_formula = format_piecewise_table(eta_edges, pt_edges, table, var_prefix='  ')
        text = replace_formula_block(text, module, 'EfficiencyFormula', new_formula)

    # --- opt-in: impact-parameter-dependent tracking efficiency (see build_ip_ratio_table) ---
    ip_curves = None
    ip_categories = [c for c in args.ip_categories.split(',') if c]
    if args.ip_curves:
        with open(args.ip_curves) as f:
            ip_curves = json.load(f)
        ib = ip_curves['binning']
        if ib['eta_edges'] != eta_edges or ib['pt_edges'] != pt_edges:
            raise SystemExit('--ip-curves uses a different (eta, pt) binning than --curves')
        d0_edges = ib['d0_edges_mm']
        # charged hadrons first: their d0 shapes are the fallback for sparser categories (muons)
        ch_shapes = None
        for cat in sorted(ip_categories, key=lambda c: c != 'chargedHadron'):
            module = EFFICIENCY_MODULES[cat]
            data = ip_curves['categories'][cat]
            offline_formula = extract_formula_block(offline_text, module, 'EfficiencyFormula')
            table, shapes = build_ip_ratio_table(
                data['n_offline'], data['n_matched'], offline_formula,
                eta_edges, pt_edges, d0_edges, args.ip_min_count, '{} d0-dependent efficiency'.format(cat),
                fallback_2d=(curves['categories'][cat]['efficiency_ratio'], curves['categories'][cat]['n_offline']),
                fallback_shapes=ch_shapes if cat != 'chargedHadron' else None)
            if cat == 'chargedHadron':
                ch_shapes = shapes
            if args.charged_eff_pt_floor > 0:
                for ie in range(len(eta_edges) - 1):
                    for ip in range(len(pt_edges) - 1):
                        if pt_edges[ip + 1] <= args.charged_eff_pt_floor + 1e-9:
                            table[ie][ip] = [0.0] * (len(d0_edges) - 1)
            new_formula = format_piecewise_table_3d(eta_edges, pt_edges, d0_edges, table, var_prefix='  ')
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
    jes_corr = None
    if args.jes_correction:
        with open(args.jes_correction) as f:
            jes_corr = json.load(f)
        if jes_corr['jet_pt_edges'] != jet_pt_edges:
            raise SystemExit('--jes-correction uses a different jet-pT binning than --curves')
        for ie in range(len(eta_edges) - 1):
            for ip in range(len(jet_pt_edges) - 1):
                jes_table[ie][ip] *= jes_corr['factors'][ip]
    new_jes_formula = format_piecewise_table(eta_edges, jet_pt_edges, jes_table, var_prefix='  ')
    text = replace_formula_block(text, 'JetEnergyScalePUPPIAK8', 'ScaleFormula', new_jes_formula)

    # --- ECal/HCal (hand-set "plan B", not data-driven - see function docstring) ---
    text = apply_calo_plan_b(text, args.calo_resolution_degradation, args.calo_granularity_factor)

    # --- PUPPI: the one setting the HLT card may differ in (see function docstring) ---
    text = apply_puppi_use_charged(text, args.puppi_use_charged == 'true')

    # --- HLT jet-finder JetPTMin (hand-set, structural - see module docstring) ---
    for module in ('FastJetFinderPUPPIAK8', 'FastJetFinderPUPPIAK15'):
        text = replace_scalar(text, module, 'JetPTMin', args.hlt_jet_pt_min)

    # --- opt-in: HLT jets without PUPPI/CHS (see apply_no_puppi) ---
    if args.no_puppi:
        text = apply_no_puppi(text, args.pu_track_z_window, args.hlt_pf_pt_min)

    header = make_header(args.curves, curves, args.offline_card,
                          args.calo_resolution_degradation, args.calo_granularity_factor,
                          args.hlt_jet_pt_min, args.charged_eff_pt_floor,
                          args.puppi_use_charged == 'true',
                          ip_curves_path=args.ip_curves, ip_curves=ip_curves, ip_categories=ip_categories,
                          no_puppi=args.no_puppi, z_window_mm=args.pu_track_z_window,
                          pf_pt_min=args.hlt_pf_pt_min, jes_correction_path=args.jes_correction, jes_correction=jes_corr)
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
