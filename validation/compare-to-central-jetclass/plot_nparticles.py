#!/usr/bin/env python3

'''Compare the "number of particles per jet" distribution of our own production to the
centrally-available JetClass dataset, per process, both for the total count and split
by particle type.

Since both use the same gridpack and Delphes card, the two should match within
statistical uncertainties for every class; a mismatch would point at a real difference
in the pipeline rather than at the offline-against-HLT degradation other scripts cover.

The total is read from the jet_nparticles branch, which the ntuplizer always writes and
which is identical by construction to the length of the per-particle arrays, so this is
cheaper than summing a jagged array. The per-type counts have no such precomputed
branch and are the per-jet sum of the corresponding type flag.

Output is one small-multiples figure per quantity, all classes in one figure rather than
one file each, which is what a by-eye scan across classes needs.
'''

import os
import sys
import glob
import argparse

import numpy as np
import awkward as ak
import matplotlib.pyplot as plt
import uproot

REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(REPO_DIR)
from download_gridpack import normalize_proc

# same house style as testing/test-generation-time/plot_timing.py
plt.rcParams.update({
    'font.size': 15,
    'axes.labelsize': 18,
    'xtick.labelsize': 14,
    'ytick.labelsize': 14,
    'legend.fontsize': 13,
})
OUR_COLOR = 'darkorchid'
CENTRAL_COLOR = 'dodgerblue'

THISDIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTDIR = os.path.join(THISDIR, 'output_plots')
DEFAULT_OUR_OUTPUT_PATH = '/eos/user/l/llambrec/jetclass/output_jetclass1_10M'
DEFAULT_OUR_CARD = 'onlyFatJetNoPU'  # offline, no pileup - the card this comparison is about
# our local (partial, 5M-jet val split) central JetClass download - see
# module docstring/README for how it got there (JetClass_Pythia_val_5M.tar,
# extracted). Changes far less often than our own production output does,
# hence a real default here (unlike --our-output-path's sibling scripts,
# which all require --output-path explicitly - that one changes per run).
DEFAULT_CENTRAL_PATH = '/eos/user/l/llambrec/jetclass/JetClass/val_5M'
DEFAULT_CENTRAL_PATTERN = '{proc}_*.root'  # matches the public JetClass release's own file naming
DEFAULT_PROCS = 'HToBB,HToCC,HToGG,HToWW2Q1L,HToWW4Q,TTBar,TTBarLep,WToQQ,ZJetsToNuNu,ZToQQ'
DEFAULT_MAX_JETS_PER_SOURCE = 200_000  # central files are ~100k jets each - cap so this stays fast
NPARTICLES_BRANCH = 'jet_nparticles'
TREE_NAME = 'tree'
# (result-dict key, axis label, source branch) - the branch is a per-jet
# vector<bool>, summed to a per-jet count of that type (see read_jet_data())
PARTICLE_TYPES = [
    ('charged_hadron', 'Charged hadrons per jet', 'part_isChargedHadron'),
    ('neutral_hadron', 'Neutral hadrons per jet', 'part_isNeutralHadron'),
    ('photon',         'Photons per jet',         'part_isPhoton'),
    ('electron',       'Electrons per jet',       'part_isElectron'),
    ('muon',           'Muons per jet',           'part_isMuon'),
]
ALL_BRANCHES = [NPARTICLES_BRANCH, 'jet_pt', 'jet_eta'] + [branch for _, _, branch in PARTICLE_TYPES]

# JetClass paper (Qu, Li, Qian 2022) selection window - confirmed to be
# baked directly into the actual central JetClass files (see
# plot_jet_kinematics.py: central jet_pt/jet_eta show a hard edge at
# exactly these values in every class), not a later-analysis-stage cut as
# originally suspected. It's implemented in the jet-universe/
# jetclass_generation repo across TWO stages: makeNtuples.C applies
# `PT < 500 || |Eta| > 2` per job, and a separate postprocessing step
# (postprocessing/mergeTrees.C, run after run.sh, when merging per-job
# outputs into the final published files) applies the upper bound:
# `jet_pt > 500 && jet_pt < 1000`.
#
# Applied HERE (this comparison script) only, on both sources, so
# central-vs-ours stays apples-to-apples - deliberately NOT applied in our
# own production ntuplizer/run.sh, which keeps the broader (unselected)
# output for now (see --our-card's own default output, still the full
# unselected sample on disk).
SELECTION_PT_RANGE = (500.0, 1000.0)
SELECTION_ETA_MAX = 2.0


def selection_mask(jet_pt, jet_eta):
    '''Boolean mask for the jet pT and |eta| selection, or all-true when it is disabled.
    '''
    return (jet_pt > SELECTION_PT_RANGE[0]) & (jet_pt < SELECTION_PT_RANGE[1]) & (np.abs(jet_eta) < SELECTION_ETA_MAX)


def our_files(output_path, proc, card):
    '''The ntuples of our own production for one process.'''
    d = os.path.join(output_path, 'jetclass1', proc, 'precompiled', card)
    return sorted(glob.glob(os.path.join(d, 'ntuple_*.root')))


def central_files(central_path, proc, pattern):
    '''The central dataset's files for one process.'''
    return sorted(glob.glob(os.path.join(central_path, pattern.format(proc=proc))))


def read_jet_data(files, max_jets=None, apply_selection=True):
    '''Single-pass read of `files`, capped at max_jets selected jets, i.e. the cap applies
    after the selection.
    '''
    keys = [key for key, _, _ in PARTICLE_TYPES] + ['total', 'jet_pt', 'jet_eta']
    chunks = {key: [] for key in keys}
    total = 0
    for path in files:
        if max_jets is not None and total >= max_jets:
            break
        try:
            with uproot.open(path) as f:
                arrs = f[TREE_NAME].arrays(ALL_BRANCHES, library='ak')
        except Exception as e:
            print('  WARNING: could not read {} ({}: {})'.format(path, type(e).__name__, e), file=sys.stderr)
            continue
        jet_pt = ak.to_numpy(arrs['jet_pt'])
        jet_eta = ak.to_numpy(arrs['jet_eta'])
        mask = selection_mask(jet_pt, jet_eta) if apply_selection else slice(None)

        chunks['total'].append(ak.to_numpy(arrs[NPARTICLES_BRANCH])[mask])
        chunks['jet_pt'].append(jet_pt[mask])
        chunks['jet_eta'].append(jet_eta[mask])
        for key, _, branch in PARTICLE_TYPES:
            # part_is<Type> is a per-particle bool, one jagged list per jet -
            # summing it (True=1) over axis=1 gives the per-jet count of that type
            chunks[key].append(ak.to_numpy(ak.sum(arrs[branch], axis=1))[mask])
        total += len(chunks['total'][-1])

    result = {}
    for key, pieces in chunks.items():
        arr = np.concatenate(pieces) if pieces else np.array([], dtype=np.int64)
        if max_jets is not None and len(arr) > max_jets:
            arr = arr[:max_jets]
        result[key] = arr
    return result


def make_plot(ax, label, our_vals, central_vals, xlabel):
    '''One (process, quantity) overlaid step-histogram comparison, drawn onto `ax`.'''
    both = np.concatenate([our_vals, central_vals]) if len(our_vals) and len(central_vals) else \
        (our_vals if len(our_vals) else central_vals)
    if len(both) == 0:
        ax.text(0.5, 0.5, '{}: no data'.format(label), ha='center', va='center', transform=ax.transAxes)
        return
    # integer bins, edges at half-integers so each bin is centered on one
    # particle count - cap the range at the 99.5th percentile (combined) so
    # a handful of very high-multiplicity outlier jets don't wash out the bulk
    hi = int(np.ceil(np.percentile(both, 99.5))) + 1
    bins = np.arange(-0.5, hi + 1.5, 1)

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
    # headroom above the tallest bin (log scale: a multiplicative factor),
    # so the text box/legend (both pinned to the top corners below) never
    # overlaps the curves
    if max_height > 0:
        bottom, _ = ax.get_ylim()
        ax.set_ylim(bottom, max_height * 25)
    ax.text(0.03, 0.95, label, transform=ax.transAxes, ha='left', va='top', fontsize=14,
            bbox=dict(boxstyle='round', facecolor='white', edgecolor='gray', alpha=0.85))
    ax.legend(loc='upper right')


def make_grid(results, procs, key, xlabel, outpath):
    '''One small-multiples figure with every process together, for one quantity.'''
    ncols = 5
    nrows = (len(procs) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 6 * nrows))
    axes = np.atleast_1d(axes).flatten()
    for ax, proc in zip(axes, procs):
        ours, central = results[proc]
        make_plot(ax, proc, ours[key], central[key], xlabel)
    for ax in axes[len(procs):]:
        ax.axis('off')
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print('wrote {}'.format(outpath))


def print_stats(proc, source, vals):
    '''Print each process' mean and median for both datasets.'''
    if len(vals) == 0:
        print('{:<14}{:<20}{:>10}'.format(proc, source, 'no data'))
        return
    print('{:<14}{:<20}{:>10}{:>10.2f}{:>10.1f}{:>10.2f}'.format(
        proc, source, len(vals), vals.mean(), np.median(vals), vals.std()))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--central-path', default=DEFAULT_CENTRAL_PATH,
        help='directory containing central JetClass ROOT files (default: {} - our local'
             ' partial/val_5M download, see module docstring)'.format(DEFAULT_CENTRAL_PATH))
    parser.add_argument('--central-pattern', default=DEFAULT_CENTRAL_PATTERN,
        help='glob pattern (relative to --central-path, "{{proc}}" substituted with each'
             ' process name) matching that process\'s central files (default: {!r},'
             ' the public JetClass release\'s own naming)'.format(DEFAULT_CENTRAL_PATTERN))
    parser.add_argument('--our-output-path', default=DEFAULT_OUR_OUTPUT_PATH,
        help='our own production output directory (default: {})'.format(DEFAULT_OUR_OUTPUT_PATH))
    parser.add_argument('--our-card', default=DEFAULT_OUR_CARD,
        help='which of our Delphes cards to compare (default: {} - offline, no pileup)'.format(DEFAULT_OUR_CARD))
    parser.add_argument('--procs', default=DEFAULT_PROCS,
        help='comma-separated jetclass1 process names (default: all 10)')
    parser.add_argument('--max-jets-per-source', type=int, default=DEFAULT_MAX_JETS_PER_SOURCE,
        help='cap on jets read per (process, source) (default: {:,}) - central files are'
             ' large, this keeps runtime/memory bounded; set 0/negative for no cap'.format(
                 DEFAULT_MAX_JETS_PER_SOURCE))
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR,
        help='directory to write plots into (default: {})'.format(DEFAULT_OUTDIR))
    parser.add_argument('--self-test', action='store_true',
        help='label the run as a plumbing self-test (e.g. --central-path pointed at our own'
             ' output) rather than a real central-vs-ours comparison - only affects the'
             ' printed banner, not the plots/logic themselves')
    parser.add_argument('--no-selection', action='store_true',
        help='skip the pT in [{:g},{:g}] GeV / |eta|<{:g} selection (default: applied to both'
             ' sources - see SELECTION_PT_RANGE/SELECTION_ETA_MAX\'s own comment for why)'.format(
                 SELECTION_PT_RANGE[0], SELECTION_PT_RANGE[1], SELECTION_ETA_MAX))
    args = parser.parse_args()

    procs = [normalize_proc(p.strip()) for p in args.procs.split(',') if p.strip()]
    if not procs:
        raise Exception('--procs did not contain any process names')
    max_jets = args.max_jets_per_source if args.max_jets_per_source and args.max_jets_per_source > 0 else None

    if args.self_test:
        print('*** --self-test: this is a plumbing check, not a real central-vs-ours comparison ***')

    os.makedirs(args.outdir, exist_ok=True)

    header = '{:<14}{:<20}{:>10}{:>10}{:>10}{:>10}'.format(
        'proc', 'source', 'njets', 'mean', 'median', 'std')
    print(header)
    print('-' * len(header))

    results = {}
    for proc in procs:
        ours = read_jet_data(our_files(args.our_output_path, proc, args.our_card), max_jets,
                              apply_selection=not args.no_selection)
        central = read_jet_data(central_files(args.central_path, proc, args.central_pattern), max_jets,
                                 apply_selection=not args.no_selection)
        results[proc] = (ours, central)
        print_stats(proc, 'ours ({})'.format(args.our_card), ours['total'])
        print_stats(proc, 'central JetClass', central['total'])

    # one multi-axes ("all classes together") figure per quantity - total,
    # then each particle type - no per-process/individual files (see module
    # docstring)
    make_grid(results, procs, 'total', 'Particles per jet', os.path.join(args.outdir, 'nparticles_all_processes.png'))
    for key, xlabel, _ in PARTICLE_TYPES:
        make_grid(results, procs, key, xlabel, os.path.join(args.outdir, 'nparticles_{}_all_processes.png'.format(key)))
