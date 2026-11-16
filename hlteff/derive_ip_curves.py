#!/usr/bin/env python3

'''Derive the offline-to-HLT tracking-efficiency ratio as a function of the transverse
impact parameter, in 3D bins of (|eta|, pT, |d0|) per charged category.

HLT tracking barely reconstructs displaced tracks, which the flat (pT, |eta|) ratio of
derive_curves.py can only absorb as an average over FullSim's own track population -
one with far more displaced tracks than Delphes has. Delphes efficiency formulas can
use `d0`, which ParticlePropagator has already set by the time the tracking-efficiency
modules run, so a d0-dependent HLT efficiency is expressible at card level.

`dz` is also accepted by a formula, but in Delphes it is the absolute z of closest
approach, with no access to the primary vertex z, so the z dependence cannot be
expressed the same way. It is measured here only as a side study, to choose a z window
generate_hlt_card.py can emulate through TrackPileUpSubtractor instead.

Method as in derive_curves.py: same input, same selection, same greedy deltaR matching
of offline to scouting candidates of the same category in the same jet. The matching
runs on all offline candidates of the category, so the assignment is identical to
derive_curves.py; only the counting applies the extra selection below. The offline
side's |dxy| is the |d0| variable.

The denominator differs from derive_curves.py, which counts every offline candidate:
  - lost tracks are excluded, being offline tracks without a PF candidate, which has
    no Delphes equivalent and must not dilute the efficiency applied to Delphes tracks;
  - pile-up-like tracks, prompt but far from the primary vertex in z, are excluded,
    since HLT drops those for its limited z acceptance rather than for their d0, and
    Delphes handles pile-up tracks separately, by truth.

Using the ratio as a multiplicative factor on an offline efficiency that does not
depend on d0 assumes the offline tracking efficiency is uniform in d0 within each
(|eta|, pT) bin.

Output: a JSON file consumed by generate_hlt_card.py --ip-curves and plotted by
plot_ip_curves.py. Neither curves_qcd.json nor any Delphes card is touched.

Usage:
  python derive_ip_curves.py [--input-dir DIR] [--n-files N] [--max-jets N]
                             [--dr-max DR] [--output PATH]
'''

import os
import sys
import json
import glob
import time
import argparse
from datetime import datetime, timezone

import numpy as np
import awkward as ak
import uproot

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from binning import PT_EDGES, ETA_EDGES
from derive_curves import DEFAULT_INPUT_DIR, CATEGORIES, CM_TO_MM, match_jet, wrap_phi

# |d0| bin edges in mm, the last one open-ended. Below the first edge the offline
# measurement is resolution-dominated and the HLT efficiency is flat anyway, so that
# bin is simply "prompt".
D0_EDGES = [0.0, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0, 1e9]

# |dz| bin edges in mm for the z-acceptance side study (prompt tracks only)
DZ_EDGES = [0.0, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 15.0, 20.0, 30.0, 50.0, 1e9]

BRANCHES = [
    'fj_isQCD', 'fj_eta', 'fj_phi', 'scoutfj_eta', 'scoutfj_phi',
    'cpfcandlt_etarel', 'cpfcandlt_phirel', 'cpfcandlt_px', 'cpfcandlt_py',
    'cpfcandlt_dxy', 'cpfcandlt_dz', 'cpfcandlt_isLostTrack',
    'cpfcandlt_isChargedHad', 'cpfcandlt_isEl', 'cpfcandlt_isMu',
    'scoutpfcand_etarel', 'scoutpfcand_phirel',
    'scoutpfcand_isChargedHad', 'scoutpfcand_isEl', 'scoutpfcand_isMu',
]


def bin_index(values, edges):
    '''np.digitize-based bin index; -1 outside [edges[0], edges[-1]).'''
    idx = np.digitize(values, edges) - 1
    idx[(idx < 0) | (idx >= len(edges) - 1)] = -1
    return idx


def main():
    '''Read the reference ntuples, fill the 3D count grids, and write the ratios.'''
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input-dir', default=DEFAULT_INPUT_DIR)
    parser.add_argument('--n-files', type=int, default=3,
        help='number of files to read, in sorted order (default: 3, as curves_qcd.json)')
    parser.add_argument('--max-jets', type=int, default=300000,
        help='stop after this many (QCD) jets (default: 300000)')
    parser.add_argument('--dr-max', type=float, default=0.03,
        help='max deltaR for an offline-scouting match (default: 0.03, as derive_curves.py)')
    parser.add_argument('--pu-like-dxy', type=float, default=0.1,
        help='|dxy| (mm) below which a track counts as prompt, for the pile-up-like exclusion (default: 0.1)')
    parser.add_argument('--pu-like-dz', type=float, default=1.0,
        help='prompt tracks with |dz| (mm) above this are pile-up-like and excluded (default: 1.0)')
    parser.add_argument('--chunk-size', type=int, default=20000)
    parser.add_argument('--output', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'curves_ip_qcd.json'))
    args = parser.parse_args()

    files = sorted(glob.glob(os.path.join(args.input_dir, 'dnnTuples_nanov15_*.root')))[:args.n_files]
    if not files:
        raise SystemExit('no dnnTuples_nanov15_*.root files found in {}'.format(args.input_dir))
    print('Reading {} file(s):'.format(len(files)))
    for fn in files:
        print('  ', fn)

    ne, npt, nd0, ndz = len(ETA_EDGES) - 1, len(PT_EDGES) - 1, len(D0_EDGES) - 1, len(DZ_EDGES) - 1
    n_offline = {c: np.zeros((ne, npt, nd0), dtype=np.int64) for c in CATEGORIES}
    n_matched = {c: np.zeros((ne, npt, nd0), dtype=np.int64) for c in CATEGORIES}
    n_excluded = {c: {'lost': 0, 'pu_like': 0, 'kept': 0} for c in CATEGORIES}
    # z-acceptance side study: charged hadrons, not lost, prompt; binned (|eta|, pT, |dz|)
    dz_off = np.zeros((ne, npt, ndz), dtype=np.int64)
    dz_match = np.zeros((ne, npt, ndz), dtype=np.int64)

    n_jets_done, t0, stop = 0, time.time(), False
    for fn in files:
        if stop:
            break
        with uproot.open(fn) as f:
            for chunk in f['tree'].iterate(BRANCHES, step_size=args.chunk_size, library='ak'):
                chunk = chunk[chunk['fj_isQCD'] == 1]
                if len(chunk) == 0:
                    continue
                fj_eta = ak.to_numpy(chunk['fj_eta'])
                fj_phi = ak.to_numpy(chunk['fj_phi'])
                scoutfj_eta = ak.to_numpy(chunk['scoutfj_eta'])
                scoutfj_phi = ak.to_numpy(chunk['scoutfj_phi'])
                for j in range(len(chunk)):
                    off_eta_all = fj_eta[j] + np.asarray(chunk['cpfcandlt_etarel'][j], dtype=np.float64)
                    off_phi_all = wrap_phi(fj_phi[j] + np.asarray(chunk['cpfcandlt_phirel'][j], dtype=np.float64))
                    off_pt_all = np.hypot(np.asarray(chunk['cpfcandlt_px'][j], dtype=np.float64),
                                          np.asarray(chunk['cpfcandlt_py'][j], dtype=np.float64))
                    off_dxy_all = np.abs(np.asarray(chunk['cpfcandlt_dxy'][j], dtype=np.float64)) * CM_TO_MM
                    off_dz_all = np.abs(np.asarray(chunk['cpfcandlt_dz'][j], dtype=np.float64)) * CM_TO_MM
                    off_lost_all = np.asarray(chunk['cpfcandlt_isLostTrack'][j]) != 0
                    scout_eta_all = scoutfj_eta[j] + np.asarray(chunk['scoutpfcand_etarel'][j], dtype=np.float64)
                    scout_phi_all = wrap_phi(scoutfj_phi[j] + np.asarray(chunk['scoutpfcand_phirel'][j], dtype=np.float64))

                    for cat, (off_flag, scout_flag) in CATEGORIES.items():
                        om = np.asarray(chunk[off_flag][j]) != 0
                        sm = np.asarray(chunk[scout_flag][j]) != 0
                        if not om.any():
                            continue
                        # match on ALL offline candidates of the category (as derive_curves.py)
                        match = match_jet(off_eta_all[om], off_phi_all[om], scout_eta_all[sm], scout_phi_all[sm], args.dr_max)
                        matched = match >= 0
                        eta, pt = np.abs(off_eta_all[om]), off_pt_all[om]
                        dxy, dz, lost = off_dxy_all[om], off_dz_all[om], off_lost_all[om]
                        prompt = dxy < args.pu_like_dxy
                        pu_like = prompt & (dz > args.pu_like_dz) & ~lost
                        keep = ~lost & ~pu_like & np.isfinite(dxy)
                        n_excluded[cat]['lost'] += int(lost.sum())
                        n_excluded[cat]['pu_like'] += int(pu_like.sum())
                        n_excluded[cat]['kept'] += int(keep.sum())

                        ie, ip, i0 = bin_index(eta, ETA_EDGES), bin_index(pt, PT_EDGES), bin_index(dxy, D0_EDGES)
                        ok = keep & (ie >= 0) & (ip >= 0) & (i0 >= 0)
                        np.add.at(n_offline[cat], (ie[ok], ip[ok], i0[ok]), 1)
                        okm = ok & matched
                        np.add.at(n_matched[cat], (ie[okm], ip[okm], i0[okm]), 1)

                        if cat == 'chargedHadron':
                            iz = bin_index(dz, DZ_EDGES)
                            okz = ~lost & prompt & (ie >= 0) & (ip >= 0) & (iz >= 0)
                            np.add.at(dz_off, (ie[okz], ip[okz], iz[okz]), 1)
                            okzm = okz & matched
                            np.add.at(dz_match, (ie[okzm], ip[okzm], iz[okzm]), 1)

                n_jets_done += len(chunk)
                print('  processed {} jets ({:.1f} jets/s)'.format(n_jets_done, n_jets_done / max(time.time() - t0, 1e-9)))
                if n_jets_done >= args.max_jets:
                    stop = True
                    break
    print('Total jets processed: {} in {:.1f}s'.format(n_jets_done, time.time() - t0))

    def ratio(num, den):
        '''num / den, with non-finite results replaced by NaN.'''
        with np.errstate(invalid='ignore', divide='ignore'):
            r = num / den
        return np.where(np.isfinite(r), r, np.nan)

    def to_list(a):
        '''Convert an array to nested lists, mapping non-finite values to None so the result is
        JSON-serializable.
        '''
        return [None if not np.isfinite(v) else float(v) for v in a.ravel()] if a.ndim == 1 else [to_list(x) for x in a]

    result = {
        'source': {
            'input_dir': args.input_dir,
            'files': files,
            'n_jets_processed': n_jets_done,
            'dr_max': args.dr_max,
            'selection': 'fj_isQCD == 1',
            'denominator': ('offline cpfcandlt_* of the category, excluding lost tracks and pile-up-like '
                            'tracks (|dxy| < {} mm and |dz| > {} mm); matching done on all candidates'.format(
                                args.pu_like_dxy, args.pu_like_dz)),
            'assumption': 'offline tracking efficiency uniform in d0 within each (|eta|, pT) bin',
            'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        },
        'binning': {'pt_edges': PT_EDGES, 'eta_edges': ETA_EDGES, 'd0_edges_mm': D0_EDGES, 'dz_edges_mm': DZ_EDGES},
        'categories': {},
        'dz_acceptance': {
            'note': ('charged hadrons, not lost, prompt (|dxy| < {} mm); offline |dz| w.r.t. the offline PV; '
                     'binned (|eta|, pT, |dz|) - measures HLT tracking\'s z acceptance, which Delphes '
                     'formulas cannot express (their dz is absolute)'.format(args.pu_like_dxy)),
            'n_offline': dz_off.tolist(),
            'n_matched': dz_match.tolist(),
            'efficiency_ratio': to_list(ratio(dz_match, dz_off)),
        },
    }
    for cat in CATEGORIES:
        result['categories'][cat] = {
            'n_offline': n_offline[cat].tolist(),
            'n_matched': n_matched[cat].tolist(),
            'efficiency_ratio': to_list(ratio(n_matched[cat], n_offline[cat])),
            # same denominator, inclusive in d0 - for comparison with curves_qcd.json
            'efficiency_ratio_d0_inclusive': to_list(ratio(n_matched[cat].sum(axis=2), n_offline[cat].sum(axis=2))),
            'n_candidates': n_excluded[cat],
        }

    with open(args.output, 'w') as fout:
        json.dump(result, fout, indent=1)
    print('Wrote', args.output)


if __name__ == '__main__':
    main()
