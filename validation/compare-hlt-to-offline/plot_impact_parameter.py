#!/usr/bin/env python3

'''
Offline vs HLT track impact parameters of CHARGED particles, split per jet class.

Same comparison and same look as plot_nparticles.py - normalized step histograms,
Offline in blue and HLT in purple with sqrt(N) bands, one panel per jet class - but
for the per-particle track impact parameters instead of a per-jet count.

Three independent splits, one figure per combination:

  * VARIABLE   d0 (transverse) or dz (longitudinal), both in cm.
  * SELECTION  every charged particle in the jet, or only the LEADING charged
               particle (highest pT). The leading track is what a tagger leans on
               most, and pooling every particle lets a few very displaced ones
               dominate the tail, so the two answer different questions.
  * JET CLASS  one panel per class, as everywhere else in this directory.

  -> ip_<d0|dz>_<all|leading>_charged.png   (2 x 2 = 4 figures)

ONLY CHARGED PARTICLES are histogrammed: a neutral candidate has no track, so our
own ntuples store 0 for it (verified: 9 nonzero out of 420212 neutrals in a sample
file) and the fullsim reference has no neutral IP branch at all. Including them
would put a huge spike at exactly zero that is an artifact, not physics.

THE RANGE MATTERS HERE, more than for the other scripts. Offline and HLT populate
wildly different ranges: in a sample QCD file, 99.6% of HLT d0 values fall within
+-1 cm, while offline has an ~18% tail reaching +-1000 cm and beyond (dz out to
4600 cm). Those far values are not resolvable tracks in any useful sense. So each
variable is plotted in a symmetric window (--d0-range / --dz-range) and everything
outside is CLIPPED INTO THE EDGE BINS rather than dropped, for two reasons:

  * dropping would renormalize each side over only what it kept, making offline and
    HLT look more alike than they are - the tail is precisely part of the difference;
  * clipping keeps both sides normalized over all their charged particles, and the
    overflow shows up as an honest spike in the end bins.

Each panel also prints the percentage of each side that landed outside the window,
so the clipped fraction is never invisible. Use --no-clip to drop instead.

Usage:
  python3 plot_impact_parameter.py FILE_OR_GLOB_OR_DIR [...] --outdir DIR [options]

Examples:
  python3 plot_impact_parameter.py /eos/user/l/llambrec/jetclass/.../merged/jetclass2sb \\
      --outdir output_plots_ip --classes QCD
  python3 plot_impact_parameter.py 'ntuple_*.root' --outdir output_plots_ip --d0-range 0.2
'''

import os
import sys
import argparse

import numpy as np
import awkward as ak
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import ntuple_io as nio
import plot_style as ps
from plot_nparticles import CLASSES, class_masks, expand_files, TREE_NAME

# (key, part_ suffix, axis label, default half-width of the plotted window in cm).
# Defaults chosen from the data rather than by convention: they hold ~99% of the HLT
# side, which is the narrower of the two - see the module docstring.
# (key, part_ suffix, short axis label, long name for the figure title, default
# half-width of the plotted window in cm). The axis label is kept SHORT on purpose:
# the full description does not fit under a 6-inch panel and gets clipped at both
# ends, so it lives in the figure title instead.
VARIABLES = [
    ('d0', 'd0val', None, r'$d_{0}$ [cm]', 'Transverse impact parameter', 0.5),
    ('dz', 'dzval', None, r'$d_{z}$ [cm]', 'Longitudinal impact parameter', 1.0),
    # significance = value / its error, dimensionless. "ours" only: the reference
    # dataset stores a pre-computed dxysig/dzsig instead of the error, so there is
    # nothing to divide by there - those variables are skipped on that schema rather
    # than silently dividing by a zero-filled error (see ntuple_io.FULLSIM_*_FIELD).
    # +-20 from the data: it holds 89% of the offline and 99.5% of the HLT values.
    ('d0sig', 'd0val', 'd0err', r'$d_{0}/\sigma_{d_{0}}$',
     'Transverse impact parameter significance', 20.0),
    ('dzsig', 'dzval', 'dzerr', r'$d_{z}/\sigma_{d_{z}}$',
     'Longitudinal impact parameter significance', 20.0),
]

# (key, label, whether to keep only the highest-pT charged particle of each jet)
SELECTIONS = [
    ('all_charged', 'All charged particles', False),
    ('leading_charged', 'Leading charged particle', True),
]

NBINS = 60

# Paper-style y-range per variable, FIXED rather than derived from the data.
#
# The signal and the QCD samples are plotted by separate runs that never see each
# other's histograms, so a range taken from one of them (X_bb, say) would not match
# the other - and comparing an X->bb panel with a QCD panel is the whole point. These
# are hard-coded so every figure of a given variable has the same axis, whichever run
# produced it.
#
# Chosen from the measured densities of both samples (max of nominal+error, and the
# smallest non-zero bin):
#            signal max / min      QCD max / min
#   d0        15-23 / 0.0018       12-23 / 0.0041
#   dz        8.7-9.6 / 0.0009     7.0-11 / 0.0032
#   d0sig     0.32-0.36 / 9e-5     0.36-0.37 / 2.4e-4
#   dzsig     0.31-0.36 / 1.8e-4   0.34-0.37 / 2.1e-4
# with headroom above for the legend. A variable not listed here falls back to
# deriving the range from YLIM_REFERENCE_CLASS within its own run.
PAPER_YLIM = {
    'd0':    (5e-2, 5e2),
    'dz':    (2e-2, 2e2),
    'd0sig': (2e-3, 1e1),
    'dzsig': (2e-3, 1e1),
}
SUFFIXES = ['px', 'py', 'charge', 'd0val', 'dzval', 'd0err', 'dzerr']


def charged_values(data, prefix, suffix, leading_only, err_suffix=None):
    '''Per-jet jagged -> flat array of one variable's values for the charged particles
    of each jet, either all of them or only the highest-pT one.

    Returns (values, per_jet_index) where per_jet_index maps each returned value back
    to the jet it came from, so a class mask can be applied afterwards without
    re-doing the jagged work for every class.
    '''
    charge = data[prefix + 'charge']
    val = data[prefix + suffix][charge != 0]
    if err_suffix is not None:
        # significance: divide by the per-particle error. A non-positive error means
        # the track has no usable uncertainty, so that particle is dropped rather
        # than turned into an infinity.
        err = data[prefix + err_suffix][charge != 0]
        val = ak.where(err > 0, val / ak.where(err > 0, err, 1.0), np.nan)
    if not leading_only:
        counts = ak.to_numpy(ak.num(val, axis=1))
        flat = ak.to_numpy(ak.flatten(val, axis=None))
        return _finite(flat, np.repeat(np.arange(len(counts)), counts))

    pt = np.sqrt(data[prefix + 'px'] ** 2 + data[prefix + 'py'] ** 2)[charge != 0]
    # jets with no charged particle at all have no leading track to speak of and are
    # simply absent from the result (argmax on an empty list is undefined)
    jet_idx = np.arange(len(val))
    has_any = ak.to_numpy(ak.num(pt, axis=1)) > 0
    val, pt, jet_idx = val[has_any], pt[has_any], jet_idx[has_any]
    lead = ak.argmax(pt, axis=1, keepdims=True)
    return _finite(ak.to_numpy(ak.flatten(val[lead])), jet_idx)


def _finite(values, jet_index):
    '''Drop the entries a significance could not be computed for (marked NaN above),
    keeping the value -> jet index map aligned. A no-op for the plain IP variables.'''
    keep = np.isfinite(values)
    if keep.all():
        return values, jet_index
    return values[keep], jet_index[keep]


def new_accumulator(nbins, with_hlt):
    """Per-(variable, selection, class) running totals.

    The script reads ONE file at a time and adds into these, rather than
    concatenating every file's per-particle branches first: memory then does not
    scale with the size of the production. Summing per-file histograms is exactly
    histogramming the concatenation, and everything the panel needs is additive -
    the bin counts, the number of values (which is what the density is normalized
    by), the number outside the window, and the jet count.
    """
    a = {'off_counts': np.zeros(nbins), 'off_n': 0, 'off_out': 0, 'njets': 0}
    if with_hlt:
        a.update({'hlt_counts': np.zeros(nbins), 'hlt_n': 0, 'hlt_out': 0})
    return a


def accumulate(a, side, vals, edges, half_width, clip):
    """Add one file's values for one side ('off'/'hlt') into the accumulator."""
    if len(vals) == 0:
        return
    a[side + '_n'] += len(vals)
    a[side + '_out'] += int(np.count_nonzero(np.abs(vals) > half_width))
    plotted = np.clip(vals, edges[0], edges[-1]) if clip else vals
    counts, _ = np.histogram(plotted, bins=edges)
    a[side + '_counts'] += counts


def density_from_counts(counts, edges):
    """(nominal, error) of the density-normalized histogram from raw bin counts.

    Same definition as plot_style.poisson_density(), which takes values instead:
    counts / (total * bin_width), with the sqrt(N) error carried through the same
    scaling. `total` is the in-range sum, which is what the counts already are.
    """
    widths = np.diff(edges)
    total = counts.sum()
    if total == 0:
        z = np.zeros(len(counts), dtype=float)
        return z, z
    scale = 1.0 / (total * widths)
    return counts * scale, np.sqrt(counts) * scale


def draw_panel(ax, class_name, acc, edges, xlabel, clip, paper_style=False, ylim=None):
    '''One class's panel: Offline vs HLT, same style as plot_nparticles._draw_hist().'''
    has_hlt = 'hlt_counts' in acc
    if acc['off_n'] == 0 and (not has_hlt or acc['hlt_n'] == 0):
        ax.text(0.5, 0.5, '{}: no data'.format(ps.class_label(class_name)), ha='center',
                va='center', transform=ax.transAxes)
        return

    series = [('Offline', 'off', ps.OFFLINE_COLOR)]
    if has_hlt:
        series.append(('HLT', 'hlt', ps.HLT_COLOR))

    max_height = 0.0
    handles, labels, outside = [], [], []
    for series_label, side, color in series:
        if acc[side + '_n'] == 0:
            continue
        outside.append('{} outside: {:.1f}%'.format(
            series_label, 100.0 * acc[side + '_out'] / acc[side + '_n']))
        nominal, err = density_from_counts(acc[side + '_counts'], edges)
        e = edges
        if paper_style and clip:
            # hide the two end bins, which hold the clipped overflow and would
            # otherwise show as spikes. Note the normalization is NOT redone: the
            # remaining bins are exactly as in the PNG, just not drawn out to the
            # edges, so the paper figure is a sub-range of the same histogram rather
            # than a differently-normalized one.
            nominal, err, e = nominal[1:-1], err[1:-1], e[1:-1]
        handles.append(ps.step_band(ax, nominal, err, e, color))
        labels.append(series_label)
        if len(nominal):
            max_height = max(max_height, (nominal + err).max())

    ax.set_xlabel(xlabel)
    ax.set_ylabel('Particles (normalized)')
    ax.set_yscale('log')
    ps.apply_grid(ax)
    if ylim is not None:
        ax.set_ylim(*ylim)
    elif max_height > 0:
        bottom, _ = ax.get_ylim()
        ax.set_ylim(bottom, max_height * 40)

    info = ['Jet class: {}'.format(ps.class_label(class_name))]
    if not paper_style:
        info += ['{} jets'.format(acc['njets'])] + outside
    ps.draw_info(ax, info, fontsize=12)
    if handles:
        ps.legend_with_bands(ax, handles, labels, loc='upper right')


# In paper style every class of a given variable shares one y-range, so the panels
# can be compared by eye and placed side by side in a note. X_bb sets it: it is the
# broadest of the classes, so its range contains the others.
YLIM_REFERENCE_CLASS = 'X_bb'


def make_grid(results, classes, outpath, edges, xlabel, title, clip,
              paper_style=False, ylim=None):
    '''One figure, one panel per class - same small-multiples layout as the sibling
    scripts' own make_grid().'''
    ncols = min(5, len(classes))
    nrows = (len(classes) + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 6 * nrows))
    axes = np.atleast_1d(axes).flatten()
    drawn = {}
    for ax, name in zip(axes, classes):
        draw_panel(ax, name, results[name], edges, xlabel, clip, paper_style, ylim=ylim)
        drawn[name] = ax
    # pick up the shared range from the reference class if it was not handed in, and
    # apply it to every panel. Falls back to the widest panel when the reference
    # class is not part of this run (e.g. a QCD-only sample).
    if paper_style and ylim is None and drawn:
        ref = drawn.get(YLIM_REFERENCE_CLASS)
        ylim = ref.get_ylim() if ref is not None \
            else max((a.get_ylim() for a in drawn.values()), key=lambda lim: lim[1])
        for ax in drawn.values():
            ax.set_ylim(*ylim)
    for ax in axes[len(classes):]:
        ax.axis('off')
    # wrap=True so the title stays inside the canvas at ANY width: a full 10-class
    # grid is 5 panels wide and fits easily, but a --classes subset of one or two is
    # narrow enough to clip the title off at both ends otherwise.
    if paper_style:
        # no title in paper style - the caption carries it in a note
        fig.tight_layout()
    else:
        fig.suptitle(title, fontsize=15, wrap=True)
        # leave room for the suptitle rather than letting tight_layout overlap it
        fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print('wrote {}'.format(outpath))
    return ylim


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('files', nargs='+',
        help='ntuple file(s)/glob(s)/directory of ONE sample (same inputs as the other'
             ' scripts here - a directory is searched recursively)')
    parser.add_argument('--outdir', required=True, help='directory to write the figures into')
    parser.add_argument('--classes', default=None,
        help='comma-separated subset of jet classes (default: all - {})'.format(','.join(CLASSES)))
    parser.add_argument('--treename', default=TREE_NAME, help='tree to read (default: {})'.format(TREE_NAME))
    parser.add_argument('--d0-range', type=float, default=None,
        help='half-width of the d0 window in cm (default: {})'.format(
            dict((v[0], v[5]) for v in VARIABLES)['d0']))
    parser.add_argument('--dz-range', type=float, default=None,
        help='half-width of the dz window in cm (default: {})'.format(
            dict((v[0], v[5]) for v in VARIABLES)['dz']))
    parser.add_argument('--d0sig-range', type=float, default=None,
        help='half-width of the d0 significance window (default: {})'.format(
            dict((v[0], v[5]) for v in VARIABLES)['d0sig']))
    parser.add_argument('--dzsig-range', type=float, default=None,
        help='half-width of the dz significance window (default: {})'.format(
            dict((v[0], v[5]) for v in VARIABLES)['dzsig']))
    parser.add_argument('--single-class-figures', default=None,
        help='comma-separated classes that ALSO get their own single-panel figure,'
             ' beside the all-classes grid (default: {}; "none" to switch off)'.format(
                 ','.join(ps.SINGLE_CLASS_FIGURES)))
    parser.add_argument('--no-clip', action='store_true',
        help='drop out-of-window values instead of clipping them into the end bins.'
             ' Each side is then renormalized over only what it kept - see the module'
             ' docstring for why that flatters the comparison')
    parser.add_argument('--min-jet-pt', type=float, default=None,
        help='restrict to jets above this pT (same meaning as in the sibling scripts)')
    parser.add_argument('--max-jet-eta', type=float, default=None,
        help='restrict to jets below this |eta|')
    parser.add_argument('--paper-style', action='store_true', help=ps.PAPER_STYLE_HELP)
    parser.add_argument('--tag', default=None,
        help='suffix appended to every output filename, e.g. --tag ptmatched')
    args = parser.parse_args()

    files = expand_files(args.files)
    classes = CLASSES if args.classes is None else [c.strip() for c in args.classes.split(',') if c.strip()]
    unknown = [c for c in classes if c not in CLASSES]
    if unknown:
        raise SystemExit('unknown class(es) {} - known: {}'.format(unknown, CLASSES))
    if not os.path.exists(args.outdir):
        os.makedirs(args.outdir)

    schema = nio.detect_schema(files, treename=args.treename)
    variables = []
    for var in VARIABLES:
        if var[2] is not None and schema != 'ours':
            print('NOTE: skipping {} - the {} schema has no per-particle IP error'
                  ' (it stores a pre-computed significance instead)'.format(var[0], schema))
            continue
        variables.append(var)

    overrides = {'d0': args.d0_range, 'dz': args.dz_range,
                 'd0sig': args.d0sig_range, 'dzsig': args.dzsig_range}
    edges = {}
    for var_key, _, _, _, _, default_hw in variables:
        hw = overrides[var_key] if overrides[var_key] is not None else default_hw
        edges[var_key] = np.linspace(-hw, hw, NBINS + 1)

    # ONE FILE AT A TIME. Everything a panel needs is additive (see
    # new_accumulator()), so the per-particle branches of one file are read, binned
    # and thrown away before the next is opened. Reading them all first instead made
    # memory track the size of the production - 12 GB for the signal family and ~20 GB
    # projected for QCD, which is a request the batch system struggles to place.
    clip = not args.no_clip
    acc = {}
    has_hlt = False
    for i, f in enumerate(files, 1):
        print('  reading {}/{}: {}'.format(i, len(files), os.path.basename(f)))
        data = nio.load_particles([f], suffixes=SUFFIXES, treename=args.treename)
        has_hlt = 'hlt_matched' in data
        masks, _ = class_masks([f], classes)
        keep = nio.jet_selection_mask([f], min_jet_pt=args.min_jet_pt,
                                      max_jet_eta=args.max_jet_eta, treename=args.treename)
        if keep is not None:
            masks = {name: m & keep for name, m in masks.items()}

        for var_key, suffix, err_suffix, _, _, _ in variables:
            e = edges[var_key]
            hw = e[-1]
            for sel_key, _, leading_only in SELECTIONS:
                off_vals, off_jet = charged_values(data, 'part_', suffix, leading_only,
                                                   err_suffix)
                if has_hlt:
                    hlt_vals, hlt_jet = charged_values(data, 'hlt_part_', suffix,
                                                       leading_only, err_suffix)
                for name in classes:
                    m = masks[name]
                    key = (var_key, sel_key, name)
                    if key not in acc:
                        acc[key] = new_accumulator(NBINS, has_hlt)
                    acc[key]['njets'] += int(m.sum())
                    if len(off_vals):
                        accumulate(acc[key], 'off', off_vals[m[off_jet]], e, hw, clip)
                    if has_hlt and len(hlt_vals):
                        accumulate(acc[key], 'hlt', hlt_vals[m[hlt_jet]], e, hw, clip)
        del data

    if not has_hlt:
        print('NOTE: offline-only input - plotting the Offline side alone')

    for var_key, suffix, err_suffix, xlabel, long_name, _ in variables:
        e = edges[var_key]
        for sel_key, sel_label, _ in SELECTIONS:
            results = {name: acc[(var_key, sel_key, name)] for name in classes}
            name = 'ip_{}_{}'.format(var_key, sel_key)
            if args.tag:
                name += '_' + args.tag
            title = '{} - {}'.format(long_name, sel_label)

            # the grid first, so its paper variant fixes the shared y-range that the
            # single-class figures then reuse - otherwise each of those would pick
            # its own and they could not be compared with each other
            # fixed range if this variable has one, else fall back to deriving it
            # from the reference class inside this run (see PAPER_YLIM)
            shared_ylim = PAPER_YLIM.get(var_key)
            base = os.path.join(args.outdir, name + '.png')
            for path, paper in ps.output_variants(base, args.paper_style):
                used = make_grid(results, classes, path, e, xlabel, title, clip,
                                 paper_style=paper,
                                 ylim=shared_ylim if paper else None)
                if paper and shared_ylim is None:
                    shared_ylim = used

            for cls in ps.single_class_selection(args.single_class_figures, classes):
                one = os.path.join(args.outdir, '{}_{}.png'.format(name, cls))
                for path, paper in ps.output_variants(one, args.paper_style):
                    make_grid(results, [cls], path, e, xlabel, title, clip,
                              paper_style=paper, ylim=shared_ylim if paper else None)


if __name__ == '__main__':
    main()
