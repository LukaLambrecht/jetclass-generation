#!/usr/bin/env python3

'''
Quick, standalone look at whole-jet pT for the same paired offline/scouting
QCD data that derive_curves.py measures (see hlteff/README.md "Data
source") - motivated by the 10M-jet HLT-card dataset produced yesterday
showing only 50-80% (outliers down to 30%) as many HLT jets as offline
jets, well beyond what simple pT>200 GeV migration alone should cause.

This does NOT reproduce derive_curves.py's own JetEnergyScalePUPPIAK8
measurement (that's `jes['scout_over_offline_ratio']` in curves_qcd.json,
already visualized in hlteff/plots/scale_jetEnergyPUPPIAK8.png, a MEAN-only
curve on the coarse JET_PT_EDGES grid, folded straight into the generated
HLT card). This script instead looks at the raw ingredients directly and
adds the spread (not just the mean) of the offline/HLT pT ratio, to see
whether the ratio's spread alone (jets scattering below whatever pT cut is
applied) is large enough to plausibly explain a 20-70% jet-count deficit,
or whether that deficit needs a different explanation (e.g. genuine
reconstruction failures, not just kinematic migration across a threshold).

Selection matches derive_curves.py's own exactly: `fj_isQCD == 1` - the
same jets the HLT card's data-driven corrections were themselves derived
from, per the request that motivated this script (check the input data,
not a downstream simulation of it).

Only three flat branches are read (fj_pt, fj_eta, scoutfj_pt - no
per-particle branches, no matching) - much lighter than derive_curves.py's
full pipeline, so reading many more jets than its own --max-jets default
is still fast; the default here is deliberately smaller anyway since jet-pT
conclusions don't need the same statistics as the fine per-particle
efficiency/resolution grid.

Produces two figures (house style matches plot_curves.py: one panel per
|eta| bin, from binning.py's own ETA_EDGES/JET_PT_EDGES):
  jet_pt_distributions.png - offline (fj_pt) vs HLT (scoutfj_pt) pT spectra,
    overlaid, log-log.
  jet_pt_ratio.png - mean +/- std of scoutfj_pt/fj_pt, binned by fj_pt
    (JET_PT_EDGES) - the actual "how much does HLT pT scatter relative to
    offline, and by how much" answer; also printed as a table to stdout.

Usage:
  python hlteff/exploration/plot_jet_pt.py [--input-dir DIR] [--n-files N]
                                            [--max-jets N] [--outdir DIR]
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
from binning import ETA_EDGES, JET_PT_EDGES, n_eta_bins, n_jet_pt_bins, jet_pt_bin_index, eta_bin_index
from derive_curves import DEFAULT_INPUT_DIR

DEFAULT_OUTDIR = os.path.join(EXPLORATION_DIR, 'plots')

BRANCHES = ['fj_isQCD', 'fj_eta', 'fj_pt', 'scoutfj_pt']

OFFLINE_COLOR = 'dodgerblue'
HLT_COLOR = 'darkorchid'

plt.rcParams.update({
    'font.size': 13,
    'axes.labelsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 11,
})


def jet_pt_bin_center(i):
    ### geometric mean of the bin edges, same log-axis convention as
    # binning.py's own pt_bin_center() (JET_PT_EDGES has no such helper there)
    return (JET_PT_EDGES[i] * JET_PT_EDGES[i + 1]) ** 0.5


def new_panel_figure(ne):
    fig, axes = plt.subplots(1, ne, figsize=(7 * ne, 5.5))
    if ne == 1:
        axes = [axes]
    return fig, axes


def finish_panel(ax, ie, xlabel, logx=True, logy=False):
    if logx:
        ax.set_xscale('log')
    if logy:
        ax.set_yscale('log')
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


def read_jets(input_dir, n_files, max_jets):
    files = sorted(glob.glob(os.path.join(input_dir, 'dnnTuples_nanov15_*.root')))[:n_files]
    if not files:
        raise SystemExit('no dnnTuples_nanov15_*.root files found in {}'.format(input_dir))
    print('Reading {} file(s):'.format(len(files)))
    for fn in files:
        print('  ', fn)

    fj_pt_chunks, fj_eta_chunks, scoutfj_pt_chunks = [], [], []
    n_read = 0
    for fn in files:
        if n_read >= max_jets:
            break
        with uproot.open(fn) as f:
            tree = f['tree']
            for chunk in tree.iterate(BRANCHES, step_size=50000, library='ak'):
                chunk = chunk[chunk['fj_isQCD'] == 1]
                if len(chunk) == 0:
                    continue
                fj_pt_chunks.append(ak.to_numpy(chunk['fj_pt']))
                fj_eta_chunks.append(ak.to_numpy(chunk['fj_eta']))
                scoutfj_pt_chunks.append(ak.to_numpy(chunk['scoutfj_pt']))
                n_read += len(chunk)
                if n_read >= max_jets:
                    break

    fj_pt = np.concatenate(fj_pt_chunks)[:max_jets]
    fj_eta = np.concatenate(fj_eta_chunks)[:max_jets]
    scoutfj_pt = np.concatenate(scoutfj_pt_chunks)[:max_jets]
    print('Read {} QCD jets (fj_isQCD==1).'.format(len(fj_pt)))
    return fj_pt, fj_eta, scoutfj_pt


def plot_distributions(fj_pt, fj_eta, scoutfj_pt, outdir):
    ne = n_eta_bins()
    lo = max(1.0, min(np.nanmin(fj_pt), np.nanmin(scoutfj_pt[np.isfinite(scoutfj_pt) & (scoutfj_pt > 0)])))
    hi = max(np.nanmax(fj_pt), np.nanmax(scoutfj_pt[np.isfinite(scoutfj_pt)]))
    bins = np.logspace(np.log10(lo), np.log10(hi), 60)

    fig, axes = new_panel_figure(ne)
    for ie, ax in enumerate(axes):
        sel = np.abs(fj_eta) >= ETA_EDGES[ie]
        sel &= np.abs(fj_eta) < ETA_EDGES[ie + 1]
        ax.hist(fj_pt[sel], bins=bins, histtype='step', linewidth=2, color=OFFLINE_COLOR,
                label='offline (fj_pt), N={}'.format(sel.sum()))
        scout = scoutfj_pt[sel]
        scout = scout[np.isfinite(scout) & (scout > 0)]
        ax.hist(scout, bins=bins, histtype='step', linewidth=2, color=HLT_COLOR,
                label='HLT (scoutfj_pt), N={}'.format(len(scout)))
        finish_panel(ax, ie, r'Jet $p_{T}$ [GeV]', logy=True)

    axes[0].set_ylabel('Jets')
    fig.suptitle('Offline vs HLT jet $p_{T}$ (QCD, fj_isQCD==1)', fontsize=15)
    save(fig, outdir, 'jet_pt_distributions.png')


def plot_ratio(fj_pt, fj_eta, scoutfj_pt, outdir, min_count=50):
    ne, npt = n_eta_bins(), n_jet_pt_bins()
    good = np.isfinite(fj_pt) & (fj_pt > 0) & np.isfinite(scoutfj_pt) & (scoutfj_pt > 0)

    print()
    header = '{:<16}{:>14}{:>10}{:>10}{:>10}'.format('|eta| bin', 'fj_pt bin [GeV]', 'n_jets', 'mean', 'std')
    print(header)
    print('-' * len(header))

    fig, axes = new_panel_figure(ne)
    for ie, ax in enumerate(axes):
        eta_sel = good & (np.abs(fj_eta) >= ETA_EDGES[ie]) & (np.abs(fj_eta) < ETA_EDGES[ie + 1])

        centers, means, stds, counts = [], [], [], []
        for ip in range(npt):
            pt_sel = eta_sel & (fj_pt >= JET_PT_EDGES[ip]) & (fj_pt < JET_PT_EDGES[ip + 1])
            n = int(pt_sel.sum())
            centers.append(jet_pt_bin_center(ip))
            if n < min_count:
                means.append(np.nan)
                stds.append(np.nan)
            else:
                ratio = scoutfj_pt[pt_sel] / fj_pt[pt_sel]
                means.append(float(np.mean(ratio)))
                stds.append(float(np.std(ratio)))
            counts.append(n)
            print('{:<16}{:>14}{:>10}{:>10}{:>10}'.format(
                '{:g}-{:g}'.format(ETA_EDGES[ie], ETA_EDGES[ie + 1]),
                '{:g}-{:g}'.format(JET_PT_EDGES[ip], JET_PT_EDGES[ip + 1]),
                n,
                '{:.3f}'.format(means[-1]) if np.isfinite(means[-1]) else 'n/a',
                '{:.3f}'.format(stds[-1]) if np.isfinite(stds[-1]) else 'n/a'))

        centers = np.array(centers)
        means = np.array(means)
        stds = np.array(stds)
        ax.errorbar(centers, means, yerr=stds, fmt='o-', color=HLT_COLOR, linewidth=2,
                     markersize=5, capsize=3, label=r'mean $\pm$ std of $p_T^{HLT}/p_T^{offline}$')
        for ip in range(npt):
            if counts[ip] < min_count:
                ax.axvspan(JET_PT_EDGES[ip], JET_PT_EDGES[ip + 1], color='gray', alpha=0.08, linewidth=0)

        ax.axhline(1.0, color='black', linewidth=0.8, linestyle='-', alpha=0.3)
        finish_panel(ax, ie, r'Offline jet $p_{T}$ [GeV]')

    axes[0].set_ylabel(r'$p_{T}^{HLT} / p_{T}^{offline}$')
    fig.suptitle('HLT/offline jet $p_{T}$ ratio (QCD, fj_isQCD==1)', fontsize=15)
    save(fig, outdir, 'jet_pt_ratio.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input-dir', default=DEFAULT_INPUT_DIR,
        help='directory of dnnTuples_nanov15_*.root files (default: QCD training sample,'
             ' same as derive_curves.py)')
    parser.add_argument('--n-files', type=int, default=3,
        help='number of files to read from --input-dir, in sorted order (default: 3)')
    parser.add_argument('--max-jets', type=int, default=300000,
        help='stop after reading this many QCD jets total (default: 300000) - only'
             ' fj_pt/fj_eta/scoutfj_pt are read (no per-particle branches/matching), so'
             ' this is fast even at a few hundred thousand jets')
    parser.add_argument('--min-count', type=int, default=50,
        help='minimum jets in a (eta, pT) bin to plot a ratio point for it (default: 50) -'
             ' thin bins are shaded gray instead')
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR,
        help='directory to write plots into (default: hlteff/exploration/plots)')
    args = parser.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    fj_pt, fj_eta, scoutfj_pt = read_jets(args.input_dir, args.n_files, args.max_jets)

    plot_distributions(fj_pt, fj_eta, scoutfj_pt, args.outdir)
    plot_ratio(fj_pt, fj_eta, scoutfj_pt, args.outdir, min_count=args.min_count)


if __name__ == '__main__':
    main()
