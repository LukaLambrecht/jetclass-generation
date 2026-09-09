#!/usr/bin/env python3

'''
Compares the "number of particles per jet" distribution between OFFLINE
and HLT reconstruction of the SAME jets, per jet class - the compare-hlt-
to-offline sibling of ../compare-to-central-jetclass2/plot_nparticles.py:
same 10-class grid (QCD aggregated into one class, X_tauhtaue/X_tauhtaum
merged into one "X_tauhtaul" class, the flavor-mixed two-prong labels
excluded - see CLASS_SUFFIXES/CLASSES), but comparing Offline vs HLT
reconstruction of ONE production (via a PAIRED ntuple - see ntuple_io.py)
instead of comparing our production against the published central dataset.

Works with EITHER schema ntuple_io.py knows about (see its own module
docstring) - whatever `files` actually are is detected automatically and
needs no flag:

  - "ours": jet_label directly (index 0-14 for the 10 Res2P classes -
    RES2P_LABEL_INDEX - index 161-187 for QCD - QCD_LABEL_RANGE - see
    delphes_analyzers/FatJetMatching.h's own labels_ vector).
  - "fullsim": each raw fj_label value's resolved SUFFIX name (bb/cc/ss/
    .../tauhtauh - see ntuple_io.resolve_fullsim_label_names()) matched
    against the identical CLASS_SUFFIXES scheme "ours" uses, rather than
    by fj_label index directly (fullsim's own index list doesn't
    correspond to ours) - a name-based match, not a claim that a given
    suffix comes from the same underlying resonance (neutral vs charged)
    in both datasets.

`files` is just every ntuple to pool together and then bucket by class,
same as ../plot_pt.py/plot_composition.py - no separate "QCD source"/
"Higgs source" arguments: since every jet is bucketed by its OWN label
regardless of which file it came from, one combined glob (or several)
covering every process/sample you want represented is enough - e.g. an
"ours" production's train_qcd AND train_higgs2p ntuples together, or one
fullsim sample's files, or several fullsim samples' files at once. (A
train_higgs2p production's own QCD-fallback jets - see makeNtuples.C - do
end up in the QCD class alongside a train_qcd file's jets if you pool
both; if that's not wanted for a given comparison, simply don't include
that file in `files`.)

Offline vs HLT correspondence and the actual per-jet particle counting both
come from ntuple_io.load_nparticles() - the lightest read ntuple_io.py
offers, since this script never needs any per-particle CONTENT, just how
many there are per jet ("ours" has this precomputed as a flat branch
already; fullsim needs one small branch per underlying collection).

Output: one multi-axes ("small multiples") figure, 2 rows x 5 columns,
all 10 classes together:
  nparticles_offline_vs_hlt_all_classes.png

Usage:
  # our own paired (onlyFatJet+onlyFatJetHLT) production - every process pooled together
  python3 plot_nparticles.py \\
      '/eos/user/l/llambrec/jetclass/output_jetclass2_5M/jetclass2/*/onlyFatJet+onlyFatJetHLT/ntuple_*.root'

  # the real FullSim/scouting reference dataset instead
  python3 plot_nparticles.py \\
      '/eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/QCD_PT-mixed_TuneCP5_13p6TeV_pythia8_new/dnnTuples_nanov15_*.root' \\
      '/eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/H0HpHm_mixed_new/dnnTuples_nanov15_*.root' \\
      --outdir output_plots/fullsim

  # a subset of classes / capped statistics
  python3 plot_nparticles.py 'FILES...' --classes QCD,X_bb,X_cc --max-jets 200000
'''

import os
import sys
import glob
import argparse

import numpy as np
import uproot
import matplotlib.pyplot as plt

THISDIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(THISDIR))  # validation/ - for ntuple_io
import ntuple_io as nio

# same house style as ../compare-to-central-jetclass2/plot_nparticles.py
plt.rcParams.update({
    'font.size': 15,
    'axes.labelsize': 18,
    'xtick.labelsize': 14,
    'ytick.labelsize': 14,
    'legend.fontsize': 13,
})
OFFLINE_COLOR = 'dodgerblue'
HLT_COLOR = 'darkorchid'

DEFAULT_OUTDIR = os.path.join(THISDIR, 'output_plots')
TREE_NAME = 'tree'

# jet_label index of every two-prong resonance flavor, per
# delphes_analyzers/FatJetMatching.h's labels_ vector (indices 0-14) -
# "ours"-schema only, identical to
# ../compare-to-central-jetclass2/plot_nparticles.py's own RES2P_LABEL_INDEX
RES2P_LABEL_INDEX = {
    'X_bb': 0, 'X_cc': 1, 'X_ss': 2, 'X_qq': 3,
    'X_bc': 4, 'X_cs': 5, 'X_bq': 6, 'X_cq': 7, 'X_sq': 8,
    'X_gg': 9, 'X_ee': 10, 'X_mm': 11, 'X_tauhtaue': 12, 'X_tauhtaum': 13, 'X_tauhtauh': 14,
}
QCD_LABEL_RANGE = range(161, 188)  # "ours"-schema only: all 27 QCD_* flavor labels

# The 10-class scheme itself, schema-agnostic: each class is a SET OF SUFFIX
# NAMES (bb/cc/ss/.../tauhtauh - the common vocabulary both FatJetMatching.h's
# labelH2p_-style X_* names and DNNTuples' own labelH2p_ share, see
# ntuple_io.py) - X_tauhtaul merges X_tauhtaue+X_tauhtaum (module docstring);
# every OTHER suffix either scheme's own H2p-like list carries (X_bc/X_cs/
# X_bq/X_cq/X_sq for "ours", "bc"/"bs"/"cs" for fullsim) is simply not in
# this dict at all, i.e. excluded - same effect as
# ../compare-to-central-jetclass2/plot_nparticles.py's own exclusion of the
# 5 flavor-mixed labels, just expressed once, by name, for both schemas.
CLASS_SUFFIXES = {
    'X_bb': {'bb'}, 'X_cc': {'cc'}, 'X_ss': {'ss'}, 'X_qq': {'qq'},
    'X_gg': {'gg'}, 'X_ee': {'ee'}, 'X_mm': {'mm'},
    'X_tauhtaul': {'tauhtaue', 'tauhtaum'}, 'X_tauhtauh': {'tauhtauh'},
}
CLASSES = ['QCD', 'X_bb', 'X_cc', 'X_ss', 'X_qq', 'X_gg', 'X_ee', 'X_mm', 'X_tauhtaul', 'X_tauhtauh']


def expand_files(patterns):
    '''Glob-expand each pattern (quote globs on the command line so THIS expands them,
    not the shell) - a pattern matching nothing is kept as a literal path, so a plain
    existing file still works and a genuine typo fails loudly (on the actual read)
    instead of silently vanishing here. Same as ../plot_pt.py/plot_composition.py's
    own expand_files().'''
    files = []
    for pattern in patterns:
        matched = sorted(glob.glob(pattern))
        files.extend(matched if matched else [pattern])
    if not files:
        raise ValueError('no files matched: {}'.format(patterns))
    return files


def read_jet_label(files):
    '''"ours"-schema only: plain jet_label read (flat int branch) alongside
    ntuple_io.load_particles()'s own read of the same `files` (see class_masks()) - two
    independent uproot.concatenate calls over the identical, already-fixed file list
    stay aligned element-wise (uproot preserves file order deterministically).'''
    paths = ['{}:{}'.format(f, TREE_NAME) for f in files]
    return uproot.concatenate(paths, filter_name=['jet_label'], library='np')['jet_label']


def class_masks(files, class_names):
    '''
    Returns ({class_name: boolean mask}, njets) for `files` (a fixed list, pooling
    every jet together regardless of which file it came from) and the requested
    `class_names` - dispatches on ntuple_io.detect_schema(): "ours" matches each
    class's CLASS_SUFFIXES set by exact jet_label index (via RES2P_LABEL_INDEX/
    QCD_LABEL_RANGE); fullsim matches by each raw fj_label value's resolved SUFFIX
    name instead (see module docstring's "fullsim" bullet for why this is a name-based
    match, not a physical-origin one).
    '''
    schema = nio.detect_schema(files, treename=TREE_NAME)

    if schema == 'ours':
        jet_label = read_jet_label(files)
        masks = {}
        for name in class_names:
            if name == 'QCD':
                masks[name] = np.isin(jet_label, list(QCD_LABEL_RANGE))
            else:
                indices = [RES2P_LABEL_INDEX['X_' + s] for s in CLASS_SUFFIXES[name]]
                masks[name] = np.isin(jet_label, indices)
        return masks, len(jet_label)

    # fullsim: resolve each distinct observed fj_label value's own category (via its
    # co-occurring boolean flag, same approach as print_njets.py's read_one()) and,
    # for H2p values, its suffix name (via ntuple_io.resolve_fullsim_label_names()) -
    # then match classes by suffix, QCD by category alone (aggregating every QCD_*
    # subflavor regardless of suffix, exactly like "ours" does via QCD_LABEL_RANGE)
    values, category_flags, njets = nio.load_fullsim_raw_labels(files)
    value_to_category = {}
    for cat, flags in category_flags.items():
        in_cat = np.unique(values[flags])
        for v in in_cat:
            value_to_category[int(v)] = cat
    resolved_names = nio.resolve_fullsim_label_names(value_to_category)
    h2p_prefix = nio.FULLSIM_SUBLABEL_PREFIX['H2p']

    masks = {}
    for name in class_names:
        if name == 'QCD':
            masks[name] = category_flags['QCD']
            continue
        wanted = {v for v, n in resolved_names.items()
                  if n.startswith(h2p_prefix) and n[len(h2p_prefix):] in CLASS_SUFFIXES[name]}
        masks[name] = np.isin(values, list(wanted)) if wanted else np.zeros(njets, dtype=bool)
    return masks, njets


def read_all_classes(files, class_names, max_jets):
    '''
    One combined read of `files`: the requested classes' boolean masks (see
    class_masks()) plus ntuple_io.load_nparticles()'s own per-jet counts - the
    lightest possible read for this script's purposes, since it never needs any
    per-particle CONTENT, just how many there are per jet (see load_nparticles()'s own
    docstring: "ours" reads a precomputed flat int branch directly, no jagged data
    touched at all). has_hlt is False for a single-card "ours" production with no
    HLT/paired side at all (see ntuple_io.py), in which case this script falls back to
    plotting Offline only. A `max_jets` cap is applied post-read (simpler than the
    sibling script's own incremental per-file capping, at the cost of still reading
    everything - fine for the dataset sizes this is meant for).

    Unmatched jets (no HLT/scouting counterpart found at all - see
    ntuple_io.load_particles()'s own docstring) are excluded from hlt_nparticles
    entirely, not counted as "0 particles": an unmatched row's hlt_jet_nparticles is
    genuinely 0 (empty hlt_part_* vectors), but that's a different thing from "HLT
    reconstructed a real, near-empty jet" and would otherwise inflate the low end of
    the HLT distribution with jets HLT never even saw. njets/n_matched (returned
    alongside, for make_plot()'s own info text) still count every jet in the class,
    matched or not - only the HLT nparticles VALUES themselves are matched-only.

    Returns {class_name: (offline_nparticles, hlt_nparticles_or_None, njets, n_matched_or_None)}.
    '''
    masks, njets_total = class_masks(files, class_names)
    counts = nio.load_nparticles(files, treename=TREE_NAME)
    has_hlt = 'hlt_jet_nparticles' in counts
    if max_jets is not None and njets_total > max_jets:
        masks = {name: m[:max_jets] for name, m in masks.items()}
        counts = {k: v[:max_jets] for k, v in counts.items()}

    offline_all = counts['jet_nparticles']
    hlt_all = counts.get('hlt_jet_nparticles')
    matched_all = counts.get('hlt_matched')

    results = {}
    for name in class_names:
        mask = masks[name]
        offline_vals = offline_all[mask]
        if has_hlt:
            match_mask = matched_all[mask]
            n_matched = int(match_mask.sum())
            hlt_vals = hlt_all[mask][match_mask]
        else:
            n_matched = None
            hlt_vals = None
        results[name] = (offline_vals, hlt_vals, len(offline_vals), n_matched)
    return results


def make_plot(ax, label, offline_vals, hlt_vals, njets, n_matched):
    '''Same look as ../compare-to-central-jetclass2/plot_nparticles.py's own make_plot(),
    Offline vs HLT instead of central vs ours, plus a jet-count/match-rate caption.'''
    both = np.concatenate([offline_vals, hlt_vals]) if hlt_vals is not None and len(hlt_vals) else offline_vals
    if len(both) == 0:
        ax.text(0.5, 0.5, '{}: no data'.format(label), ha='center', va='center', transform=ax.transAxes)
        return
    hi = int(np.ceil(np.percentile(both, 99.5))) + 1
    bins = np.arange(-0.5, hi + 1.5, 1)

    series = [('Offline', offline_vals, OFFLINE_COLOR)]
    if hlt_vals is not None:
        series.append(('HLT', hlt_vals, HLT_COLOR))

    max_height = 0.0
    for series_label, vals, color in series:
        if len(vals) == 0:
            continue
        counts, _, _ = ax.hist(vals, bins=bins, density=True, histtype='step', linewidth=2, color=color,
                                label=series_label)
        if len(counts):
            max_height = max(max_height, counts.max())
    ax.set_yscale('log')
    ax.set_xlabel('Particles per jet')
    ax.set_ylabel('Number of jets (normalized)')
    if max_height > 0:
        bottom, _ = ax.get_ylim()
        ax.set_ylim(bottom, max_height * 25)

    info_lines = ['Jet class: {}'.format(label)]
    if n_matched is not None:
        info_lines.append('{} jets ({:.1f}% HLT matched)'.format(njets, 100.0 * n_matched / njets if njets else 0))
    else:
        info_lines.append('{} jets'.format(njets))
    for i, line in enumerate(info_lines):
        ax.text(0.03, 0.95 - 0.07 * i, line, transform=ax.transAxes, ha='left', va='top', fontsize=14)
    ax.legend(loc='upper right')


def make_grid(results, classes, outpath):
    '''One multi-axes ("small multiples") figure, 2 rows x 5 columns, all `classes` together -
    same layout as the sibling script's own make_grid().'''
    ncols = 5
    nrows = (len(classes) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 6 * nrows))
    axes = np.atleast_1d(axes).flatten()
    for ax, name in zip(axes, classes):
        offline_vals, hlt_vals, njets, n_matched = results[name]
        make_plot(ax, name, offline_vals, hlt_vals, njets, n_matched)
    for ax in axes[len(classes):]:
        ax.axis('off')
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print('wrote {}'.format(outpath))


def print_stats(name, source, vals):
    if vals is None:
        print('{:<16}{:<10}{:>10}'.format(name, source, 'n/a'))
        return
    if len(vals) == 0:
        print('{:<16}{:<10}{:>10}'.format(name, source, 'no data'))
        return
    print('{:<16}{:<10}{:>10}{:>10.2f}{:>10.1f}{:>10.2f}'.format(
        name, source, len(vals), vals.mean(), np.median(vals), vals.std()))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('files', nargs='+',
        help='ntuple file(s)/glob(s) to pool together and bucket by jet class - e.g. an'
             ' "ours" production\'s train_qcd AND train_higgs2p ntuples together, or one'
             ' or more fullsim samples\' files (see module docstring)')
    parser.add_argument('--classes', default=','.join(CLASSES),
        help='comma-separated class names (default: all 10 - QCD + 9 diagonal Res2P flavors,'
             ' see CLASSES/CLASS_SUFFIXES)')
    parser.add_argument('--max-jets', type=int, default=None,
        help='cap on jets read in total (across all `files`, before bucketing) - default:'
             ' no cap (read everything available)')
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR,
        help='directory to write plots into (default: {})'.format(DEFAULT_OUTDIR))
    args = parser.parse_args()

    classes = [c.strip() for c in args.classes.split(',') if c.strip()]
    unknown = [c for c in classes if c != 'QCD' and c not in CLASS_SUFFIXES]
    if unknown:
        raise Exception('unknown class(es) {} - known classes: {}'.format(unknown, ', '.join(CLASSES)))
    max_jets = args.max_jets if args.max_jets and args.max_jets > 0 else None

    os.makedirs(args.outdir, exist_ok=True)

    files = expand_files(args.files)
    results = read_all_classes(files, classes, max_jets)

    header = '{:<16}{:<10}{:>10}{:>10}{:>10}{:>10}'.format(
        'class', 'source', 'njets', 'mean', 'median', 'std')
    print(header)
    print('-' * len(header))
    for name in classes:
        offline_vals, hlt_vals, njets, n_matched = results[name]
        print_stats(name, 'offline', offline_vals)
        print_stats(name, 'hlt', hlt_vals)

    make_grid(results, classes, os.path.join(args.outdir, 'nparticles_offline_vs_hlt_all_classes.png'))
