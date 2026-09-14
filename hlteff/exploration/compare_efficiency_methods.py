#!/usr/bin/env python3

'''
Compares two different ways of estimating the offline-vs-HLT charged-hadron
tracking efficiency from the same paired QCD ntuples derive_curves.py uses
(see hlteff/README.md "Data source") - motivated by the suspicion that the
matching-based method (derive_curves.py's own, via match_jet() with
--dr-max) might be *understating* the true HLT efficiency: a genuine HLT
track that migrates slightly in (eta,phi) relative to its offline
counterpart (a real, if modest, effect - see README "Notable findings" on
pT resolution) could fall outside the dR window and register as "no match"
even though the particle WAS reconstructed, undercounting efficiency.

Two methods, computed from the SAME read of the SAME jets:

- "matching" (derive_curves.py's own method): per jet, offline and scouting
  charged-hadron candidates are greedily matched within --dr-max (nearest
  deltaR first). efficiency_matching[eta,pt] = n_matched / n_offline, where
  both indices are the OFFLINE candidate's own (eta,pt) bin. Requires
  geometric pairing to work correctly; sensitive to --dr-max and to any
  systematic eta/phi shift between the two reconstructions.
- "counting" (this script's own addition, per the request that motivated
  it): no per-particle pairing at all. Every offline charged-hadron
  candidate is binned by its own (eta,pt) into n_offline[eta,pt]; every
  scouting charged-hadron candidate is independently binned by ITS OWN
  (eta,pt) into n_scout[eta,pt] - completely unpaired, just two marginal
  counts. efficiency_counting[eta,pt] = n_scout / n_offline. This can only
  work because it's the SAME underlying set of jets on both sides (the
  README's own "Data source" - offline/scouting rows are two independent
  reconstructions of the identical event) and because the Delphes
  ChargedHadronTrackingEfficiency module this measurement feeds is itself
  only ever a function of (pT, eta) - a genuinely-reconstructed particle's
  own (pT, eta) is what determines its simulated fate either way, so a
  particle-count ratio per bin is a valid alternate estimator of exactly
  the same physical quantity dR-matching tries to measure, without dR
  itself entering at all. The tradeoff: this can't tell a genuine
  HLT-reconstructed track from an unrelated fake landing in the same bin
  (dR-matching's own protection against that), so a real difference
  between the two methods could go either way - matching missing genuine
  migrated tracks (undercounting) vs counting picking up unrelated fakes
  (overcounting) - the comparison itself is the diagnostic.

n_offline (the shared denominator) is identical between the two methods by
construction - matching only changes what counts as "found" in the
numerator, so it's read once and reused, not recomputed twice.

Produces one figure (efficiency_comparison_chargedHadron.png, one panel per
|eta| bin, house style matching plot_curves.py/plot_jet_pt.py) with both
curves overlaid, plus a full (eta, pT bin) -> (n_offline, n_matched,
n_scout, eff_matching, eff_counting) table printed to stdout.

Usage:
  python hlteff/exploration/compare_efficiency_methods.py [--input-dir DIR]
      [--n-files N] [--max-jets N] [--dr-max DR] [--outdir DIR]
'''

import os
import sys
import glob
import argparse

import numpy as np
import awkward as ak
import uproot
import matplotlib.pyplot as plt

EXPLORATION_DIR = os.path.dirname(os.path.abspath(__file__))
HLTEFF_DIR = os.path.dirname(EXPLORATION_DIR)
sys.path.insert(0, HLTEFF_DIR)
from binning import PT_EDGES, ETA_EDGES, n_pt_bins, n_eta_bins, pt_bin_index, eta_bin_index, pt_bin_center
from derive_curves import DEFAULT_INPUT_DIR, wrap_phi, match_jet

DEFAULT_OUTDIR = os.path.join(EXPLORATION_DIR, 'plots')

BRANCHES = [
    'fj_isQCD', 'fj_eta', 'fj_phi',
    'scoutfj_eta', 'scoutfj_phi',
    'cpfcandlt_etarel', 'cpfcandlt_phirel', 'cpfcandlt_px', 'cpfcandlt_py', 'cpfcandlt_isChargedHad',
    'scoutpfcand_etarel', 'scoutpfcand_phirel', 'scoutpfcand_px', 'scoutpfcand_py', 'scoutpfcand_isChargedHad',
]

MATCHING_COLOR = 'darkorchid'
COUNTING_COLOR = 'darkorange'

plt.rcParams.update({
    'font.size': 13,
    'axes.labelsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 11,
})


def new_panel_figure(ne):
    fig, axes = plt.subplots(1, ne, figsize=(7 * ne, 5.5), sharey=True)
    if ne == 1:
        axes = [axes]
    return fig, axes


def finish_panel(ax, ie, xlabel, logx=True):
    if logx:
        ax.set_xscale('log')
    ax.set_xlabel(xlabel)
    ax.minorticks_on()
    ax.grid(True, which='major', linestyle='-', alpha=0.4)
    ax.grid(True, which='minor', linestyle=':', alpha=0.2)
    ax.set_title(r'${:g} < |\eta| \leq {:g}$'.format(ETA_EDGES[ie], ETA_EDGES[ie + 1]), fontsize=13)
    ax.legend(loc='best')


def save(fig, outdir, name):
    outpath = os.path.join(outdir, name)
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print('Saved', outpath)


def step_edges(edges, values):
    x = list(edges)
    y = list(values) + [values[-1]]
    return x, y


def measure(input_dir, n_files, max_jets, dr_max, chunk_size=20000):
    files = sorted(glob.glob(os.path.join(input_dir, 'dnnTuples_nanov15_*.root')))[:n_files]
    if not files:
        raise SystemExit('no dnnTuples_nanov15_*.root files found in {}'.format(input_dir))
    print('Reading {} file(s):'.format(len(files)))
    for fn in files:
        print('  ', fn)

    ne, npt = n_eta_bins(), n_pt_bins()
    n_offline = np.zeros((ne, npt), dtype=np.int64)
    n_matched = np.zeros((ne, npt), dtype=np.int64)
    n_scout = np.zeros((ne, npt), dtype=np.int64)

    n_jets_done = 0
    for fn in files:
        if n_jets_done >= max_jets:
            break
        with uproot.open(fn) as f:
            tree = f['tree']
            for chunk in tree.iterate(BRANCHES, step_size=chunk_size, library='ak'):
                chunk = chunk[chunk['fj_isQCD'] == 1]
                n_jets_chunk = len(chunk)
                if n_jets_chunk == 0:
                    continue

                fj_eta = ak.to_numpy(chunk['fj_eta'])
                fj_phi = ak.to_numpy(chunk['fj_phi'])
                scoutfj_eta = ak.to_numpy(chunk['scoutfj_eta'])
                scoutfj_phi = ak.to_numpy(chunk['scoutfj_phi'])

                for j in range(n_jets_chunk):
                    off_mask = np.asarray(chunk['cpfcandlt_isChargedHad'][j]) != 0
                    off_eta = fj_eta[j] + np.asarray(chunk['cpfcandlt_etarel'][j], dtype=np.float64)[off_mask]
                    off_phi = wrap_phi(fj_phi[j] + np.asarray(chunk['cpfcandlt_phirel'][j], dtype=np.float64)[off_mask])
                    off_px = np.asarray(chunk['cpfcandlt_px'][j], dtype=np.float64)[off_mask]
                    off_py = np.asarray(chunk['cpfcandlt_py'][j], dtype=np.float64)[off_mask]
                    off_pt = np.hypot(off_px, off_py)

                    scout_mask = np.asarray(chunk['scoutpfcand_isChargedHad'][j]) != 0
                    scout_eta = scoutfj_eta[j] + np.asarray(chunk['scoutpfcand_etarel'][j], dtype=np.float64)[scout_mask]
                    scout_phi = wrap_phi(scoutfj_phi[j] + np.asarray(chunk['scoutpfcand_phirel'][j], dtype=np.float64)[scout_mask])
                    scout_px = np.asarray(chunk['scoutpfcand_px'][j], dtype=np.float64)[scout_mask]
                    scout_py = np.asarray(chunk['scoutpfcand_py'][j], dtype=np.float64)[scout_mask]
                    scout_pt = np.hypot(scout_px, scout_py)

                    # "counting": every scouting candidate binned by ITS OWN
                    # (eta,pt), completely independent of the offline side -
                    # no pairing, no dR at all (see module docstring)
                    for k in range(len(scout_pt)):
                        ie = eta_bin_index(abs(scout_eta[k]))
                        ip = pt_bin_index(scout_pt[k])
                        if ie is None or ip is None:
                            continue
                        n_scout[ie, ip] += 1

                    # "matching": derive_curves.py's own method, reused as-is
                    match = match_jet(off_eta, off_phi, scout_eta, scout_phi, dr_max)
                    for k in range(len(off_pt)):
                        ie = eta_bin_index(abs(off_eta[k]))
                        ip = pt_bin_index(off_pt[k])
                        if ie is None or ip is None:
                            continue
                        n_offline[ie, ip] += 1
                        if match[k] >= 0:
                            n_matched[ie, ip] += 1

                n_jets_done += n_jets_chunk
                print('  processed {} jets'.format(n_jets_done))
                if n_jets_done >= max_jets:
                    break

    print('Total jets processed: {}'.format(n_jets_done))
    return n_offline, n_matched, n_scout


def print_table(n_offline, n_matched, n_scout):
    ne, npt = n_eta_bins(), n_pt_bins()
    header = '{:<14}{:<16}{:>10}{:>10}{:>10}{:>14}{:>14}'.format(
        '|eta| bin', 'pT bin [GeV]', 'n_off', 'n_match', 'n_scout', 'eff_match', 'eff_count')
    print()
    print(header)
    print('-' * len(header))
    for ie in range(ne):
        for ip in range(npt):
            noff = int(n_offline[ie, ip])
            nmat = int(n_matched[ie, ip])
            nsc = int(n_scout[ie, ip])
            eff_m = nmat / noff if noff > 0 else float('nan')
            eff_c = nsc / noff if noff > 0 else float('nan')
            print('{:<14}{:<16}{:>10}{:>10}{:>10}{:>14}{:>14}'.format(
                '{:g}-{:g}'.format(ETA_EDGES[ie], ETA_EDGES[ie + 1]),
                '{:g}-{:g}'.format(PT_EDGES[ip], PT_EDGES[ip + 1]),
                noff, nmat, nsc,
                '{:.3f}'.format(eff_m) if noff > 0 else 'n/a',
                '{:.3f}'.format(eff_c) if noff > 0 else 'n/a'))


def plot_comparison(n_offline, n_matched, n_scout, outdir, min_count=200):
    ne, npt = n_eta_bins(), n_pt_bins()
    pt_centers = np.array([pt_bin_center(ip) for ip in range(npt)])

    with np.errstate(invalid='ignore', divide='ignore'):
        eff_matching = n_matched / n_offline
        eff_counting = n_scout / n_offline

    fig, axes = new_panel_figure(ne)
    for ie, ax in enumerate(axes):
        em = eff_matching[ie]
        ec = eff_counting[ie]
        rx, ry_m = step_edges(PT_EDGES, [v if np.isfinite(v) else np.nan for v in em])
        _, ry_c = step_edges(PT_EDGES, [v if np.isfinite(v) else np.nan for v in ec])
        ax.step(rx, ry_m, where='post', color=MATCHING_COLOR, linewidth=2.5,
                label=r'matching ($n_{matched}/n_{offline}$)')
        ax.step(rx, ry_c, where='post', color=COUNTING_COLOR, linewidth=2.5, linestyle='--',
                label=r'counting ($n_{scout}/n_{offline}$, unpaired)')
        for ip in range(npt):
            if n_offline[ie, ip] < min_count:
                ax.axvspan(PT_EDGES[ip], PT_EDGES[ip + 1], color='gray', alpha=0.08, linewidth=0)

        ax.set_ylim(0, 1.3)
        ax.axhline(1.0, color='black', linewidth=0.8, linestyle='-', alpha=0.3)
        finish_panel(ax, ie, r'Particle $p_{T}$ [GeV]')

    axes[0].set_ylabel('Charged hadron efficiency')
    fig.suptitle('Offline-vs-HLT charged hadron efficiency: matching vs counting (QCD)', fontsize=15)
    save(fig, outdir, 'efficiency_comparison_chargedHadron.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input-dir', default=DEFAULT_INPUT_DIR,
        help='directory of dnnTuples_nanov15_*.root files (default: QCD training sample,'
             ' same as derive_curves.py)')
    parser.add_argument('--n-files', type=int, default=2,
        help='number of files to read from --input-dir, in sorted order (default: 2,'
             ' matching derive_curves.py\'s own default)')
    parser.add_argument('--max-jets', type=int, default=150000,
        help='stop after processing this many jets total (default: 150000, matching'
             ' derive_curves.py\'s own default)')
    parser.add_argument('--dr-max', type=float, default=0.03,
        help='max deltaR for the matching method (default: 0.03, same default as'
             ' derive_curves.py - does not affect the counting method at all)')
    parser.add_argument('--min-count', type=int, default=200,
        help='minimum n_offline in a bin to plot it un-shaded (default: 200)')
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR,
        help='directory to write plots into (default: hlteff/exploration/plots)')
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    n_offline, n_matched, n_scout = measure(args.input_dir, args.n_files, args.max_jets, args.dr_max)
    print_table(n_offline, n_matched, n_scout)
    plot_comparison(n_offline, n_matched, n_scout, args.outdir, min_count=args.min_count)


if __name__ == '__main__':
    main()
