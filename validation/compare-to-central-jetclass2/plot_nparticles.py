#!/usr/bin/env python3

'''Compare the "number of particles per jet" distribution of our own JetClass-II
production to the published JetClass-II dataset, per class, both for the total count
and split by particle type.

The JetClass-II sibling of ../compare-to-central-jetclass/plot_nparticles.py: same
purpose and style, adapted to the different data format and class scheme.

- The published dataset ships as .parquet grouped by topology rather than by physics
  process, and every file carries an integer jet_label column instead of one label per
  file. FatJetMatching.h's labels_ vector is the authoritative index-to-name mapping,
  which our own jet_label branch uses too.
- The 3- and 4-prong topology is out of scope: neither downloaded nor produced here.
  QCD is kept as one combined class, as in JetClass-I. Of the two-prong flavour labels
  only the flavour-diagonal ones are plotted: the mixed ones are reachable only from a
  charged resonance, and only the neutral one is generated here. The two semi-leptonic
  ditau classes are merged into one panel, purely so the grid fits on two rows; the
  underlying labels are untouched.
- Our own production has no per-class files either. The QCD class is sourced from the
  QCD process only, not from the signal process' QCD-fallback jets, which have
  different kinematics and would bias the comparison; the signal classes come from the
  signal process only, each selected by its own exact label values.
- JetClass-II's published files do not bake in the narrow pT and |eta| window
  JetClass-I's do; see plot_jet_kinematics.py for what they actually contain.
'''

import os
import sys
import glob
import argparse

import numpy as np
import awkward as ak
import matplotlib.pyplot as plt
import uproot
import pyarrow.parquet as pq

# same house style as ../compare-to-central-jetclass/plot_nparticles.py
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
DEFAULT_OUR_OUTPUT_PATH = '/eos/user/l/llambrec/jetclass/output_jetclass2_1M'
DEFAULT_OUR_CARD = 'onlyFatJet'  # matches what we submitted production with (includes PU, like the official dataset)
DEFAULT_CENTRAL_PATH = '/eos/user/l/llambrec/jetclass/JetClass2/val'
TREE_NAME = 'tree'
# central files are ~100k jets each, our own production targets ~1M jets
# per class too - default to no cap (read everything available); override
# for a quicker/lighter run
DEFAULT_MAX_JETS_PER_SOURCE = None

# jet_label index of every two-prong resonance flavor, per
# delphes_analyzers/FatJetMatching.h's labels_ vector (indices 0-14) - the
# single source of truth this mirrors. Includes the 5 flavor-mixed indices
# (X_bc..X_sq) for reference even though CLASS_INFO below never uses them
# (see module docstring: charged-resonance-only, not generated/plotted).
RES2P_LABEL_INDEX = {
    'X_bb': 0, 'X_cc': 1, 'X_ss': 2, 'X_qq': 3,
    'X_bc': 4, 'X_cs': 5, 'X_bq': 6, 'X_cq': 7, 'X_sq': 8,
    'X_gg': 9, 'X_ee': 10, 'X_mm': 11, 'X_tauhtaue': 12, 'X_tauhtaum': 13, 'X_tauhtauh': 14,
}
QCD_LABEL_RANGE = range(161, 188)  # all 27 QCD_* flavor labels, combined into one class

# (class name -> (jet_label indices making up this class, central file
# prefix, our own jetclass2/<proc> subdirectory)) - QCD and the Res2P
# flavors pull from two DIFFERENT underlying sources (see module docstring
# for why train_higgs2p's own QCD-fallback jets are deliberately excluded
# from the QCD class). 'X_tauhtaul' combines the X_tauhtaue and X_tauhtaum
# jet_label values into one plotted class (see module docstring) - order
# here is the plotting order (QCD first, then the 9 diagonal flavors in
# labels_ vector order, tauhtaue+tauhtaum merged at that point).
CLASSES = ['QCD', 'X_bb', 'X_cc', 'X_ss', 'X_qq', 'X_gg', 'X_ee', 'X_mm', 'X_tauhtaul', 'X_tauhtauh']
CLASS_INFO = {'QCD': (set(QCD_LABEL_RANGE), 'QCD', 'train_qcd')}
for _name in ('X_bb', 'X_cc', 'X_ss', 'X_qq', 'X_gg', 'X_ee', 'X_mm', 'X_tauhtauh'):
    CLASS_INFO[_name] = ({RES2P_LABEL_INDEX[_name]}, 'Res2P', 'train_higgs2p')
CLASS_INFO['X_tauhtaul'] = ({RES2P_LABEL_INDEX['X_tauhtaue'], RES2P_LABEL_INDEX['X_tauhtaum']}, 'Res2P', 'train_higgs2p')

PARTICLE_TYPES = [
    ('charged_hadron', 'Charged hadrons per jet', 'part_isChargedHadron'),
    ('neutral_hadron', 'Neutral hadrons per jet', 'part_isNeutralHadron'),
    ('photon',         'Photons per jet',         'part_isPhoton'),
    ('electron',       'Electrons per jet',       'part_isElectron'),
    ('muon',           'Muons per jet',           'part_isMuon'),
]
NPARTICLES_BRANCH = 'jet_nparticles'
CORE_BRANCHES = [NPARTICLES_BRANCH, 'jet_pt', 'jet_eta', 'jet_label'] + [b for _, _, b in PARTICLE_TYPES]

# JetClass-II's own baked-in selection (established by directly inspecting
# the downloaded central files' jet_pt/jet_eta range - see
# plot_jet_kinematics.py's own module docstring): a hard pT floor matching
# Delphes' own JetPTMin=200 on the offline card, no upper bound, and the
# offline card's own |eta|<2.5 acceptance. Different from JetClass-I's
# fixed [500,1000] GeV window (see ../compare-to-central-jetclass/
# plot_nparticles.py's own SELECTION_* comment) - JetClass-II spans a much
# broader boosted-jet pT range by design (many mass points/pThat bins).
SELECTION_PT_MIN = 200.0
SELECTION_ETA_MAX = 2.5


def selection_mask(jet_pt, jet_eta):
    '''Boolean mask for the jet pT and |eta| selection, or all-true when it is disabled.
    '''
    return (jet_pt > SELECTION_PT_MIN) & (np.abs(jet_eta) < SELECTION_ETA_MAX)


def our_files(output_path, proc, card):
    '''The ntuples of our own production for one process.'''
    d = os.path.join(output_path, 'jetclass2', proc, card)
    return sorted(glob.glob(os.path.join(d, 'ntuple_*.root')))


def central_files(central_path, prefix):
    '''The published dataset's files for one topology family.'''
    return sorted(glob.glob(os.path.join(central_path, '{}_*.parquet'.format(prefix))))


def read_root(files, branches, max_jets=None):
    '''Single-pass read of our own ntuples into one concatenated awkward record array.
    '''
    chunks = []
    total = 0
    for path in files:
        if max_jets is not None and total >= max_jets:
            break
        try:
            with uproot.open(path) as f:
                arr = f[TREE_NAME].arrays(branches, library='ak')
        except Exception as e:
            print('  WARNING: could not read {} ({}: {})'.format(path, type(e).__name__, e), file=sys.stderr)
            continue
        chunks.append(arr)
        total += len(arr)
    result = ak.concatenate(chunks) if chunks else ak.Array({b: [] for b in branches})
    if max_jets is not None and len(result) > max_jets:
        result = result[:max_jets]
    return result


def read_parquet(files, branches, max_jets=None):
    '''read_root()'s counterpart for the published .parquet files.'''
    chunks = []
    total = 0
    for path in files:
        if max_jets is not None and total >= max_jets:
            break
        try:
            table = pq.read_table(path, columns=branches)
        except Exception as e:
            print('  WARNING: could not read {} ({}: {})'.format(path, type(e).__name__, e), file=sys.stderr)
            continue
        chunks.append(ak.from_arrow(table))
        total += table.num_rows
    result = ak.concatenate(chunks) if chunks else ak.Array({b: [] for b in branches})
    if max_jets is not None and len(result) > max_jets:
        result = result[:max_jets]
    return result


def bucket_by_class(arr, class_names, apply_selection=True):
    '''Split one source's flat record array into the requested classes, by exact label value.
    '''
    jet_pt = ak.to_numpy(arr['jet_pt'])
    jet_eta = ak.to_numpy(arr['jet_eta'])
    jet_label = ak.to_numpy(arr['jet_label'])
    sel = selection_mask(jet_pt, jet_eta) if apply_selection else np.ones(len(arr), dtype=bool)
    result = {}
    for name in class_names:
        labels, _, _ = CLASS_INFO[name]
        label_mask = np.isin(jet_label, list(labels))
        result[name] = arr[sel & label_mask]
    return result


def read_all_classes(central_path, our_output_path, our_card, class_names, max_jets_per_source, apply_selection=True):
    '''Read every distinct source exactly once and bucket it into the requested classes.
    '''
    central_cache, our_cache = {}, {}
    results = {}
    for name in class_names:
        labels, central_prefix, our_proc = CLASS_INFO[name]
        if central_prefix not in central_cache:
            print('reading central {} files...'.format(central_prefix))
            raw = read_parquet(central_files(central_path, central_prefix), CORE_BRANCHES, max_jets_per_source)
            central_cache[central_prefix] = bucket_by_class(
                raw, [n for n in class_names if CLASS_INFO[n][1] == central_prefix], apply_selection)
        if our_proc not in our_cache:
            print('reading our {} files...'.format(our_proc))
            raw = read_root(our_files(our_output_path, our_proc, our_card), CORE_BRANCHES, max_jets_per_source)
            our_cache[our_proc] = bucket_by_class(
                raw, [n for n in class_names if CLASS_INFO[n][2] == our_proc], apply_selection)
        results[name] = (our_cache[our_proc][name], central_cache[central_prefix][name])
    return results


def make_plot(ax, label, our_vals, central_vals, xlabel):
    '''One class' overlaid step-histogram comparison, ours against central.'''
    both = np.concatenate([our_vals, central_vals]) if len(our_vals) and len(central_vals) else \
        (our_vals if len(our_vals) else central_vals)
    if len(both) == 0:
        ax.text(0.5, 0.5, '{}: no data'.format(label), ha='center', va='center', transform=ax.transAxes)
        return
    hi = int(np.ceil(np.percentile(both, 99.5))) + 1
    bins = np.arange(-0.5, hi + 1.5, 1)

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


def make_grid(results, classes, key, xlabel, outpath, value_fn):
    '''One small-multiples figure with every requested class, for one quantity.'''
    ncols = 5
    nrows = (len(classes) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 6 * nrows))
    axes = np.atleast_1d(axes).flatten()
    for ax, name in zip(axes, classes):
        ours, central = results[name]
        make_plot(ax, name, value_fn(ours), value_fn(central), xlabel)
    for ax in axes[len(classes):]:
        ax.axis('off')
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print('wrote {}'.format(outpath))


def total_nparticles(arr):
    '''Total particles per jet.'''
    return ak.to_numpy(arr[NPARTICLES_BRANCH]) if len(arr) else np.array([], dtype=np.int64)


def particle_type_count(arr, branch):
    '''Particles of one type per jet.'''
    return ak.to_numpy(ak.sum(arr[branch], axis=1)) if len(arr) else np.array([], dtype=np.int64)


def print_stats(name, source, vals):
    '''Print each class' mean and median for both datasets.'''
    if len(vals) == 0:
        print('{:<16}{:<24}{:>10}'.format(name, source, 'no data'))
        return
    print('{:<16}{:<24}{:>10}{:>10.2f}{:>10.1f}{:>10.2f}'.format(
        name, source, len(vals), vals.mean(), np.median(vals), vals.std()))


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
        help='comma-separated class names (default: all 10 - QCD + 9 diagonal Res2P flavors,'
             ' see CLASSES/CLASS_INFO)')
    parser.add_argument('--max-jets-per-source', type=int, default=DEFAULT_MAX_JETS_PER_SOURCE,
        help='cap on jets read per underlying SOURCE (train_qcd/train_higgs2p/QCD/Res2P files),'
             ' not per final class - default: no cap (read everything available)')
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR,
        help='directory to write plots into (default: {})'.format(DEFAULT_OUTDIR))
    parser.add_argument('--self-test', action='store_true',
        help='label the run as a plumbing self-test (e.g. --central-path pointed at our own'
             ' output) rather than a real central-vs-ours comparison')
    parser.add_argument('--no-selection', action='store_true',
        help='skip the pT>{:g} GeV / |eta|<{:g} selection (default: applied to both sources -'
             ' see SELECTION_PT_MIN/SELECTION_ETA_MAX\'s own comment for why)'.format(
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

    header = '{:<16}{:<24}{:>10}{:>10}{:>10}{:>10}'.format(
        'class', 'source', 'njets', 'mean', 'median', 'std')
    print(header)
    print('-' * len(header))
    for name in classes:
        ours, central = results[name]
        print_stats(name, 'ours ({})'.format(args.our_card), total_nparticles(ours))
        print_stats(name, 'central JetClass-II', total_nparticles(central))

    make_grid(results, classes, 'total', 'Particles per jet',
              os.path.join(args.outdir, 'nparticles_all_classes.png'), total_nparticles)
    for key, xlabel, branch in PARTICLE_TYPES:
        make_grid(results, classes, key, xlabel,
                  os.path.join(args.outdir, 'nparticles_{}_all_classes.png'.format(key)),
                  lambda arr, branch=branch: particle_type_count(arr, branch))
