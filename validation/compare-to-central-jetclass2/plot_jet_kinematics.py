#!/usr/bin/env python3

'''
Compares jet-level kinematics (jet_pt, jet_eta) of our own JetClass-II
production to the published JetClass-II dataset, per class - same style as
plot_nparticles.py (see that module's docstring for the full context: class
scheme, file formats, why QCD is one combined class while 9 of the Res2P
flavors are each their own class/panel).

Unlike JetClass-I - where the published files bake in a hard, narrow
pT in [500,1000] GeV / |eta|<2 window (see ../compare-to-central-jetclass/
plot_jet_kinematics.py's own docstring for how that was established) -
JetClass-II's published files span a much broader boosted-jet pT range by
design (many resonance mass points / QCD pThat bins). Directly checking the
downloaded central jet_pt/jet_eta range (see plot_nparticles.py's own
SELECTION_PT_MIN/SELECTION_ETA_MAX) shows a hard floor at pT>200 GeV (no
upper bound) and |eta|<2.5 - matching Delphes' own JetPTMin=200 on the
offline card and its eta acceptance, not a separate later-stage analysis
cut. Plotted here with a wide, fixed bin range on both axes (extending past
the selection on the low-pT/high-eta side) so that floor is directly
visible as a hard edge, same reasoning as the JetClass-I sibling script.

Reuses plot_nparticles.py's file-discovery/read/bucketing plumbing directly
(same --central-path/--our-output-path/--classes/etc. semantics) rather
than duplicating it.

Usage:
  python3 plot_jet_kinematics.py
  python3 plot_jet_kinematics.py --classes QCD,X_bb,X_gg --no-selection
'''

import os
import argparse

import numpy as np
import awkward as ak
import matplotlib.pyplot as plt

from plot_nparticles import (
    CLASSES, CLASS_INFO, read_all_classes, selection_mask,
    OUR_COLOR, CENTRAL_COLOR,
    DEFAULT_OUR_OUTPUT_PATH, DEFAULT_OUR_CARD, DEFAULT_CENTRAL_PATH,
    DEFAULT_MAX_JETS_PER_SOURCE, DEFAULT_OUTDIR,
    SELECTION_PT_MIN, SELECTION_ETA_MAX,
)

THISDIR = os.path.dirname(os.path.abspath(__file__))

# (branch, axis label, (bin_lo, bin_hi, nbins)) - range deliberately extends
# below SELECTION_PT_MIN / past SELECTION_ETA_MAX on both sources, so the
# hard floor/acceptance edge is directly visible rather than potentially
# cropped out; no upper pT bin range restriction beyond what comfortably
# covers JetClass-II's own broad spectrum (see module docstring)
KINEMATICS = [
    ('jet_pt',  'Jet pT [GeV]', (0, 3000, 60)),
    ('jet_eta', 'Jet eta',      (-3, 3, 60)),
]


def jet_pt(arr):
    return ak.to_numpy(arr['jet_pt']) if len(arr) else np.array([], dtype=np.float64)


def jet_eta(arr):
    return ak.to_numpy(arr['jet_eta']) if len(arr) else np.array([], dtype=np.float64)


VALUE_FN = {'jet_pt': jet_pt, 'jet_eta': jet_eta}


def make_plot(ax, label, our_vals, central_vals, xlabel, bin_range):
    '''Same look as plot_nparticles.make_plot(), but fixed-range float bins instead of integer ones.'''
    lo, hi, nbins = bin_range
    bins = np.linspace(lo, hi, nbins + 1)

    if len(our_vals) == 0 and len(central_vals) == 0:
        ax.text(0.5, 0.5, '{}: no data'.format(label), ha='center', va='center', transform=ax.transAxes)
        return

    max_height = 0.0
    for vals, series_label, color in ((central_vals, 'central JetClass-II', CENTRAL_COLOR),
                                       (our_vals, 'ours ({})'.format(DEFAULT_OUR_CARD), OUR_COLOR)):
        if len(vals) == 0:
            continue
        counts, _, _ = ax.hist(vals, bins=bins, density=True, histtype='step', linewidth=2, color=color,
                                label=series_label)
        if len(counts):
            max_height = max(max_height, counts.max())
    ax.set_yscale('log')
    ax.set_xlabel(xlabel)
    ax.set_ylabel('Number of jets (normalized)')
    if max_height > 0:
        bottom, _ = ax.get_ylim()
        ax.set_ylim(bottom, max_height * 25)
    ax.text(0.03, 0.95, label, transform=ax.transAxes, ha='left', va='top', fontsize=14,
            bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray', alpha=0.85))
    ax.legend(loc='upper right')


def make_grid(results, classes, key, xlabel, bin_range, outpath):
    ncols = 5
    nrows = (len(classes) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 6 * nrows))
    axes = np.atleast_1d(axes).flatten()
    value_fn = VALUE_FN[key]
    for ax, name in zip(axes, classes):
        ours, central = results[name]
        make_plot(ax, name, value_fn(ours), value_fn(central), xlabel, bin_range)
    for ax in axes[len(classes):]:
        ax.axis('off')
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print('wrote {}'.format(outpath))


def print_stats(name, source, vals):
    '''min/p1/p99/max, not mean/median/std (matches ../compare-to-central-jetclass/plot_jet_kinematics.py) - the
    question here is whether there's a hard edge at a specific value.'''
    if len(vals) == 0:
        print('{:<16}{:<24}{:>10}'.format(name, source, 'no data'))
        return
    print('{:<16}{:<24}{:>10}{:>10.2f}{:>10.2f}{:>10.2f}{:>10.2f}'.format(
        name, source, len(vals), vals.min(), np.percentile(vals, 1), np.percentile(vals, 99), vals.max()))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--central-path', default=DEFAULT_CENTRAL_PATH,
        help='directory containing the downloaded central JetClass-II .parquet files (default: {})'.format(
            DEFAULT_CENTRAL_PATH))
    parser.add_argument('--our-output-path', default=DEFAULT_OUR_OUTPUT_PATH,
        help='our own jetclass2 production output directory (default: {})'.format(DEFAULT_OUR_OUTPUT_PATH))
    parser.add_argument('--our-card', default=DEFAULT_OUR_CARD,
        help='which of our Delphes cards to compare (default: {})'.format(DEFAULT_OUR_CARD))
    parser.add_argument('--classes', default=','.join(CLASSES),
        help='comma-separated class names (default: all 10 - QCD + 9 diagonal Res2P flavors)')
    parser.add_argument('--max-jets-per-source', type=int, default=DEFAULT_MAX_JETS_PER_SOURCE,
        help='cap on jets read per underlying source, not per final class (default: no cap)')
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR,
        help='directory to write plots into (default: {})'.format(DEFAULT_OUTDIR))
    parser.add_argument('--self-test', action='store_true',
        help='label the run as a plumbing self-test rather than a real comparison')
    parser.add_argument('--no-selection', action='store_true',
        help='skip the pT>{:g} GeV / |eta|<{:g} selection (default: applied to both sources) -'
             ' pass this to see the RAW, unselected kinematics (e.g. to check for a hard edge'
             ' in the first place, as originally done to find these values)'.format(
                 SELECTION_PT_MIN, SELECTION_ETA_MAX))
    args = parser.parse_args()

    classes = [c.strip() for c in args.classes.split(',') if c.strip()]
    unknown = [c for c in classes if c not in CLASS_INFO]
    if unknown:
        raise Exception('unknown class(es) {} - known classes: {}'.format(unknown, ', '.join(CLASSES)))
    max_jets = args.max_jets_per_source if args.max_jets_per_source and args.max_jets_per_source > 0 else None

    if args.self_test:
        print('*** --self-test: this is a plumbing check, not a real central-vs-ours comparison ***')

    os.makedirs(args.outdir, exist_ok=True)

    results = read_all_classes(args.central_path, args.our_output_path, args.our_card,
                                classes, max_jets, apply_selection=not args.no_selection)

    header = '{:<16}{:<24}{:>10}{:>10}{:>10}{:>10}{:>10}'.format(
        'class', 'source', 'njets', 'min', 'p1', 'p99', 'max')
    print(header)
    print('-' * len(header))
    for name in classes:
        ours, central = results[name]
        for key, _, _ in KINEMATICS:
            print_stats(name, 'ours ({}) {}'.format(args.our_card, key), VALUE_FN[key](ours))
            print_stats(name, 'central JetClass-II {}'.format(key), VALUE_FN[key](central))

    for key, xlabel, bin_range in KINEMATICS:
        out = os.path.join(args.outdir, '{}_all_classes.png'.format(key))
        make_grid(results, classes, key, xlabel, bin_range, out)
