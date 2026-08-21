#!/usr/bin/env python3

'''
Plot the mean per-jet particle-flow composition (energy fraction of
electrons, muons, charged hadrons, photons, neutral hadrons, and any
unclassified constituents) versus jet pT, as horizontal stacked bar
charts - one panel per input ntuple, arranged side by side in the order
the files are given on the command line.

Usage:
  python plot_composition.py FILE1 [FILE2 ...] [--labels LABEL1 [LABEL2 ...]] [options]

Example:
  python plot_composition.py \
      /path/to/HToBB/onlyFatJetNoPU/ntuple_0.root \
      /path/to/HToBB/onlyFatJetHLTNoPU/ntuple_0.root \
      --labels Offline HLT \
      --output testing/plot_composition.png
'''

import os
import argparse

import numpy as np
import awkward as ak
import uproot
import matplotlib.pyplot as plt

plt.rcParams.update({
    'font.size': 14,
    'axes.labelsize': 15,
    'xtick.labelsize': 13,
    'ytick.labelsize': 13,
    'legend.fontsize': 13,
})

# category name -> (mask function given a dict of the loaded branch arrays,
# legend label, bar color); order determines stacking order (left to right)
CATEGORIES = [
    ('electron',       lambda d: d['part_isElectron'] != 0,       'Electron',       'crimson'),
    ('muon',           lambda d: d['part_isMuon'] != 0,           'Muon',           'rebeccapurple'),
    ('charged_hadron', lambda d: d['part_isChargedHadron'] != 0,  'Charged hadron', 'darkorange'),
    ('photon',         lambda d: d['part_isPhoton'] != 0,         'Photon',         'goldenrod'),
    ('neutral_hadron', lambda d: d['part_isNeutralHadron'] != 0,  'Neutral hadron', 'teal'),
    ('unclassified',   None,                                      'Unclassified',   'gray'),
]

BRANCHES = [
    'jet_pt', 'part_energy',
    'part_isElectron', 'part_isMuon', 'part_isPhoton',
    'part_isChargedHadron', 'part_isNeutralHadron',
]

DEFAULT_PT_BINS = [200, 250, 300, 400, 500, 650, 800, 1000, 1500, 2000, 3000, 5000]


def load_composition_data(fname, treename='tree'):
    ### read the branches needed to compute per-jet composition fractions
    with uproot.open(fname) as f:
        arrays = f[treename].arrays(BRANCHES, library='ak')
    data = {b: arrays[b] for b in BRANCHES}

    total_energy = ak.sum(data['part_energy'], axis=1)

    classified = ak.zeros_like(data['part_isElectron'], dtype=np.int32)
    fracs = {}
    for name, mask_fn, _, _ in CATEGORIES:
        if mask_fn is None:
            continue
        mask = ak.values_astype(mask_fn(data), np.float32)
        classified = classified + ak.values_astype(mask_fn(data), np.int32)
        fracs[name] = ak.to_numpy(ak.sum(mask * data['part_energy'], axis=1) / total_energy)
    fracs['unclassified'] = ak.to_numpy(
        ak.sum(ak.values_astype(classified == 0, np.float32) * data['part_energy'], axis=1) / total_energy)

    jet_pt = ak.to_numpy(data['jet_pt'])
    return jet_pt, fracs


def default_label(fname):
    ### derive a readable default label from a ntuple path, e.g.
    # ".../HToBB/onlyFatJetHLT/ntuple_0.root" -> "onlyFatJetHLT"
    parent = os.path.basename(os.path.dirname(os.path.abspath(fname)))
    return parent if parent else fname


def format_bin_label(lo, hi):
    fmt = lambda v: '{:g}'.format(v)
    return '{}–{}'.format(fmt(lo), fmt(hi))


def main():
    parser = argparse.ArgumentParser(
        description='Plot mean per-jet particle-flow composition vs jet pT, one panel per input ntuple.')
    parser.add_argument('files', nargs='+',
        help='ntuple ROOT files to compare (e.g. produced by makeNtuples.C); panels are'
             ' arranged left to right in the order given here')
    parser.add_argument('--labels', nargs='+', default=None,
        help='panel titles, one per file (default: inferred from each file\'s parent directory name)')
    parser.add_argument('--treename', default='tree',
        help='name of the tree to read (default: tree)')
    parser.add_argument('--ptbins', default=None,
        help='comma-separated jet pT bin edges in GeV'
             ' (default: {})'.format(','.join(str(b) for b in DEFAULT_PT_BINS)))
    parser.add_argument('--label-threshold', type=float, default=5.0,
        help='minimum segment size in %% for a percentage label to be drawn inside it (default: 5)')
    parser.add_argument('--output', default='testing/plot_composition.png',
        help='output plot file (default: testing/plot_composition.png)')
    args = parser.parse_args()

    if args.labels is not None and len(args.labels) != len(args.files):
        raise ValueError('--labels must have the same length as the number of input files')
    labels = args.labels if args.labels is not None else [default_label(f) for f in args.files]

    pt_bins = [float(x) for x in args.ptbins.split(',')] if args.ptbins else DEFAULT_PT_BINS
    nbins = len(pt_bins) - 1
    bin_labels = [format_bin_label(pt_bins[i], pt_bins[i + 1]) for i in range(nbins)]
    y = np.arange(nbins)

    fig, axes = plt.subplots(1, len(args.files), figsize=(6.5 * len(args.files), 0.55 * nbins + 2),
                              sharey=True)
    if len(args.files) == 1:
        axes = [axes]

    for ax, fname, label in zip(axes, args.files, labels):
        jet_pt, fracs = load_composition_data(fname, treename=args.treename)

        # mean per-jet composition (%) in each pT bin, per category
        binned = {name: np.full(nbins, np.nan) for name, _, _, _ in CATEGORIES}
        njets_per_bin = np.zeros(nbins, dtype=int)
        for i in range(nbins):
            lo, hi = pt_bins[i], pt_bins[i + 1]
            in_bin = (jet_pt >= lo) & (jet_pt < hi)
            njets_per_bin[i] = np.count_nonzero(in_bin)
            if njets_per_bin[i] == 0:
                continue
            for name, _, _, _ in CATEGORIES:
                binned[name][i] = 100.0 * np.mean(fracs[name][in_bin])

        left = np.zeros(nbins)
        for name, _, cat_label, color in CATEGORIES:
            vals = np.nan_to_num(binned[name])
            ax.barh(y, vals, left=left, height=0.7, color=color, label=cat_label)
            for i in range(nbins):
                if vals[i] >= args.label_threshold:
                    ax.text(left[i] + vals[i] / 2, y[i], '{:.0f}%'.format(vals[i]),
                            ha='center', va='center', color='white', fontweight='bold', fontsize=12)
            left += vals

        ax.set_title(label, fontweight='bold', fontsize=17)
        ax.set_xlabel('Mean per-jet composition [%]')
        ax.set_xlim(0, 100)
        ax.xaxis.grid(True, alpha=0.3)
        ax.set_axisbelow(True)

    axes[0].set_yticks(y)
    axes[0].set_yticklabels(bin_labels)
    axes[0].set_ylabel(r'Jet $p_{T}$ bin [GeV]')
    axes[0].invert_yaxis()

    handles, legend_labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc='lower center', ncol=3,
               bbox_to_anchor=(0.5, -0.09), frameon=False)

    fig.tight_layout()

    outdir = os.path.dirname(os.path.abspath(args.output))
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir)
    fig.savefig(args.output, dpi=150, bbox_inches='tight')
    print('Saved plot to {}'.format(args.output))


if __name__ == '__main__':
    main()
