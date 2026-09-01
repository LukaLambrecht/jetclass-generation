#!/usr/bin/env python3

'''
Compares jet-level kinematics (jet_pt, jet_eta) of our own production
(offline conditions, onlyFatJetNoPU/JetClassI card) to the
centrally-available JetClass dataset, per process/class - same style as
plot_nparticles.py (see that module's docstring for the full context), but
checking a different, more direct question: the JetClass paper (Qu, Li,
Qian 2022) states jets are selected with "transverse momentum in 500-1000
GeV and pseudorapidity |eta| < 2", but it's unclear whether that window is
actually baked into the released dataset files themselves, or only applied
at some later analysis stage. Plotting the ACTUAL jet_pt/jet_eta
distributions found in the central files answers this directly: a hard
edge at those values means the cut IS in the files; a smooth tail past
them means it's a later-stage cut and the files themselves are broader.

Deliberately uses fixed (not per-process, not percentile-cropped) bin
ranges that extend well past the paper's stated window on both sides, so
any real edge (or lack of one) is directly visible rather than potentially
hidden by auto-ranging.

Reuses plot_nparticles.py's file-discovery/CLI-default plumbing directly
(same --central-path/--our-output-path/etc. semantics) rather than
duplicating it.

Usage:
  python3 plot_jet_kinematics.py
  python3 plot_jet_kinematics.py --our-output-path /eos/user/l/llambrec/jetclass/output_jetclass1_5M_sync --our-card JetClassI
'''

import os
import sys
import argparse

import numpy as np
import matplotlib.pyplot as plt
import uproot

from plot_nparticles import (
    our_files, central_files, normalize_proc, selection_mask,
    OUR_COLOR, CENTRAL_COLOR, TREE_NAME,
    DEFAULT_OUR_OUTPUT_PATH, DEFAULT_OUR_CARD, DEFAULT_CENTRAL_PATH,
    DEFAULT_CENTRAL_PATTERN, DEFAULT_PROCS, DEFAULT_MAX_JETS_PER_SOURCE,
    DEFAULT_OUTDIR, SELECTION_PT_RANGE, SELECTION_ETA_MAX,
)

THISDIR = os.path.dirname(os.path.abspath(__file__))

# (result-dict key/branch name, axis label, (bin_lo, bin_hi, nbins)) - the
# range is fixed and deliberately wider than the paper's stated selection
# window (pT in [500,1000] GeV, |eta|<2) so an edge at those values (or its
# absence) is directly visible rather than potentially cropped out
KINEMATICS = [
    ('jet_pt',  'Jet pT [GeV]', (300, 1500, 60)),
    ('jet_eta', 'Jet eta',      (-3, 3, 60)),
]


def read_kinematics(files, max_jets=None, apply_selection=True):
    '''
    Same semantics as plot_nparticles.read_jet_data() - single-pass read,
    capped at max_jets SELECTED jets. apply_selection (default on, see
    plot_nparticles.selection_mask()'s own comment) restricts both sources
    to the same pT/eta window before capping/plotting - note this means
    the resulting plot's x-axis range (still fixed wide, see KINEMATICS
    above) will show both curves hard-edged at the same values by
    construction; what's still informative is whether the SHAPE within
    that shared window matches, not the edges themselves (already
    established separately, with --no-selection, before this option existed).
    '''
    branches = [key for key, _, _ in KINEMATICS]
    chunks = {key: [] for key in branches}
    total = 0
    for path in files:
        if max_jets is not None and total >= max_jets:
            break
        try:
            with uproot.open(path) as f:
                arrs = f[TREE_NAME].arrays(branches, library='np')
        except Exception as e:
            print('  WARNING: could not read {} ({}: {})'.format(path, type(e).__name__, e), file=sys.stderr)
            continue
        mask = selection_mask(arrs['jet_pt'], arrs['jet_eta']) if apply_selection else slice(None)
        for key in branches:
            chunks[key].append(arrs[key][mask])
        total += len(chunks[branches[0]][-1])

    result = {}
    for key in branches:
        arr = np.concatenate(chunks[key]) if chunks[key] else np.array([], dtype=np.float64)
        if max_jets is not None and len(arr) > max_jets:
            arr = arr[:max_jets]
        result[key] = arr
    return result


def make_plot(ax, label, our_vals, central_vals, xlabel, bin_range):
    '''Same look as plot_nparticles.make_plot(), but fixed-range float bins instead of integer ones.'''
    lo, hi, nbins = bin_range
    bins = np.linspace(lo, hi, nbins + 1)

    if len(our_vals) == 0 and len(central_vals) == 0:
        ax.text(0.5, 0.5, '{}: no data'.format(label), ha='center', va='center', transform=ax.transAxes)
        return

    max_height = 0.0
    for vals, series_label, color in ((central_vals, 'central JetClass', CENTRAL_COLOR),
                                       (our_vals, 'ours (offline)', OUR_COLOR)):
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


def make_grid(results, procs, key, xlabel, bin_range, outpath):
    ncols = 5
    nrows = (len(procs) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 6 * nrows))
    axes = np.atleast_1d(axes).flatten()
    for ax, proc in zip(axes, procs):
        ours, central = results[proc]
        make_plot(ax, proc, ours[key], central[key], xlabel, bin_range)
    for ax in axes[len(procs):]:
        ax.axis('off')
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print('wrote {}'.format(outpath))


def print_stats(proc, source, vals):
    '''
    min/1st-percentile/99th-percentile/max, not mean/median/std (unlike
    plot_nparticles.py's own print_stats) - the question here is whether
    there's a hard edge at a specific value, which percentiles/extrema
    show directly and a mean would just wash out.
    '''
    if len(vals) == 0:
        print('{:<14}{:<20}{:>10}'.format(proc, source, 'no data'))
        return
    print('{:<14}{:<20}{:>10}{:>10.2f}{:>10.2f}{:>10.2f}{:>10.2f}'.format(
        proc, source, len(vals), vals.min(), np.percentile(vals, 1), np.percentile(vals, 99), vals.max()))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--central-path', default=DEFAULT_CENTRAL_PATH,
        help='directory containing central JetClass ROOT files (default: {})'.format(DEFAULT_CENTRAL_PATH))
    parser.add_argument('--central-pattern', default=DEFAULT_CENTRAL_PATTERN,
        help='glob pattern (relative to --central-path, "{{proc}}" substituted) matching that'
             ' process\'s central files (default: {!r})'.format(DEFAULT_CENTRAL_PATTERN))
    parser.add_argument('--our-output-path', default=DEFAULT_OUR_OUTPUT_PATH,
        help='our own production output directory (default: {})'.format(DEFAULT_OUR_OUTPUT_PATH))
    parser.add_argument('--our-card', default=DEFAULT_OUR_CARD,
        help='which of our Delphes cards to compare (default: {})'.format(DEFAULT_OUR_CARD))
    parser.add_argument('--procs', default=DEFAULT_PROCS,
        help='comma-separated jetclass1 process names (default: all 10)')
    parser.add_argument('--max-jets-per-source', type=int, default=DEFAULT_MAX_JETS_PER_SOURCE,
        help='cap on jets read per (process, source) (default: {:,})'.format(DEFAULT_MAX_JETS_PER_SOURCE))
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR,
        help='directory to write plots into (default: {})'.format(DEFAULT_OUTDIR))
    parser.add_argument('--self-test', action='store_true',
        help='label the run as a plumbing self-test rather than a real comparison')
    parser.add_argument('--no-selection', action='store_true',
        help='skip the pT in [{:g},{:g}] GeV / |eta|<{:g} selection (default: applied to both'
             ' sources) - pass this to see the RAW, unselected kinematics (e.g. to check for'
             ' a hard edge in the first place, as originally done to find these values)'.format(
                 SELECTION_PT_RANGE[0], SELECTION_PT_RANGE[1], SELECTION_ETA_MAX))
    args = parser.parse_args()

    procs = [normalize_proc(p.strip()) for p in args.procs.split(',') if p.strip()]
    if not procs:
        raise Exception('--procs did not contain any process names')
    max_jets = args.max_jets_per_source if args.max_jets_per_source and args.max_jets_per_source > 0 else None

    if args.self_test:
        print('*** --self-test: this is a plumbing check, not a real central-vs-ours comparison ***')

    os.makedirs(args.outdir, exist_ok=True)

    header = '{:<14}{:<20}{:>10}{:>10}{:>10}{:>10}{:>10}'.format(
        'proc', 'source', 'njets', 'min', 'p1', 'p99', 'max')
    print(header)
    print('-' * len(header))

    results = {}
    for proc in procs:
        ours = read_kinematics(our_files(args.our_output_path, proc, args.our_card), max_jets,
                                apply_selection=not args.no_selection)
        central = read_kinematics(central_files(args.central_path, proc, args.central_pattern), max_jets,
                                   apply_selection=not args.no_selection)
        results[proc] = (ours, central)
        for key, _, _ in KINEMATICS:
            print_stats(proc, 'ours ({}) {}'.format(args.our_card, key), ours[key])
            print_stats(proc, 'central JetClass {}'.format(key), central[key])

    for key, xlabel, bin_range in KINEMATICS:
        out = os.path.join(args.outdir, '{}_all_processes.png'.format(key))
        make_grid(results, procs, key, xlabel, bin_range, out)
