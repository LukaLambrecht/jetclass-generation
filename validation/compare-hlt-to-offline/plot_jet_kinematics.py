#!/usr/bin/env python3

'''
Compare basic JET kinematics (pT and eta) between OFFLINE and HLT
reconstruction of the SAME jets, per jet class - the jet-level sibling of
plot_nparticles.py, which does the same for per-jet particle counts. Reads
EITHER of two schemas transparently (see ntuple_io.py for the full
description of each, and how they're normalized onto the same
jet_*/hlt_jet_*/hlt_matched naming used below):

  - our own PAIRED ntuples (delphes_analyzers/makeNtuplesPaired.C for the
    delphes backend, fullsim_analyzers/makeNtuplesFullSim.cc for the
    fullsim one): one row per selected offline jet, carrying its own
    jet_* branches plus its matched HLT jet's hlt_jet_* branches.
  - the real CMS offline+scouting reference dataset this pipeline is trying
    to mimic (see hlteff/README.md's "Data source").

Which schema the input is gets detected automatically (ntuple_io.detect_schema())
and needs no flag. The jet classes are exactly plot_nparticles.py's own 10
(QCD aggregated, X_tauhtaue/X_tauhtaum merged into X_tauhtaul, flavor-mixed
two-prong labels excluded) - imported from it rather than redefined, so the
two scripts can never disagree about what a class is.

CHEAP BY CONSTRUCTION: only flat per-jet scalar branches are read
(ntuple_io.load_jet_kinematics()), never any per-particle data - so this runs
over a whole production in seconds, unlike plot_nparticles.py --plots types.

Unmatched jets (no HLT counterpart at all) are excluded from the HLT
distributions rather than entered as their -999 sentinel, for the same reason
plot_nparticles.py excludes them from its HLT counts; the per-class match rate
is printed and shown on each panel so that exclusion is never silent.

Each quantity gets its own figure, a 2x5 grid of jet classes, with Offline and
HLT overlaid. Binning is FIXED by default (see QUANTITIES), not derived from
the data, so the same quantity is directly comparable between two different
productions plotted separately - which is the main use: run it once per dataset
into its own --outdir and compare. The printed median/mean table is usually the
quickest way to see a hardness difference between two samples.

Usage (from any directory):
  python3 plot_jet_kinematics.py FILE_OR_GLOB [FILE_OR_GLOB ...] [options]

Examples:
  # the real CMS reference dataset, both its samples pooled
  python3 plot_jet_kinematics.py \\
      '/eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/*/dnnTuples_nanov15_*.root' \\
      --outdir output_plots_fullsim_og

  # our own fullsim production
  python3 plot_jet_kinematics.py \\
      '/eos/user/l/llambrec/jetclass/output_fullsim_630k_trial/jetclass2/*/fullsim_offline+hlt/ntuple_*.root' \\
      --outdir output_plots_fullsim_trial

  # a different pT window, and only a couple of classes
  python3 plot_jet_kinematics.py 'FILES...' --range pt=200,25000 --classes QCD,X_bb
'''

import os
import sys
import argparse

import numpy as np
import matplotlib.pyplot as plt

THISDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(THISDIR))  # validation/ - for ntuple_io
import ntuple_io as nio
# the class scheme and the file-list helper come from the sibling script, so the
# two can't drift apart in what "X_tauhtaul" or "QCD" means (it guards its own
# command-line handling behind __main__, so importing it does nothing else)
sys.path.append(THISDIR)
from plot_nparticles import CLASSES, CLASS_SUFFIXES, class_masks, expand_files

# same house style as plot_nparticles.py
plt.rcParams.update({
    'font.size': 16,
    'axes.labelsize': 18,
    'xtick.labelsize': 14,
    'ytick.labelsize': 14,
    'legend.fontsize': 14,
})

OFFLINE_COLOR = 'dodgerblue'
HLT_COLOR = 'darkorchid'

DEFAULT_OUTDIR = os.path.join(THISDIR, 'output_plots')
TREE_NAME = 'tree'

# The quantities this script can plot, each as
#   key: (axis label, default low edge, default high edge, nbins, log-spaced x?)
# `key` is an ntuple_io.JET_QUANTITIES name, i.e. it reads jet_<key>/hlt_jet_<key>
# on either schema - so extending this to e.g. sdmass or tau2 later is a one-line
# addition here and nothing else. Defaults are fixed rather than data-derived, see
# the module docstring.
QUANTITIES = {
    'pt':  (r'Jet $p_{T}$ [GeV]', 150.0, 6000.0, 40, True),
    'eta': (r'Jet $\eta$',        -2.6,  2.6,    40, False),
}
DEFAULT_QUANTITIES = ['pt', 'eta']


def parse_range_overrides(range_args):
    '''--range pt=200,25000 (repeatable) -> {'pt': (200.0, 25000.0)}.'''
    out = {}
    for item in range_args or []:
        if '=' not in item:
            raise Exception('--range must be KEY=LO,HI, got {!r}'.format(item))
        key, rng = item.split('=', 1)
        key = key.strip()
        if key not in QUANTITIES:
            raise Exception('--range key {!r} is not a plottable quantity - known: {}'.format(
                key, ', '.join(QUANTITIES)))
        try:
            lo, hi = (float(x) for x in rng.split(','))
        except ValueError:
            raise Exception('--range {!r}: expected KEY=LO,HI with two numbers'.format(item))
        if not hi > lo:
            raise Exception('--range {!r}: high edge must exceed the low one'.format(item))
        out[key] = (lo, hi)
    return out


def bin_edges_for(key, overrides):
    label, lo, hi, nbins, logx = QUANTITIES[key]
    if key in overrides:
        lo, hi = overrides[key]
    if logx:
        if lo <= 0:
            raise Exception('{}: a log-spaced axis needs a positive low edge, got {}'.format(key, lo))
        return np.logspace(np.log10(lo), np.log10(hi), nbins + 1), label, logx
    return np.linspace(lo, hi, nbins + 1), label, logx


def read_all_classes(files, class_names, quantities, max_jets, min_jet_pt=None, max_jet_eta=None):
    '''
    One read of `files` for every requested quantity, bucketed into the requested
    classes (via plot_nparticles.class_masks(), so identical class definitions).

    The HLT values of a class are the matched subset only (see module docstring);
    njets/n_matched count every jet of the class either way, for the panel captions.
    A `max_jets` cap is applied post-read, same as plot_nparticles.py does.

    Returns {class_name: {'njets': n, 'n_matched': m_or_None,
                          'q': {quantity: (offline_values, hlt_values_or_None)}}}.
    '''
    masks, njets_total = class_masks(files, class_names)
    data = nio.load_jet_kinematics(files, quantities=quantities, treename=TREE_NAME)
    has_hlt = 'hlt_matched' in data
    if max_jets is not None and njets_total > max_jets:
        masks = {name: m[:max_jets] for name, m in masks.items()}
        data = {k: v[:max_jets] for k, v in data.items()}

    # Optional extra OFFLINE selection, applied to every class alike - see
    # ntuple_io.jet_selection_mask() for why the samples compared here need it.
    keep = nio.jet_selection_mask(files, min_jet_pt=min_jet_pt, max_jet_eta=max_jet_eta,
                                  treename=TREE_NAME)
    if keep is not None:
        if max_jets is not None and len(keep) > max_jets:
            keep = keep[:max_jets]
        print('offline selection ({}) keeps {}/{} jets ({:.1f}%)'.format(
            nio.describe_jet_selection(min_jet_pt, max_jet_eta),
            int(keep.sum()), len(keep), 100.0 * keep.mean() if len(keep) else 0))
        masks = {name: m & keep for name, m in masks.items()}

    matched_all = data.get('hlt_matched')
    results = {}
    for name in class_names:
        mask = masks[name]
        match_mask = matched_all[mask] if has_hlt else None
        per_q = {}
        for q in quantities:
            offline_vals = np.asarray(data['jet_' + q])[mask]
            hlt_vals = np.asarray(data['hlt_jet_' + q])[mask][match_mask] if has_hlt else None
            per_q[q] = (offline_vals, hlt_vals)
        results[name] = {'njets': int(mask.sum()),
                         'n_matched': int(match_mask.sum()) if has_hlt else None,
                         'q': per_q}
    return results


def make_panel(ax, class_name, key, offline_vals, hlt_vals, njets, n_matched, overrides):
    '''One jet class' panel for one quantity: Offline and HLT overlaid as normalized
    step histograms on a shared fixed binning, log-y (jet spectra span orders of
    magnitude), captioned with the class, its jet count/match rate and both medians -
    the medians being the number that actually quantifies "one sample is harder than
    the other".'''
    edges, label, logx = bin_edges_for(key, overrides)
    if len(offline_vals) == 0:
        ax.text(0.5, 0.5, '{}: no data'.format(class_name), ha='center', va='center',
                transform=ax.transAxes)
        return

    series = [('Offline', offline_vals, OFFLINE_COLOR)]
    if hlt_vals is not None:
        series.append(('HLT', hlt_vals, HLT_COLOR))
    max_height = 0.0
    for series_label, vals, color in series:
        if len(vals) == 0:
            continue
        counts, _, _ = ax.hist(vals, bins=edges, density=True, histtype='step',
                               linewidth=2, color=color, label=series_label)
        if len(counts):
            max_height = max(max_height, counts.max())

    ax.set_xlabel(label)
    ax.set_ylabel('Number of jets (normalized)')
    if logx:
        ax.set_xscale('log')
    ax.set_yscale('log')
    ax.minorticks_on()
    ax.grid(True, which='major', linestyle='-', alpha=0.4)
    ax.grid(True, which='minor', linestyle=':', alpha=0.25)
    if max_height > 0:
        bottom, _ = ax.get_ylim()
        ax.set_ylim(bottom, max_height * 60)

    info_lines = ['Jet class: {}'.format(class_name)]
    if n_matched is not None:
        info_lines.append('{} jets ({:.1f}% HLT matched)'.format(
            njets, 100.0 * n_matched / njets if njets else 0))
    else:
        info_lines.append('{} jets'.format(njets))
    info_lines.append('Offline median: {:.3g}'.format(np.median(offline_vals)))
    if hlt_vals is not None and len(hlt_vals):
        info_lines.append('HLT median: {:.3g}'.format(np.median(hlt_vals)))
    for i, line in enumerate(info_lines):
        ax.text(0.03, 0.96 - 0.065 * i, line, transform=ax.transAxes, ha='left', va='top',
                fontsize=13)
    ax.legend(loc='upper right')


def make_grid(results, classes, key, outpath, overrides):
    '''One figure per quantity: 2 rows x 5 columns of jet classes, same layout as
    plot_nparticles.py's own make_grid().'''
    ncols = 5
    nrows = (len(classes) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 6 * nrows))
    axes = np.atleast_1d(axes).flatten()
    for ax, name in zip(axes, classes):
        entry = results[name]
        offline_vals, hlt_vals = entry['q'][key]
        make_panel(ax, name, key, offline_vals, hlt_vals, entry['njets'], entry['n_matched'],
                   overrides)
    for ax in axes[len(classes):]:
        ax.axis('off')
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print('wrote {}'.format(outpath))


def print_stats(class_name, source, vals):
    if vals is None or len(vals) == 0:
        print('{:<16}{:<10}{:>10}'.format(class_name, source, 'no data'))
        return
    # 4 significant figures rather than fixed decimals, so the same table is
    # readable for a quantity of order 1000 (pT) and one of order 0.01 (eta mean)
    print('{:<16}{:<10}{:>10}{:>12.4g}{:>12.4g}{:>12.4g}{:>12.4g}'.format(
        class_name, source, len(vals), vals.mean(), np.median(vals),
        np.percentile(vals, 25), np.percentile(vals, 75)))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('files', nargs='+',
        help='ntuple file(s)/glob(s) to pool together and bucket by jet class (quote globs'
             ' so THIS expands them, not the shell) - see module docstring')
    parser.add_argument('--quantities', default=','.join(DEFAULT_QUANTITIES),
        help='comma-separated quantities to plot, one figure each (default: {}; available:'
             ' {})'.format(','.join(DEFAULT_QUANTITIES), ', '.join(QUANTITIES)))
    parser.add_argument('--classes', default=','.join(CLASSES),
        help='comma-separated class names (default: all 10, exactly as plot_nparticles.py)')
    parser.add_argument('--range', action='append', dest='ranges', default=None, metavar='KEY=LO,HI',
        help='override a quantity\'s binning range, repeatable (e.g. --range pt=200,25000).'
             ' Defaults are fixed so separate productions stay comparable - see QUANTITIES')
    parser.add_argument('--max-jets', type=int, default=None,
        help='cap on jets read in total, across all `files`, before bucketing (default: no cap)')
    parser.add_argument('--min-jet-pt', type=float, default=None,
        help='extra selection on the OFFLINE jet pT in GeV (default: none - plot whatever the'
             ' sample contains). Use 200 to put a fullsim production made before 2026-10-05'
             ' on the same footing as the CMS reference dataset and the delphes productions,'
             ' which are all effectively cut there - see read_all_classes()')
    parser.add_argument('--max-jet-eta', type=float, default=None,
        help='extra selection on the OFFLINE jet |eta| (default: none). The CMS reference'
             ' dataset uses 2.4; our own ntuplizers used 2.5 until 2026-10-05')
    parser.add_argument('--tag', default=None,
        help='suffix added to the output file names, e.g. --tag ptmatched ->'
             ' jet_kinematics_pt_ptmatched.png - so a selected and an unselected version can'
             ' live side by side in one --outdir')
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR,
        help='directory to write plots into (default: {})'.format(DEFAULT_OUTDIR))
    args = parser.parse_args()

    quantities = [q.strip() for q in args.quantities.split(',') if q.strip()]
    unknown = [q for q in quantities if q not in QUANTITIES]
    if unknown:
        raise Exception('unknown quantity/-ies {} - available: {}'.format(
            unknown, ', '.join(QUANTITIES)))
    if not quantities:
        raise Exception('--quantities selected nothing to plot')

    classes = [c.strip() for c in args.classes.split(',') if c.strip()]
    unknown = [c for c in classes if c != 'QCD' and c not in CLASS_SUFFIXES]
    if unknown:
        raise Exception('unknown class(es) {} - known classes: {}'.format(
            unknown, ', '.join(CLASSES)))

    overrides = parse_range_overrides(args.ranges)
    max_jets = args.max_jets if args.max_jets and args.max_jets > 0 else None
    os.makedirs(args.outdir, exist_ok=True)

    files = expand_files(args.files)
    results = read_all_classes(files, classes, quantities, max_jets,
                               min_jet_pt=args.min_jet_pt, max_jet_eta=args.max_jet_eta)
    suffix = '_{}'.format(args.tag) if args.tag else ''

    for key in quantities:
        header = '{:<16}{:<10}{:>10}{:>12}{:>12}{:>12}{:>12}'.format(
            'class', 'source', 'njets', 'mean', 'median', 'p25', 'p75')
        print('\n=== {} ==='.format(QUANTITIES[key][0]))
        print(header)
        print('-' * len(header))
        for name in classes:
            offline_vals, hlt_vals = results[name]['q'][key]
            print_stats(name, 'offline', offline_vals)
            print_stats(name, 'hlt', hlt_vals)
        make_grid(results, classes, key,
                  os.path.join(args.outdir, 'jet_kinematics_{}{}.png'.format(key, suffix)),
                  overrides)
