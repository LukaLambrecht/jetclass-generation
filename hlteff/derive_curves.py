#!/usr/bin/env python3

'''
Derive data-driven offline-vs-HLT("scouting") charged-particle tracking
efficiency and momentum-resolution degradation curves, from paired
offline/scouting CMS ntuples (see README.md for what these files contain
and where they come from).

For each jet, offline candidates (cpfcandlt_*, split by isChargedHad/isEl/isMu)
are geometrically matched (nearest-neighbor in (eta,phi), greedy, within
--dr-max) to scouting candidates (scoutpfcand_*, same category flags) in the
same jet. Per (category, |eta| bin, pT bin) - see binning.py - we record:
  - n_offline: number of offline candidates (the efficiency denominator)
  - n_matched: number of those with a scouting match (the numerator)
  - the distribution of (pt_scout - pt_offline)/pt_offline for matched pairs,
    summarized as a robust sigma (half the 16-84 percentile width), i.e. how
    much *extra* smearing scouting reconstruction adds on top of whatever
    offline resolution already is.

For every matched pair, regardless of category (chargedHadron/electron/muon
combined, matching TrackMerger's own species-agnostic pooling upstream of
TrackSmearing), we additionally record (scout_dxy - off_dxy) and
(scout_dz - off_dz), converted from the ntuple's cm to the Delphes card's mm
(see README "Notable findings" for how that unit inference was made) -
the same kind of "extra smearing" measurement as pT, but for the impact
parameters TrackSmearing's D0/DZResolutionFormula model.

Separately, and needing no per-particle matching at all (the jets
themselves are already paired row-by-row, see README), we measure the
direct scoutfj_pt/fj_pt ratio - binned by the jet's own (pT, |eta|) on the
coarser JET_PT_EDGES grid - for JetEnergyScalePUPPIAK8, plus fj_pt/fj_genjet_pt
(offline reco vs. real gen-jet truth) purely as a documentation/validation
number (see the module's own comments for why only the offline side has a
usable truth reference in this ntuple production).

Neutral particles (photon/neutralHadron, via npfcand_*/scoutpfcand_* isGamma/
isNeutralHad flags) are matched the same way as the charged categories, but
binned by *energy* (reusing PT_EDGES as an energy grid, since Delphes'
SimpleCalorimeter ResolutionFormula is a function of energy, not pT) rather
than pT, and the "extra smearing" is the *absolute* (scout_energy -
off_energy) in GeV (not a relative difference - ECal/HCal's resolution
formulas are already absolute-GeV, unlike the fractional pT resolution
formulas). There's no Efficiency module for neutrals to retune this way
(see README "Scope"), so this measurement instead feeds a separate
closure check (see check_calo_closure.py): does degrading only the
resolution formula (holding EnergyMin/EnergySignificanceMin fixed)
reproduce the neutral efficiency loss (n_matched/n_offline) that's
measured directly here, or is there a residual that resolution alone
can't explain?

Output is a single JSON file (default hlteff/curves_qcd.json) consumed by
generate_hlt_card.py to actually build the new Delphes card - this script
only measures, it does not touch any Delphes card itself.

Usage:
  python derive_curves.py [--input-dir DIR] [--n-files N] [--max-jets N]
                           [--dr-max DR] [--output PATH]

Default input is the QCD sample (see README for why QCD, not signal, is
the basis here).
'''

import os
import sys
import json
import glob
import argparse
import time
from datetime import datetime, timezone

import numpy as np
import awkward as ak
import uproot

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from binning import (PT_EDGES, ETA_EDGES, JET_PT_EDGES, n_pt_bins, n_eta_bins, n_jet_pt_bins,
                      pt_bin_index, eta_bin_index, jet_pt_bin_index)

DEFAULT_INPUT_DIR = '/eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/QCD_PT-mixed_TuneCP5_13p6TeV_pythia8_new'

# (category name) -> (offline flag branch, scouting flag branch)
CATEGORIES = {
    'chargedHadron': ('cpfcandlt_isChargedHad', 'scoutpfcand_isChargedHad'),
    'electron':      ('cpfcandlt_isEl',         'scoutpfcand_isEl'),
    'muon':          ('cpfcandlt_isMu',         'scoutpfcand_isMu'),
}

# neutral categories: offline collection is npfcand_* (not cpfcandlt_*)
NEUTRAL_CATEGORIES = {
    'photon':        ('npfcand_isGamma',     'scoutpfcand_isGamma'),
    'neutralHadron': ('npfcand_isNeutralHad', 'scoutpfcand_isNeutralHad'),
}

# the ntuple stores dxy/dz in cm (inferred from magnitude: median offline
# |dxy| ~43 micron, physically sensible for cm); the Delphes card's D0/DZ
# resolution tables are in mm (their own low-pT/high-pT endpoints, 0.35mm
# and 0.011mm, match published CMS d0-resolution curves in mm) - see
# README "Notable findings".
CM_TO_MM = 10.0

BRANCHES = [
    'fj_isQCD', 'fj_eta', 'fj_phi', 'fj_pt', 'fj_genjet_pt',
    'scoutfj_eta', 'scoutfj_phi', 'scoutfj_pt',
    'cpfcandlt_etarel', 'cpfcandlt_phirel', 'cpfcandlt_px', 'cpfcandlt_py',
    'cpfcandlt_dxy', 'cpfcandlt_dz',
    'cpfcandlt_isChargedHad', 'cpfcandlt_isEl', 'cpfcandlt_isMu',
    'npfcand_etarel', 'npfcand_phirel', 'npfcand_energy',
    'npfcand_isGamma', 'npfcand_isNeutralHad',
    'scoutpfcand_etarel', 'scoutpfcand_phirel', 'scoutpfcand_px', 'scoutpfcand_py',
    'scoutpfcand_energy', 'scoutpfcand_dxy', 'scoutpfcand_dz',
    'scoutpfcand_isChargedHad', 'scoutpfcand_isEl', 'scoutpfcand_isMu',
    'scoutpfcand_isGamma', 'scoutpfcand_isNeutralHad',
]


def wrap_phi(phi):
    return (phi + np.pi) % (2 * np.pi) - np.pi


def match_jet(off_eta, off_phi, scout_eta, scout_phi, dr_max,
              off_energy=None, scout_energy=None, rel_e_tol=None):
    '''
    Greedy nearest-neighbor matching within dr_max between one jet's offline
    and scouting candidates (of the same category). Returns an array of
    length len(off_eta): the matched scouting index, or -1 if unmatched.

    ACCEPTANCE is purely geometric (deltaR < dr_max) - that gate is
    unchanged by the energy option below. What can change is the ASSIGNMENT
    ORDER among candidates that both pass that gate: by default (off_energy/
    scout_energy/rel_e_tol all None) pairs are assigned strictly
    closest-deltaR-first, so a scouting candidate is never claimed by two
    offline candidates. If off_energy/scout_energy/rel_e_tol are given,
    pairs are instead ranked by (deltaR/dr_max)^2 + (relative energy
    difference/rel_e_tol)^2 - i.e. within the same geometric window,
    energy-similar pairs are preferred over energy-dissimilar ones. This is
    a soft disambiguator, not a second cut: it only changes *which* nearby
    candidate wins when several are within dr_max of each other (e.g.
    overlapping calorimeter showers), not whether a candidate is matched at
    all - so with a generous rel_e_tol it shouldn't meaningfully bias the
    energy-difference distribution among genuinely unambiguous pairs, which
    is what makes it safe to use for measuring that same distribution (see
    README "Notable findings" - this exists to address the HCal matched-pair
    energy-difference blowup, suspected to be shower-matching confusion).
    '''
    n_off = off_eta.shape[0]
    n_scout = scout_eta.shape[0]
    match = np.full(n_off, -1, dtype=np.int64)
    if n_off == 0 or n_scout == 0:
        return match

    deta = off_eta[:, None] - scout_eta[None, :]
    dphi = wrap_phi(off_phi[:, None] - scout_phi[None, :])
    dR2 = deta * deta + dphi * dphi
    dr_max2 = dr_max * dr_max

    if off_energy is not None:
        rel_ediff = (scout_energy[None, :] - off_energy[:, None]) / np.maximum(off_energy[:, None], 1e-6)
        rank_metric = dR2 / dr_max2 + (rel_ediff / rel_e_tol) ** 2
    else:
        rank_metric = dR2

    order = np.argsort(rank_metric, axis=None)
    flat_dR2 = dR2.ravel()
    flat_rank = rank_metric.ravel()
    used_off = np.zeros(n_off, dtype=bool)
    used_scout = np.zeros(n_scout, dtype=bool)
    n_to_match = min(n_off, n_scout)
    n_matched = 0
    for idx in order:
        if flat_dR2[idx] > dr_max2:
            continue  # not "break": rank_metric order != dR2 order once energy is included
        i, j = divmod(int(idx), n_scout)
        if used_off[i] or used_scout[j]:
            continue
        used_off[i] = True
        used_scout[j] = True
        match[i] = j
        n_matched += 1
        if n_matched == n_to_match:
            break
    return match


def robust_sigma(values, min_count=20):
    ### half the 16th-84th percentile width - a resolution estimator that's
    # far less sensitive to occasional mismatched pairs than a plain std
    if len(values) < min_count:
        return None
    lo, hi = np.percentile(values, [15.87, 84.13])
    return float((hi - lo) / 2.0)


def robust_median(values, min_count=20):
    if len(values) < min_count:
        return None
    return float(np.median(values))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input-dir', default=DEFAULT_INPUT_DIR,
        help='directory of dnnTuples_nanov15_*.root files (default: QCD training sample)')
    parser.add_argument('--n-files', type=int, default=2,
        help='number of files to read from --input-dir, in sorted order (default: 2)')
    parser.add_argument('--max-jets', type=int, default=150000,
        help='stop after processing this many jets total, across all files (default: 150000)')
    parser.add_argument('--dr-max', type=float, default=0.03,
        help='max deltaR for an offline-scouting candidate to be considered the same'
             ' particle - used for chargedHadron/electron/muon matching (default: 0.03)')
    parser.add_argument('--dr-max-neutral', type=float, default=None,
        help='same as --dr-max, but for photon/neutralHadron matching (default: same as --dr-max).'
             ' Tested tighter (0.015) + --neutral-use-energy together: made ECal *worse* (the'
             ' tighter window excludes genuine matches whose shower centroid shifts a bit between'
             ' offline/HLT) and left HCal\'s high-energy sigma blowup essentially unchanged (so'
             ' that\'s not a matching-precision problem - see README "Notable findings") - kept'
             ' available for further experimentation, not because it\'s recommended')
    parser.add_argument('--neutral-use-energy', action='store_true',
        help='enable the soft energy-aware tie-break for photon/neutralHadron matching (see'
             ' match_jet docstring); off by default - see --dr-max-neutral help for why')
    parser.add_argument('--rel-e-tol', type=float, default=1.0,
        help='relative-energy tolerance for --neutral-use-energy (default: 1.0)')
    parser.add_argument('--chunk-size', type=int, default=20000,
        help='entries per uproot read chunk (default: 20000)')
    parser.add_argument('--output', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'curves_qcd.json'),
        help='output JSON path (default: hlteff/curves_qcd.json)')
    args = parser.parse_args()
    if args.dr_max_neutral is None:
        args.dr_max_neutral = args.dr_max

    files = sorted(glob.glob(os.path.join(args.input_dir, 'dnnTuples_nanov15_*.root')))[:args.n_files]
    if not files:
        raise SystemExit('no dnnTuples_nanov15_*.root files found in {}'.format(args.input_dir))
    print('Reading {} file(s):'.format(len(files)))
    for fn in files:
        print('  ', fn)

    ne, npt = n_eta_bins(), n_pt_bins()
    n_offline = {c: np.zeros((ne, npt), dtype=np.int64) for c in CATEGORIES}
    n_matched = {c: np.zeros((ne, npt), dtype=np.int64) for c in CATEGORIES}
    pt_reldiff = {c: [[[] for _ in range(npt)] for _ in range(ne)] for c in CATEGORIES}
    # impact-parameter differences, pooled across all categories (see
    # module docstring - matches TrackSmearing's own species-agnostic input)
    dxy_diff = [[[] for _ in range(npt)] for _ in range(ne)]
    dz_diff = [[[] for _ in range(npt)] for _ in range(ne)]

    ne_jet, npt_jet = n_eta_bins(), n_jet_pt_bins()
    jes_response_offline = [[[] for _ in range(npt_jet)] for _ in range(ne_jet)]
    jes_response_scout = [[[] for _ in range(npt_jet)] for _ in range(ne_jet)]

    # neutral (calorimeter) categories: binned by energy (reusing PT_EDGES,
    # see module docstring), "extra smearing" is an absolute energy diff (GeV)
    n_offline_neutral = {c: np.zeros((ne, npt), dtype=np.int64) for c in NEUTRAL_CATEGORIES}
    n_matched_neutral = {c: np.zeros((ne, npt), dtype=np.int64) for c in NEUTRAL_CATEGORIES}
    energy_diff = {c: [[[] for _ in range(npt)] for _ in range(ne)] for c in NEUTRAL_CATEGORIES}

    n_jets_done = 0
    t0 = time.time()
    stop = False
    for fn in files:
        if stop:
            break
        with uproot.open(fn) as f:
            tree = f['tree']
            for chunk in tree.iterate(BRANCHES, step_size=args.chunk_size, library='ak'):
                chunk = chunk[chunk['fj_isQCD'] == 1]
                n_jets_chunk = len(chunk)
                if n_jets_chunk == 0:
                    continue

                fj_eta = ak.to_numpy(chunk['fj_eta'])
                fj_phi = ak.to_numpy(chunk['fj_phi'])
                scoutfj_eta = ak.to_numpy(chunk['scoutfj_eta'])
                scoutfj_phi = ak.to_numpy(chunk['scoutfj_phi'])

                # jet energy scale: whole-jet quantities, no per-particle
                # matching needed (the jets are already paired row-by-row).
                #
                # fj_gen_pt/fj_gen_deltaR (and their scoutfj_ counterparts)
                # are NOT generic gen-jet matching - they're -999/999
                # sentinels for every jet in this QCD sample (they match to
                # a specific signal resonance, which QCD jets don't have).
                # fj_genjet_pt (genuine dR-matched gen-jet truth) IS
                # populated, but there is no scoutfj_genjet_pt at all in
                # this ntuple production - so a truth-based measurement is
                # only possible on the offline side. We use it there purely
                # as a validation/documentation number (is the offline
                # card's ScaleFormula=1.00 - i.e. "no correction" - actually
                # justified by real data?), and separately measure the
                # direct scoutfj_pt/fj_pt ratio (no truth reference needed)
                # for the actual HLT ScaleFormula, applying the same
                # "offline formula x measured ratio" convention used
                # everywhere else in this pipeline. See README for the
                # resulting numbers and the double-counting caveat this
                # carries (the ratio is measured in real data, but applied
                # on top of jets already built from the retuned, already
                # somewhat-degraded track-level modules).
                fj_pt = ak.to_numpy(chunk['fj_pt'])
                fj_genjet_pt = ak.to_numpy(chunk['fj_genjet_pt'])
                scoutfj_pt = ak.to_numpy(chunk['scoutfj_pt'])

                good_offline = np.isfinite(fj_genjet_pt) & (fj_genjet_pt > 0)
                for j in np.nonzero(good_offline)[0]:
                    ie = eta_bin_index(abs(fj_eta[j]))
                    ip = jet_pt_bin_index(fj_pt[j])
                    if ie is None or ip is None:
                        continue
                    jes_response_offline[ie][ip].append(fj_pt[j] / fj_genjet_pt[j])

                good_pair = np.isfinite(fj_pt) & (fj_pt > 0) & np.isfinite(scoutfj_pt)
                for j in np.nonzero(good_pair)[0]:
                    ie = eta_bin_index(abs(fj_eta[j]))
                    ip = jet_pt_bin_index(fj_pt[j])
                    if ie is None or ip is None:
                        continue
                    jes_response_scout[ie][ip].append(scoutfj_pt[j] / fj_pt[j])

                for j in range(n_jets_chunk):
                    off_eta_abs_all = fj_eta[j] + np.asarray(chunk['cpfcandlt_etarel'][j], dtype=np.float64)
                    off_phi_abs_all = wrap_phi(fj_phi[j] + np.asarray(chunk['cpfcandlt_phirel'][j], dtype=np.float64))
                    off_px_all = np.asarray(chunk['cpfcandlt_px'][j], dtype=np.float64)
                    off_py_all = np.asarray(chunk['cpfcandlt_py'][j], dtype=np.float64)
                    off_pt_all = np.hypot(off_px_all, off_py_all)
                    off_dxy_all = np.asarray(chunk['cpfcandlt_dxy'][j], dtype=np.float64) * CM_TO_MM
                    off_dz_all = np.asarray(chunk['cpfcandlt_dz'][j], dtype=np.float64) * CM_TO_MM

                    scout_eta_abs_all = scoutfj_eta[j] + np.asarray(chunk['scoutpfcand_etarel'][j], dtype=np.float64)
                    scout_phi_abs_all = wrap_phi(scoutfj_phi[j] + np.asarray(chunk['scoutpfcand_phirel'][j], dtype=np.float64))
                    scout_px_all = np.asarray(chunk['scoutpfcand_px'][j], dtype=np.float64)
                    scout_py_all = np.asarray(chunk['scoutpfcand_py'][j], dtype=np.float64)
                    scout_pt_all = np.hypot(scout_px_all, scout_py_all)
                    scout_dxy_all = np.asarray(chunk['scoutpfcand_dxy'][j], dtype=np.float64) * CM_TO_MM
                    scout_dz_all = np.asarray(chunk['scoutpfcand_dz'][j], dtype=np.float64) * CM_TO_MM
                    scout_energy_all = np.asarray(chunk['scoutpfcand_energy'][j], dtype=np.float64)

                    # neutral (calorimeter) candidates - offline side uses
                    # the same fj_eta/phi jet axis as cpfcandlt (both are
                    # offline PF collections of the same offline jet)
                    noff_eta_abs_all = fj_eta[j] + np.asarray(chunk['npfcand_etarel'][j], dtype=np.float64)
                    noff_phi_abs_all = wrap_phi(fj_phi[j] + np.asarray(chunk['npfcand_phirel'][j], dtype=np.float64))
                    noff_energy_all = np.asarray(chunk['npfcand_energy'][j], dtype=np.float64)

                    for cat, (off_flag_branch, scout_flag_branch) in CATEGORIES.items():
                        off_mask = np.asarray(chunk[off_flag_branch][j]) != 0
                        scout_mask = np.asarray(chunk[scout_flag_branch][j]) != 0

                        off_eta = off_eta_abs_all[off_mask]
                        off_phi = off_phi_abs_all[off_mask]
                        off_pt = off_pt_all[off_mask]
                        off_dxy = off_dxy_all[off_mask]
                        off_dz = off_dz_all[off_mask]
                        scout_eta = scout_eta_abs_all[scout_mask]
                        scout_phi = scout_phi_abs_all[scout_mask]
                        scout_pt = scout_pt_all[scout_mask]
                        scout_dxy = scout_dxy_all[scout_mask]
                        scout_dz = scout_dz_all[scout_mask]

                        match = match_jet(off_eta, off_phi, scout_eta, scout_phi, args.dr_max)

                        for k in range(len(off_pt)):
                            ie = eta_bin_index(abs(off_eta[k]))
                            ip = pt_bin_index(off_pt[k])
                            if ie is None or ip is None:
                                continue
                            n_offline[cat][ie, ip] += 1
                            if match[k] >= 0:
                                n_matched[cat][ie, ip] += 1
                                reldiff = (scout_pt[match[k]] - off_pt[k]) / off_pt[k]
                                pt_reldiff[cat][ie][ip].append(reldiff)
                                if np.isfinite(off_dxy[k]) and np.isfinite(scout_dxy[match[k]]):
                                    dxy_diff[ie][ip].append(scout_dxy[match[k]] - off_dxy[k])
                                if np.isfinite(off_dz[k]) and np.isfinite(scout_dz[match[k]]):
                                    dz_diff[ie][ip].append(scout_dz[match[k]] - off_dz[k])

                    for cat, (off_flag_branch, scout_flag_branch) in NEUTRAL_CATEGORIES.items():
                        off_mask = np.asarray(chunk[off_flag_branch][j]) != 0
                        scout_mask = np.asarray(chunk[scout_flag_branch][j]) != 0

                        off_eta = noff_eta_abs_all[off_mask]
                        off_phi = noff_phi_abs_all[off_mask]
                        off_energy = noff_energy_all[off_mask]
                        scout_eta = scout_eta_abs_all[scout_mask]
                        scout_phi = scout_phi_abs_all[scout_mask]
                        scout_energy = scout_energy_all[scout_mask]

                        if args.neutral_use_energy:
                            match = match_jet(off_eta, off_phi, scout_eta, scout_phi, args.dr_max_neutral,
                                               off_energy=off_energy, scout_energy=scout_energy,
                                               rel_e_tol=args.rel_e_tol)
                        else:
                            match = match_jet(off_eta, off_phi, scout_eta, scout_phi, args.dr_max_neutral)

                        for k in range(len(off_energy)):
                            ie = eta_bin_index(abs(off_eta[k]))
                            ip = pt_bin_index(off_energy[k])  # PT_EDGES reused as energy edges
                            if ie is None or ip is None:
                                continue
                            n_offline_neutral[cat][ie, ip] += 1
                            if match[k] >= 0:
                                n_matched_neutral[cat][ie, ip] += 1
                                if np.isfinite(off_energy[k]) and np.isfinite(scout_energy[match[k]]):
                                    energy_diff[cat][ie][ip].append(scout_energy[match[k]] - off_energy[k])

                n_jets_done += n_jets_chunk
                elapsed = time.time() - t0
                print('  processed {} jets ({:.1f} jets/s)'.format(n_jets_done, n_jets_done / max(elapsed, 1e-9)))
                if n_jets_done >= args.max_jets:
                    stop = True
                    break

    print('Total jets processed: {} in {:.1f}s'.format(n_jets_done, time.time() - t0))

    result = {
        'source': {
            'input_dir': args.input_dir,
            'files': files,
            'n_jets_processed': n_jets_done,
            'dr_max': args.dr_max,
            'selection': 'fj_isQCD == 1',
            'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        },
        'binning': {'pt_edges': PT_EDGES, 'eta_edges': ETA_EDGES, 'jet_pt_edges': JET_PT_EDGES},
        'categories': {},
    }
    for cat in CATEGORIES:
        with np.errstate(invalid='ignore', divide='ignore'):
            ratio = n_matched[cat] / n_offline[cat]
        sigma_extra = [[robust_sigma(pt_reldiff[cat][ie][ip]) for ip in range(npt)] for ie in range(ne)]
        n_pairs = [[len(pt_reldiff[cat][ie][ip]) for ip in range(npt)] for ie in range(ne)]
        result['categories'][cat] = {
            'n_offline': n_offline[cat].tolist(),
            'n_matched': n_matched[cat].tolist(),
            'efficiency_ratio': [[None if not np.isfinite(v) else float(v) for v in row] for row in ratio],
            'n_matched_pairs': n_pairs,
            'sigma_extra_pt': sigma_extra,
        }

    result['trackImpactParameter'] = {
        'unit': 'mm (converted from the ntuple\'s cm via CM_TO_MM - see module docstring)',
        'pooled_categories': list(CATEGORIES),
        'n_pairs': [[len(dxy_diff[ie][ip]) for ip in range(npt)] for ie in range(ne)],
        'sigma_extra_dxy': [[robust_sigma(dxy_diff[ie][ip]) for ip in range(npt)] for ie in range(ne)],
        'sigma_extra_dz': [[robust_sigma(dz_diff[ie][ip]) for ip in range(npt)] for ie in range(ne)],
    }

    result['jetEnergyScale'] = {
        'note': 'response_offline_vs_genjet (fj_pt/fj_genjet_pt) is a validation number only'
                ' (is offline\'s own ScaleFormula=1.00 justified by real data?); the card is built'
                ' from scout_over_offline_ratio (scoutfj_pt/fj_pt) - see module docstring',
        'n_jets_offline_vs_genjet': [[len(jes_response_offline[ie][ip]) for ip in range(npt_jet)] for ie in range(ne_jet)],
        'n_jets_scout_over_offline': [[len(jes_response_scout[ie][ip]) for ip in range(npt_jet)] for ie in range(ne_jet)],
        'response_offline_vs_genjet': [[robust_median(jes_response_offline[ie][ip]) for ip in range(npt_jet)] for ie in range(ne_jet)],
        'scout_over_offline_ratio': [[robust_median(jes_response_scout[ie][ip]) for ip in range(npt_jet)] for ie in range(ne_jet)],
    }

    result['neutralCalorimeter'] = {
        'note': 'binned by particle ENERGY, reusing PT_EDGES as the energy grid (see module docstring);'
                ' no Efficiency module exists for these to retune directly - see check_calo_closure.py',
        'energy_edges': PT_EDGES,
        'categories': {},
    }
    for cat in NEUTRAL_CATEGORIES:
        with np.errstate(invalid='ignore', divide='ignore'):
            ratio = n_matched_neutral[cat] / n_offline_neutral[cat]
        sigma_extra = [[robust_sigma(energy_diff[cat][ie][ip]) for ip in range(npt)] for ie in range(ne)]
        n_pairs = [[len(energy_diff[cat][ie][ip]) for ip in range(npt)] for ie in range(ne)]
        result['neutralCalorimeter']['categories'][cat] = {
            'n_offline': n_offline_neutral[cat].tolist(),
            'n_matched': n_matched_neutral[cat].tolist(),
            'efficiency_ratio': [[None if not np.isfinite(v) else float(v) for v in row] for row in ratio],
            'n_matched_pairs': n_pairs,
            'sigma_extra_energy': sigma_extra,
        }

    with open(args.output, 'w') as fout:
        json.dump(result, fout, indent=1)
    print('Wrote', args.output)


if __name__ == '__main__':
    main()
