#!/usr/bin/env python3

'''
Compare the average number of jet-constituent particles per particle-pT
bin between OFFLINE and HLT reconstruction of the SAME jets. Reads EITHER
of two schemas transparently (see ntuple_io.py for the full description
of each, and how they're normalized onto the same part_*/hlt_part_*
naming used below):

  - our own PAIRED ntuples (delphes_analyzers/makeNtuplesPaired.C): one
    row per selected offline jet, carrying its own part_* branches plus
    its matched HLT jet's hlt_part_* branches in the SAME entry
    (hlt_matched says whether a match was found at all - for an unmatched
    row, every hlt_part_* vector is simply empty, not zero-filled).

  - the real FullSim/scouting reference dataset this pipeline is trying to
    mimic (see hlteff/README.md's "Data source") - same one-entry-two-
    collections structure (every row already IS a matched pair there, see
    ntuple_io.py), letting the exact same comparison be made directly
    against real detector data instead of only Delphes-vs-Delphes.

Pass either kind of ntuple as `files` - which schema it is is detected
automatically (see ntuple_io.detect_schema()) and needs no flag.

Both sides are normalized by the SAME denominator - the total number of
offline-selected jets (rows) in the file(s) - not just the HLT-matched
subset. This is deliberate: it makes the "average particles / jet" curves
directly, honestly comparable in absolute terms, including the effect of
jets HLT lost entirely (an unmatched row's empty hlt_part_* vectors
contribute zero to the HLT curve automatically, no separate masking
needed - exactly like a genuinely-empty HLT jet would).

Produces one separate figure/file per particle category: all, charged,
neutral, electron, muon, photon, charged hadron, neutral hadron. Splitting
by category is useful because detector-level differences (e.g. offline vs
HLT tracking) typically only affect a subset of particle types (e.g.
charged hadrons), which can otherwise be diluted in the "all particles"
view by the unaffected categories.

Usage (from any directory - output defaults to output_plots/ next to this script):
  python plot_pt.py FILE_OR_GLOB [FILE_OR_GLOB ...] [options]

`files` are every paired ntuple belonging to ONE production (e.g. all of a
process' condor-job ntuple_*.root under one card-pair directory) - pass a
glob (quoted, so this script expands it, not the shell) or a full file
list; they're all concatenated (via uproot.concatenate) before plotting,
not looped over as separate series like the old (pre-paired-format)
version of this script did.

Examples:
  python plot_pt.py \\
      '/eos/user/l/llambrec/jetclass/output_jetclass2_5M/jetclass2/train_higgs2p/onlyFatJet+onlyFatJetHLT/ntuple_*.root' \\
      --info train_higgs2p --output output_plots/plot_pt_train_higgs2p.png

  # same, but against the real FullSim/scouting reference dataset
  python plot_pt.py \\
      '/eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/H0HpHm_mixed_new/dnnTuples_nanov15_*.root' \\
      --info H0HpHm_mixed_new --output output_plots/plot_pt_fullsim_h0hphm.png
'''

import os
import sys
import glob
import argparse

import numpy as np
import awkward as ak
import matplotlib.pyplot as plt

THISDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(THISDIR))  # validation/ - for ntuple_io
import ntuple_io as nio

DEFAULT_OUTPUT = os.path.join(THISDIR, 'output_plots', 'plot_pt.png')

plt.rcParams.update({
    'font.size': 16,
    'axes.labelsize': 17,
    'xtick.labelsize': 16,
    'ytick.labelsize': 16,
    'legend.fontsize': 16,
})

# category name -> (mask function given a dict of the loaded branch arrays
# and the "part_"/"hlt_part_" prefix to apply it to, or None for no mask; label
# shown in the upper-left corner of the plot)
CATEGORIES = [
    ('all',            None,                                            'All particle types'),
    ('charged',        lambda d, p: d[p + 'charge'] != 0,                'Charged particles'),
    ('neutral',        lambda d, p: d[p + 'charge'] == 0,                'Neutral particles'),
    ('electron',       lambda d, p: d[p + 'isElectron'] != 0,            'Electrons'),
    ('muon',           lambda d, p: d[p + 'isMuon'] != 0,                'Muons'),
    ('photon',         lambda d, p: d[p + 'isPhoton'] != 0,              'Photons'),
    ('charged_hadron', lambda d, p: d[p + 'isChargedHadron'] != 0,       'Charged hadrons'),
    ('neutral_hadron', lambda d, p: d[p + 'isNeutralHadron'] != 0,       'Neutral hadrons'),
]

# per-particle fields CATEGORIES actually needs (plus px/py for pT itself) - passed to
# ntuple_io.load_particles()'s own `suffixes` filter so it never reads/builds 'energy'
# (unused here), the main cost of that function
SUFFIXES = ['px', 'py', 'charge', 'isElectron', 'isMuon', 'isPhoton', 'isChargedHadron', 'isNeutralHadron']

# the two sides this script knows how to plot, in the order they're drawn -
# see load_data() for which of them a given input actually has (an
# offline-only "ours" production, e.g. output_jetclass2_5M's old single-card
# form, has no HLT side at all; every fullsim input and every paired "ours"
# production has both)
ALL_SIDES = [('part_', 'Offline', 'dodgerblue'), ('hlt_part_', 'HLT', 'darkorchid')]


def expand_files(patterns):
    '''Glob-expand each pattern (quote globs on the command line so THIS
    expands them, not the shell, to work the same whether given one file or
    a whole production's worth) - a pattern matching nothing is kept as a
    literal path, so a plain existing file still works and a genuine typo
    fails loudly (via uproot, on the actual read) instead of silently
    vanishing here.'''
    files = []
    for pattern in patterns:
        matched = sorted(glob.glob(pattern))
        files.extend(matched if matched else [pattern])
    if not files:
        raise ValueError('no files matched: {}'.format(patterns))
    return files


def load_data(files, treename='tree'):
    '''
    Read every category's branches, for whichever schema `files` actually
    are (see ntuple_io.py - detected automatically, works the same for our
    own paired ntuples or the real fullsim reference dataset), from every
    file in `files` (concatenated under the hood - so this works the same
    for one quick test file or a whole production's many per-job ntuples).
    Returns (data, njets, sides): data is ntuple_io.load_particles()'s own
    dict (plus 'part_pt'/'hlt_part_pt' entries added here), njets is the
    total number of offline-selected jets (rows) across all files - the
    single shared denominator used for every side present, see module
    docstring - and sides is ALL_SIDES filtered down to whichever side(s)
    are actually present (only ever both for fullsim; either for "ours",
    depending on whether it's a paired production - see ALL_SIDES).
    '''
    data = nio.load_particles(files, suffixes=SUFFIXES, treename=treename)
    sides = [s for s in ALL_SIDES if (s[0] + 'px') in data]
    for prefix, _, _ in sides:
        data[prefix + 'pt'] = np.sqrt(data[prefix + 'px'] ** 2 + data[prefix + 'py'] ** 2)
    return data, len(data['part_pt']), sides


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


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('files', nargs='+',
        help='paired-ntuple ROOT file(s)/glob(s) (produced by makeNtuplesPaired.C) making up'
             ' ONE production to plot Offline vs HLT for - see module docstring')
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
             ' (e.g. a process name like "train_higgs2p"); the particle-type'
             ' label is placed just below it when this is set')
    parser.add_argument('--output', default=DEFAULT_OUTPUT,
        help='base output plot file; a separate file is written per particle'
             ' category by inserting a suffix before the extension, e.g.'
             ' output_plots/plot_pt.png -> output_plots/plot_pt_all.png,'
             ' output_plots/plot_pt_charged.png, ... (default: output_plots/plot_pt.png,'
             ' next to this script)')
    args = parser.parse_args()

    if args.linbins:
        bin_edges = np.linspace(args.ptmin, args.ptmax, args.nbins + 1)
    else:
        bin_edges = np.logspace(np.log10(args.ptmin), np.log10(args.ptmax), args.nbins + 1)
    bin_centers = 0.5 * (bin_edges[:-1] + bin_edges[1:])

    files = expand_files(args.files)
    data, njets, sides = load_data(files, treename=args.treename)
    has_hlt = len(sides) == 2
    if not has_hlt:
        print('No hlt_part_*/hlt_matched branches found - this is offline-only production output'
              ' (e.g. a single-card run like output_jetclass2_5M, not a paired one); plotting Offline only.')

    n_matched = int(ak.sum(data['hlt_matched'])) if has_hlt and njets else None
    if has_hlt:
        print('{} offline-selected jets ({} with an HLT match, {:.1f}%)'.format(
            njets, n_matched, 100.0 * n_matched / njets if njets else 0))
    else:
        print('{} jets'.format(njets))

    outbase, outext = os.path.splitext(os.path.abspath(args.output))
    if not outext:
        outext = '.png'
    outdir = os.path.dirname(outbase)
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir)

    if njets == 0:
        print('WARNING: no jets found - nothing to plot')
        return

    for category, mask_fn, category_label in CATEGORIES:
        fig, ax = plt.subplots(figsize=(8, 6))

        max_height = 0.0
        for prefix, label, color in sides:
            pt = data[prefix + 'pt'][mask_fn(data, prefix)] if mask_fn is not None else data[prefix + 'pt']
            avg_mult, avg_mult_err = average_multiplicity_per_bin(pt, njets, bin_edges)
            ax.step(bin_centers, avg_mult, where='mid', color=color, linewidth=3, label=label)
            lower = np.clip(avg_mult - avg_mult_err, a_min=0, a_max=None)
            upper = avg_mult + avg_mult_err
            ax.fill_between(bin_centers, lower, upper, step='mid', color=color, alpha=0.3, linewidth=0)
            if len(upper):
                max_height = max(max_height, np.nanmax(upper))

        ax.set_xlabel(r'Particle $p_{T}$ [GeV]')
        ax.set_ylabel('Average number of particles / jet / bin')
        if not args.linx:
            ax.set_xscale('log')
        if not args.liny:
            ax.set_yscale('log')
        ax.minorticks_on()
        ax.grid(True, which='major', linestyle='-', alpha=0.4)
        ax.grid(True, which='minor', linestyle=':', alpha=0.25)
        # extra headroom above the curves so the info text (top-left) and legend
        # (top-right) both have clear space above the data rather than overlapping it
        if max_height > 0:
            bottom, _ = ax.get_ylim()
            ax.set_ylim(bottom, max_height * (25 if not args.liny else 1.6))
        info_lines = [args.info] if args.info else []
        info_lines.append('{} jets ({:.1f}% HLT-matched)'.format(njets, 100.0 * n_matched / njets)
                           if has_hlt else '{} jets'.format(njets))
        info_lines.append(category_label)
        for i, line in enumerate(info_lines):
            ax.text(0.03, 0.97 - 0.07 * i, line, transform=ax.transAxes, ha='left', va='top', fontsize=16)
        ax.legend(loc='upper right')
        fig.tight_layout()

        outpath = '{}_{}{}'.format(outbase, category, outext)
        fig.savefig(outpath, dpi=150)
        plt.close(fig)
        print('Saved plot to {}'.format(outpath))


if __name__ == '__main__':
    main()
