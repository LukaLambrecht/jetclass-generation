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
from binning import PT_EDGES, ETA_EDGES, n_pt_bins, n_eta_bins, pt_bin_index, eta_bin_index

DEFAULT_INPUT_DIR = '/eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/QCD_PT-mixed_TuneCP5_13p6TeV_pythia8_new'

# (category name) -> (offline flag branch, scouting flag branch)
CATEGORIES = {
    'chargedHadron': ('cpfcandlt_isChargedHad', 'scoutpfcand_isChargedHad'),
    'electron':      ('cpfcandlt_isEl',         'scoutpfcand_isEl'),
    'muon':          ('cpfcandlt_isMu',         'scoutpfcand_isMu'),
}

BRANCHES = [
    'fj_isQCD', 'fj_eta', 'fj_phi', 'scoutfj_eta', 'scoutfj_phi',
    'cpfcandlt_etarel', 'cpfcandlt_phirel', 'cpfcandlt_px', 'cpfcandlt_py',
    'cpfcandlt_isChargedHad', 'cpfcandlt_isEl', 'cpfcandlt_isMu',
    'scoutpfcand_etarel', 'scoutpfcand_phirel', 'scoutpfcand_px', 'scoutpfcand_py',
    'scoutpfcand_isChargedHad', 'scoutpfcand_isEl', 'scoutpfcand_isMu',
]


def wrap_phi(phi):
    return (phi + np.pi) % (2 * np.pi) - np.pi


def match_jet(off_eta, off_phi, scout_eta, scout_phi, dr_max):
    '''
    Greedy nearest-neighbor matching within dr_max between one jet's offline
    and scouting candidates (of the same category). Returns an array of
    length len(off_eta): the matched scouting index, or -1 if unmatched.
    Matches are assigned globally-closest-pair-first (not just per-offline-
    candidate nearest), so a scouting candidate is never claimed by two
    offline candidates.
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

    order = np.argsort(dR2, axis=None)
    flat = dR2.ravel()
    used_off = np.zeros(n_off, dtype=bool)
    used_scout = np.zeros(n_scout, dtype=bool)
    n_to_match = min(n_off, n_scout)
    n_matched = 0
    for idx in order:
        if flat[idx] > dr_max2:
            break
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
             ' particle (default: 0.03)')
    parser.add_argument('--chunk-size', type=int, default=20000,
        help='entries per uproot read chunk (default: 20000)')
    parser.add_argument('--output', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'curves_qcd.json'),
        help='output JSON path (default: hlteff/curves_qcd.json)')
    args = parser.parse_args()

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

                for j in range(n_jets_chunk):
                    off_eta_abs_all = fj_eta[j] + np.asarray(chunk['cpfcandlt_etarel'][j], dtype=np.float64)
                    off_phi_abs_all = wrap_phi(fj_phi[j] + np.asarray(chunk['cpfcandlt_phirel'][j], dtype=np.float64))
                    off_px_all = np.asarray(chunk['cpfcandlt_px'][j], dtype=np.float64)
                    off_py_all = np.asarray(chunk['cpfcandlt_py'][j], dtype=np.float64)
                    off_pt_all = np.hypot(off_px_all, off_py_all)

                    scout_eta_abs_all = scoutfj_eta[j] + np.asarray(chunk['scoutpfcand_etarel'][j], dtype=np.float64)
                    scout_phi_abs_all = wrap_phi(scoutfj_phi[j] + np.asarray(chunk['scoutpfcand_phirel'][j], dtype=np.float64))
                    scout_px_all = np.asarray(chunk['scoutpfcand_px'][j], dtype=np.float64)
                    scout_py_all = np.asarray(chunk['scoutpfcand_py'][j], dtype=np.float64)
                    scout_pt_all = np.hypot(scout_px_all, scout_py_all)

                    for cat, (off_flag_branch, scout_flag_branch) in CATEGORIES.items():
                        off_mask = np.asarray(chunk[off_flag_branch][j]) != 0
                        scout_mask = np.asarray(chunk[scout_flag_branch][j]) != 0

                        off_eta = off_eta_abs_all[off_mask]
                        off_phi = off_phi_abs_all[off_mask]
                        off_pt = off_pt_all[off_mask]
                        scout_eta = scout_eta_abs_all[scout_mask]
                        scout_phi = scout_phi_abs_all[scout_mask]
                        scout_pt = scout_pt_all[scout_mask]

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
        'binning': {'pt_edges': PT_EDGES, 'eta_edges': ETA_EDGES},
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

    with open(args.output, 'w') as fout:
        json.dump(result, fout, indent=1)
    print('Wrote', args.output)


if __name__ == '__main__':
    main()
