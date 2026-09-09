#!/usr/bin/env python3

'''
Plot the mean per-jet particle-flow composition (energy fraction of
electrons, muons, charged hadrons, photons, neutral hadrons, and any
unclassified constituents) versus jet pT, as horizontal stacked bar
charts - one panel for Offline, one for HLT. Reads EITHER of two schemas
transparently (see ntuple_io.py for the full description of each, and how
they're normalized onto the same part_*/hlt_part_*/jet_pt/hlt_matched
naming used below):

  - our own PAIRED ntuples (delphes_analyzers/makeNtuplesPaired.C): one
    row per selected offline jet, carrying its own part_*/jet_* branches
    plus its matched HLT jet's hlt_part_*/hlt_jet_* branches in the SAME
    entry.

  - the real FullSim/scouting reference dataset this pipeline is trying to
    mimic (see hlteff/README.md's "Data source") - same one-entry-two-
    collections structure (every row already IS a matched pair there, see
    ntuple_io.py), letting the exact same comparison be made directly
    against real detector data instead of only Delphes-vs-Delphes.

Pass either kind of ntuple as `files` - which schema it is is detected
automatically (see ntuple_io.detect_schema()) and needs no flag.

Both panels are binned by the OFFLINE jet's own pT (not the HLT jet's,
even in the HLT panel) so the two panels describe exactly the same
physical jets in each row - the HLT panel is then implicitly "...and here
is what HLT reconstructs for them", including only rows with an HLT match
(hlt_matched) in its own per-bin means (a composition FRACTION is
undefined, not 0%, for a jet HLT didn't reconstruct at all) - the
match fraction actually achieved in each bin is printed alongside the
jet count so that's never silently hidden. (Every fullsim row is matched
by construction, so its HLT panel's match fraction is always 100%.)

Usage (from any directory - output defaults to output_plots/ next to this script):
  python plot_composition.py FILE_OR_GLOB [FILE_OR_GLOB ...] [options]

`files` are every ntuple belonging to ONE production/sample (e.g. all of a
process' condor-job ntuple_*.root under one card-pair directory, or a
fullsim sample's dnnTuples_nanov15_*.root) - pass a glob (quoted, so this
script expands it, not the shell) or a full file list; they're all
concatenated before plotting.

Examples:
  python plot_composition.py \\
      '/eos/user/l/llambrec/jetclass/output_jetclass2_5M/jetclass2/train_higgs2p/onlyFatJet+onlyFatJetHLT/ntuple_*.root' \\
      --output output_plots/plot_composition_train_higgs2p.png

  # same, but against the real FullSim/scouting reference dataset
  python plot_composition.py \\
      '/eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/H0HpHm_mixed_new/dnnTuples_nanov15_*.root' \\
      --output output_plots/plot_composition_fullsim_h0hphm.png
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

DEFAULT_OUTPUT = os.path.join(THISDIR, 'output_plots', 'plot_composition.png')

plt.rcParams.update({
    'font.size': 14,
    'axes.labelsize': 15,
    'xtick.labelsize': 13,
    'ytick.labelsize': 13,
    'legend.fontsize': 13,
})

# category name -> (mask function given a dict of the loaded branch arrays
# and the "part_"/"hlt_part_" prefix to apply it to, or None for the
# unclassified catch-all; legend label; bar color) - order determines
# stacking order (left to right)
CATEGORIES = [
    ('electron',       lambda d, p: d[p + 'isElectron'] != 0,       'Electron',       'crimson'),
    ('muon',           lambda d, p: d[p + 'isMuon'] != 0,           'Muon',           'rebeccapurple'),
    ('charged_hadron', lambda d, p: d[p + 'isChargedHadron'] != 0,  'Charged hadron', 'darkorange'),
    ('photon',         lambda d, p: d[p + 'isPhoton'] != 0,         'Photon',         'goldenrod'),
    ('neutral_hadron', lambda d, p: d[p + 'isNeutralHadron'] != 0,  'Neutral hadron', 'teal'),
    ('unclassified',   None,                                        'Unclassified',   'gray'),
]

ALL_SIDES = [('part_', 'Offline'), ('hlt_part_', 'HLT')]

# per-particle fields CATEGORIES actually needs - passed to
# ntuple_io.load_particles()'s own `suffixes` filter so it never reads/builds
# 'px'/'py'/'charge' (unused here), the main cost of that function
SUFFIXES = ['energy', 'isElectron', 'isMuon', 'isPhoton', 'isChargedHadron', 'isNeutralHadron']

DEFAULT_PT_BINS = [200, 250, 300, 400, 500, 650, 800, 1000, 1500, 2000, 3000, 5000]


def expand_files(patterns):
    '''See plot_pt.py's own expand_files() - identical glob-or-literal handling.'''
    files = []
    for pattern in patterns:
        matched = sorted(glob.glob(pattern))
        files.extend(matched if matched else [pattern])
    if not files:
        raise ValueError('no files matched: {}'.format(patterns))
    return files


def load_composition_data(files, treename='tree'):
    '''
    Read the branches needed to compute per-jet composition fractions, for
    whichever schema `files` actually are (see ntuple_io.py - detected
    automatically, works the same for our own paired ntuples or the real
    fullsim reference dataset) and for whichever side(s) it has (only ever
    both for fullsim; either for "ours", depending on whether it's a
    paired production). Returns (jet_pt, hlt_matched, fracs, sides):
    jet_pt is the OFFLINE jet pT (used to bin BOTH panels - see module
    docstring), hlt_matched is None if there's no HLT side at all, and
    fracs is {'part_<category>': array, 'hlt_part_<category>': array},
    one energy-fraction value per jet (NaN where the corresponding side's
    total energy is zero, i.e. an unmatched HLT row).
    '''
    data = nio.load_particles(files, suffixes=SUFFIXES, treename=treename)
    sides = [s for s in ALL_SIDES if (s[0] + 'energy') in data]

    fracs = {}
    for prefix, _ in sides:
        total_energy = ak.sum(data[prefix + 'energy'], axis=1)
        classified = ak.zeros_like(data[prefix + 'isElectron'], dtype=np.int32)
        for name, mask_fn, _, _ in CATEGORIES:
            if mask_fn is None:
                continue
            mask = mask_fn(data, prefix)
            classified = classified + ak.values_astype(mask, np.int32)
            with np.errstate(invalid='ignore'):
                fracs[prefix + name] = ak.to_numpy(
                    ak.sum(ak.values_astype(mask, np.float32) * data[prefix + 'energy'], axis=1) / total_energy)
        with np.errstate(invalid='ignore'):
            fracs[prefix + 'unclassified'] = ak.to_numpy(
                ak.sum(ak.values_astype(classified == 0, np.float32) * data[prefix + 'energy'], axis=1) / total_energy)

    hlt_matched = ak.to_numpy(data['hlt_matched']) if len(sides) == 2 else None
    return ak.to_numpy(data['jet_pt']), hlt_matched, fracs, sides


def format_bin_label(lo, hi):
    fmt = lambda v: '{:g}'.format(v)
    return '{}–{}'.format(fmt(lo), fmt(hi))


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('files', nargs='+',
        help='paired-ntuple ROOT file(s)/glob(s) (produced by makeNtuplesPaired.C) making up'
             ' ONE production to plot Offline vs HLT composition for - see module docstring')
    parser.add_argument('--treename', default='tree',
        help='name of the tree to read (default: tree)')
    parser.add_argument('--ptbins', default=None,
        help='comma-separated jet pT bin edges in GeV, applied to the OFFLINE jet pT for'
             ' both panels (default: {})'.format(','.join(str(b) for b in DEFAULT_PT_BINS)))
    parser.add_argument('--label-threshold', type=float, default=5.0,
        help='minimum segment size in %% for a percentage label to be drawn inside it (default: 5)')
    parser.add_argument('--title', default=None,
        help='extra title text prepended to each panel title (e.g. a process name)')
    parser.add_argument('--output', default=DEFAULT_OUTPUT,
        help='output plot file (default: output_plots/plot_composition.png, next to this script)')
    args = parser.parse_args()

    pt_bins = [float(x) for x in args.ptbins.split(',')] if args.ptbins else DEFAULT_PT_BINS
    nbins = len(pt_bins) - 1
    bin_labels = [format_bin_label(pt_bins[i], pt_bins[i + 1]) for i in range(nbins)]
    y = np.arange(nbins)

    files = expand_files(args.files)
    jet_pt, hlt_matched, fracs, sides = load_composition_data(files, treename=args.treename)
    njets = len(jet_pt)
    has_hlt = hlt_matched is not None
    if has_hlt:
        print('{} offline-selected jets ({} with an HLT match, {:.1f}%)'.format(
            njets, int(hlt_matched.sum()), 100.0 * hlt_matched.sum() / njets if njets else 0))
    else:
        print('{} jets (no hlt_part_*/hlt_matched branches found - this is offline-only production'
              ' output, e.g. a single-card run like output_jetclass2_5M; plotting Offline only.)'.format(njets))

    fig, axes = plt.subplots(1, len(sides), figsize=(6.5 * len(sides), 0.55 * nbins + 2), sharey=True)
    if len(sides) == 1:
        axes = [axes]

    for ax, (prefix, side_label) in zip(axes, sides):
        # HLT's own per-bin means only ever run over hlt_matched rows - a
        # composition fraction is undefined (not 0%), for a jet with no HLT
        # match at all, not a real "0% of everything" data point
        in_side = hlt_matched if prefix == 'hlt_part_' else np.ones(njets, dtype=bool)

        binned = {name: np.full(nbins, np.nan) for name, _, _, _ in CATEGORIES}
        njets_per_bin = np.zeros(nbins, dtype=int)
        nmatched_per_bin = np.zeros(nbins, dtype=int)
        for i in range(nbins):
            lo, hi = pt_bins[i], pt_bins[i + 1]
            in_bin = (jet_pt >= lo) & (jet_pt < hi)
            njets_per_bin[i] = np.count_nonzero(in_bin)
            nmatched_per_bin[i] = np.count_nonzero(in_bin & in_side)
            if nmatched_per_bin[i] == 0:
                continue
            for name, _, _, _ in CATEGORIES:
                binned[name][i] = 100.0 * np.nanmean(fracs[prefix + name][in_bin & in_side])

        left = np.zeros(nbins)
        for name, _, cat_label, color in CATEGORIES:
            vals = np.nan_to_num(binned[name])
            ax.barh(y, vals, left=left, height=0.7, color=color, label=cat_label)
            for i in range(nbins):
                if vals[i] >= args.label_threshold:
                    ax.text(left[i] + vals[i] / 2, y[i], '{:.0f}%'.format(vals[i]),
                            ha='center', va='center', color='white', fontweight='bold', fontsize=12)
            left += vals

        title = '{} ({})'.format(args.title, side_label) if args.title else side_label
        ax.set_title(title, fontweight='bold', fontsize=17)
        ax.set_xlabel('Mean per-jet composition [%]')
        ax.set_xlim(0, 100)
        ax.xaxis.grid(True, alpha=0.3)
        ax.set_axisbelow(True)
        # per-bin (jets, HLT-match%) annotation on the right edge, so a thin/
        # low-statistics or poorly-matched bin is never silently indistinguishable
        # from a well-populated one
        for i in range(nbins):
            match_pct = 100.0 * nmatched_per_bin[i] / njets_per_bin[i] if njets_per_bin[i] else 0
            annotation = '{} jets'.format(njets_per_bin[i]) if prefix != 'hlt_part_' \
                else '{} jets ({:.0f}% matched)'.format(njets_per_bin[i], match_pct)
            ax.text(101, y[i], annotation, ha='left', va='center', fontsize=10, color='dimgray')

    axes[0].set_yticks(y)
    axes[0].set_yticklabels(bin_labels)
    axes[0].set_ylabel(r'Jet $p_{T}$ bin [GeV] (offline)')
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
