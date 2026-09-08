#!/usr/bin/env python3

'''
Compare the average number of jet-constituent particles per particle-pT
bin, across an arbitrary number of ntuples produced by makeNtuples.C
(e.g. to compare offline vs HLT-like reconstruction of the same jets).

Produces one separate figure/file per particle category: all, charged,
neutral, electron, muon, photon, charged hadron, neutral hadron. Splitting
by category is useful because detector-level differences (e.g. offline vs
HLT tracking) typically only affect a subset of particle types (e.g.
charged hadrons), which can otherwise be diluted in the "all particles"
view by the unaffected categories.

Usage (from any directory - output defaults to output_plots/ next to this script):
  python plot_pt.py FILE1 [FILE2 ...] [--labels LABEL1 [LABEL2 ...]] [options]

Example:
  python plot_pt.py \
      /path/to/HToBB/onlyFatJetNoPU/ntuple_0.root \
      /path/to/HToBB/onlyFatJetHLTNoPU/ntuple_0.root \
      --labels offline HLT \
      --output output_plots/plot_pt.png
'''

import os
import argparse

import numpy as np
import awkward as ak
import uproot
import matplotlib.pyplot as plt

THISDIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT = os.path.join(THISDIR, 'output_plots', 'plot_pt.png')

plt.rcParams.update({
    'font.size': 16,
    'axes.labelsize': 17,
    'xtick.labelsize': 16,
    'ytick.labelsize': 16,
    'legend.fontsize': 16,
})

# category name -> (mask function given a dict of the loaded branch arrays,
# or None for no mask; label shown in the upper-left corner of the plot)
CATEGORIES = [
    ('all',            None,                                       'All particle types'),
    ('charged',        lambda d: d['part_charge'] != 0,            'Charged particles'),
    ('neutral',        lambda d: d['part_charge'] == 0,            'Neutral particles'),
    ('electron',       lambda d: d['part_isElectron'] != 0,        'Electrons'),
    ('muon',           lambda d: d['part_isMuon'] != 0,            'Muons'),
    ('photon',         lambda d: d['part_isPhoton'] != 0,          'Photons'),
    ('charged_hadron', lambda d: d['part_isChargedHadron'] != 0,   'Charged hadrons'),
    ('neutral_hadron', lambda d: d['part_isNeutralHadron'] != 0,   'Neutral hadrons'),
]

BRANCHES = [
    'part_px', 'part_py', 'part_charge',
    'part_isElectron', 'part_isMuon', 'part_isPhoton',
    'part_isChargedHadron', 'part_isNeutralHadron',
]

# lines are colored per-file (not per-category), so the same file has the
# same color in every category's plot
LINE_COLORS = ['dodgerblue', 'darkorchid']


def load_particle_data(fname, treename='tree'):
    '''
    Read the branches needed for all categories from an ntuple.
    Returns (data, njets), where data is a dict of the raw jagged branch
    arrays (plus a 'pt' entry) and njets is the number of jets (tree
    entries) in the file.
    '''
    with uproot.open(fname) as f:
        data = f[treename].arrays(BRANCHES, library='ak')
    data = {b: data[b] for b in BRANCHES}
    data['pt'] = np.sqrt(data['part_px']**2 + data['part_py']**2)
    return data, len(data['pt'])


def average_multiplicity_per_bin(pt, njets, bin_edges):
    ### given a jagged per-jet pT array, return the average number of
    # particles per jet in each of the given pT bins, along with its
    # statistical (Poisson) uncertainty
    flat_pt = ak.to_numpy(ak.flatten(pt, axis=None))
    counts, _ = np.histogram(flat_pt, bins=bin_edges)
    if njets == 0:
        z = np.zeros_like(counts, dtype=float)
        return z, z
    return counts / njets, np.sqrt(counts) / njets


def default_label(fname):
    ### derive a readable default label from a ntuple path, e.g.
    # ".../HToBB/onlyFatJetHLT/ntuple_0.root" -> "onlyFatJetHLT"
    # (the ntuple filename itself, e.g. "ntuple_0.root", is the same
    # across Delphes-card subdirectories, so the parent directory name
    # is the informative part to default to)
    parent = os.path.basename(os.path.dirname(os.path.abspath(fname)))
    return parent if parent else fname


def main():
    parser = argparse.ArgumentParser(
        description='Plot the average number of jet-constituent particles per particle-pT bin, comparing multiple ntuples.')
    parser.add_argument('files', nargs='+',
        help='ntuple ROOT files to compare (e.g. produced by makeNtuples.C)')
    parser.add_argument('--labels', nargs='+', default=None,
        help='legend labels, one per file (default: inferred from each file\'s parent directory name)')
    parser.add_argument('--treename', default='tree',
        help='name of the tree to read (default: tree)')
    parser.add_argument('--ptmin', type=float, default=0.1,
        help='minimum particle pT in GeV for the binning (default: 0.1)')
    parser.add_argument('--ptmax', type=float, default=100.0,
        help='maximum particle pT in GeV for the binning (default: 100)')
    parser.add_argument('--nbins', type=int, default=30,
        help='number of pT bins (default: 30)')
    parser.add_argument('--linbins', action='store_true',
        help='use linearly spaced pT bins instead of the default log spacing')
    parser.add_argument('--linx', action='store_true',
        help='use a linear x-axis instead of the default log scale')
    parser.add_argument('--liny', action='store_true',
        help='use a linear y-axis instead of the default log scale')
    parser.add_argument('--info', default=None,
        help='extra info text shown in the upper left corner of every plot'
             ' (e.g. a process name like "Hbb jets"); the particle-type'
             ' label is placed just below it when this is set')
    parser.add_argument('--output', default=DEFAULT_OUTPUT,
        help='base output plot file; a separate file is written per particle'
             ' category by inserting a suffix before the extension, e.g.'
             ' output_plots/plot_pt.png -> output_plots/plot_pt_all.png,'
             ' output_plots/plot_pt_charged.png, ... (default: output_plots/plot_pt.png,'
             ' next to this script)')
    args = parser.parse_args()

    if args.labels is not None and len(args.labels) != len(args.files):
        raise ValueError('--labels must have the same length as the number of input files')
    labels = args.labels if args.labels is not None else [default_label(f) for f in args.files]

    if args.linbins:
        bin_edges = np.linspace(args.ptmin, args.ptmax, args.nbins + 1)
    else:
        bin_edges = np.logspace(np.log10(args.ptmin), np.log10(args.ptmax), args.nbins + 1)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

    # load all files once
    loaded = []
    for i, (fname, label) in enumerate(zip(args.files, labels)):
        color = LINE_COLORS[i % len(LINE_COLORS)]
        data, njets = load_particle_data(fname, treename=args.treename)
        print('{}: {} jets'.format(label, njets))
        loaded.append((label, color, data, njets))

    outbase, outext = os.path.splitext(os.path.abspath(args.output))
    if not outext:
        outext = '.png'
    outdir = os.path.dirname(outbase)
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir)

    for category, mask_fn, category_label in CATEGORIES:
        fig, ax = plt.subplots(figsize=(8, 6))

        for label, color, data, njets in loaded:
            if njets == 0:
                print('  WARNING: no jets found for {}, skipping'.format(label))
                continue
            pt = data['pt'][mask_fn(data)] if mask_fn is not None else data['pt']
            avg_mult, avg_mult_err = average_multiplicity_per_bin(pt, njets, bin_edges)
            ax.step(bin_centers, avg_mult, where='mid', color=color, linewidth=3,
                    label='{} ({} jets)'.format(label, njets))
            lower = np.clip(avg_mult - avg_mult_err, a_min=0, a_max=None)
            upper = avg_mult + avg_mult_err
            ax.fill_between(bin_centers, lower, upper, step='mid', color=color, alpha=0.3, linewidth=0)

        ax.set_xlabel(r'Particle $p_{T}$ [GeV]')
        ax.set_ylabel('Average number of particles / jet / bin')
        if not args.linx:
            ax.set_xscale('log')
        if not args.liny:
            ax.set_yscale('log')
        ax.minorticks_on()
        ax.grid(True, which='major', linestyle='-', alpha=0.4)
        ax.grid(True, which='minor', linestyle=':', alpha=0.25)
        if args.info:
            ax.text(0.03, 0.97, args.info, transform=ax.transAxes,
                    ha='left', va='top', fontsize=16)
            ax.text(0.03, 0.90, category_label, transform=ax.transAxes,
                    ha='left', va='top', fontsize=16)
        else:
            ax.text(0.03, 0.97, category_label, transform=ax.transAxes,
                    ha='left', va='top', fontsize=16)
        ax.legend()
        fig.tight_layout()

        outpath = '{}_{}{}'.format(outbase, category, outext)
        fig.savefig(outpath, dpi=150)
        plt.close(fig)
        print('Saved plot to {}'.format(outpath))


if __name__ == '__main__':
    main()
