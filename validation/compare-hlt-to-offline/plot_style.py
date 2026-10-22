#!/usr/bin/env python3

'''
Shared Offline-vs-HLT drawing style for the plotting scripts in this directory.

Exists so the three figure kinds that overlay Offline and HLT stay identical: same
two colours, same statistical band, same legend keys. plot_particle_pt.py already
drew a line-plus-band this way; this generalizes it to the step histograms in
plot_jet_kinematics.py and plot_nparticles.py.

THE BAND is the Poisson uncertainty sqrt(N) on the RAW per-bin count, carried
through whatever scaling the nominal histogram got. For a density-normalized
histogram that scaling is 1 / (N_total * bin_width) per bin, applied to the error
exactly as to the count - so the band is the uncertainty on the plotted quantity,
not on the raw count. Drawing it means reading raw counts ourselves rather than
letting ax.hist(density=True) do the normalization internally, which is why these
helpers take values and bins rather than wrapping ax.hist().

THE LEGEND keys show the line over its band, not a box. matplotlib's default key
for a step histogram is a rectangle outline, which says nothing about either the
line or the band; a (Patch, Line2D) tuple drawn through HandlerTuple(ndivide=1)
overlays them in one key instead. Note ndivide=1, NOT None: None splits the key box
into one section per handle, which puts the band and the line SIDE BY SIDE; 1 keeps
a single section so both are drawn over each other, i.e. the line on its band.
'''

import os

import numpy as np
from matplotlib.legend_handler import HandlerTuple
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

OFFLINE_COLOR = 'dodgerblue'
HLT_COLOR = 'darkorchid'

BAND_ALPHA = 0.3      # same as plot_particle_pt.py's existing band
LINE_WIDTH = 2


def poisson_density(vals, bins):
    '''Per-bin (nominal, error) for a density-normalized histogram of `vals`.

    Returns what ax.hist(vals, bins, density=True) would plot, plus the propagated
    sqrt(N) error. Normalization matches matplotlib's: counts / (N_in_range *
    bin_width), using the IN-RANGE total, since np.histogram drops values outside
    the binning and matplotlib normalizes by what it kept.
    '''
    counts, edges = np.histogram(vals, bins=bins)
    widths = np.diff(edges)
    total = counts.sum()
    if total == 0:
        z = np.zeros(len(counts), dtype=float)
        return z, z, edges
    scale = 1.0 / (total * widths)
    return counts * scale, np.sqrt(counts) * scale, edges


def step_band(ax, nominal, err, edges, color, zorder=2):
    '''Draw one series as a step line with a semitransparent band of +/- err.

    The band is clipped at zero: these are log-y panels and a negative lower edge
    is meaningless for a count. Returns the (patch, line) pair to put in a legend.
    '''
    lower = np.clip(nominal - err, a_min=0.0, a_max=None)
    upper = nominal + err
    ax.stairs(upper, edges, baseline=lower, fill=True, color=color,
              alpha=BAND_ALPHA, linewidth=0, zorder=zorder)
    ax.stairs(nominal, edges, color=color, linewidth=LINE_WIDTH, zorder=zorder + 1)
    return legend_key(color)


def legend_key(color, linewidth=LINE_WIDTH):
    '''A (band, line) legend handle pair for `color` - see module docstring.
    `linewidth` should match whatever the panel actually drew.'''
    return (Patch(facecolor=color, alpha=BAND_ALPHA, linewidth=0),
            Line2D([], [], color=color, linewidth=linewidth))


def legend_with_bands(ax, handles, labels, **kwargs):
    '''ax.legend() with each key drawn as the line over its band.'''
    kwargs.setdefault('handler_map', {tuple: HandlerTuple(ndivide=1)})
    return ax.legend(handles, labels, **kwargs)


# ---------------------------------------------------------------------------
# Display names
# ---------------------------------------------------------------------------

# Raw jet-class name (as used everywhere in the code, and in CLASSES) -> how it
# should be WRITTEN in a figure. Kept in one place so every script labels a class
# identically; anything not listed falls back to its raw name, so a new class shows
# up readably rather than raising.
#
# Note X_tauhtaul: the two taus have OPPOSITE charge (X is neutral), so this is
# tau^{\pm}_{l} tau^{\mp}_{h}.
CLASS_DISPLAY = {
    'QCD':         'QCD',
    'X_bb':        r'$X \rightarrow b\bar{b}$',
    'X_cc':        r'$X \rightarrow c\bar{c}$',
    'X_ss':        r'$X \rightarrow s\bar{s}$',
    'X_qq':        r'$X \rightarrow u\bar{u} / d\bar{d}$',
    'X_gg':        r'$X \rightarrow gg$',
    'X_ee':        r'$X \rightarrow e^{+}e^{-}$',
    'X_mm':        r'$X \rightarrow \mu^{+}\mu^{-}$',
    'X_tauhtauh':  r'$X \rightarrow \tau_{h}\tau_{h}$',
    'X_tauhtaul':  r'$X \rightarrow \tau^{\pm}_{l}\tau^{\mp}_{h}$',
}


def class_label(name):
    '''Formatted display name for a jet class, falling back to the raw name.'''
    return CLASS_DISPLAY.get(name, name)


# Particle-type names are written in the plural in figures ("Muons", not "Muon"):
# a panel shows a distribution over many particles, not one. plot_particle_pt.py's
# own CATEGORIES were already plural; this makes the others match.
PARTICLE_TYPE_PLURAL = {
    'Charged hadron': 'Charged hadrons',
    'Neutral hadron': 'Neutral hadrons',
    'Photon':         'Photons',
    'Electron':       'Electrons',
    'Muon':           'Muons',
    'Unclassified':   'Unclassified',
}


def type_label(name):
    '''Plural display name for a particle type, falling back to the raw name.'''
    return PARTICLE_TYPE_PLURAL.get(name, name)


# ---------------------------------------------------------------------------
# Axis furniture, so every panel in this directory looks the same
# ---------------------------------------------------------------------------

def apply_grid(ax, axis='both'):
    '''The standard major/minor grid. Drawn BELOW the data.'''
    ax.minorticks_on()
    ax.grid(True, which='major', axis=axis, linestyle='-', alpha=0.4)
    ax.grid(True, which='minor', axis=axis, linestyle=':', alpha=0.25)
    ax.set_axisbelow(True)


def log_x_ticks(ax):
    '''Label a log x-axis at 1-2-5 within each decade, as plain numbers.

    matplotlib's default labels only the decades, which on a range like 200-5000 GeV
    leaves a single "10^3" and no sense of scale. ScalarFormatter prints 200/300/500
    rather than 2x10^2, which reads better for a pT axis.
    '''
    from matplotlib.ticker import LogLocator, FuncFormatter
    ax.xaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0,), numticks=15))
    # 1-2-5 per decade, not 1-2-3-5: at the same font size as the major labels (see
    # below) the 2-3 pair collides - "2000" and "3000" render as "20003000" on a
    # 6-inch panel. 1-2-5 is the usual log scheme and still gives three labels per
    # decade, which was the point of labelling the minors at all.
    ax.xaxis.set_minor_locator(LogLocator(base=10.0, subs=(2.0, 5.0), numticks=15))
    # '%g', NOT ScalarFormatter: on a decade below 1 the latter rounds every tick to
    # "0" (0.2, 0.3 and 0.5 all print as 0), which is worse than no label at all.
    fmt = FuncFormatter(lambda v, pos: '{:g}'.format(v))
    ax.xaxis.set_major_formatter(fmt)
    ax.xaxis.set_minor_formatter(fmt)
    # SAME size for major and minor: the decade ticks (1000) are major and the
    # 2-3-5 ones (200, 2000, ...) are minor, so leaving minor at a smaller size made
    # one label in each decade visibly bigger than its neighbours. Taking the value
    # from rcParams rather than hardcoding one also keeps the x labels the same size
    # as the y labels, which are untouched.
    import matplotlib as mpl
    ax.tick_params(axis='x', which='both', labelsize=mpl.rcParams['xtick.labelsize'])


def draw_info(ax, lines, fontsize=13, x=0.03, y=0.96, dy=0.065):
    '''The per-panel info block, top-left, in the order given.'''
    for i, line in enumerate(lines):
        ax.text(x, y - dy * i, line, transform=ax.transAxes, ha='left', va='top',
                fontsize=fontsize)


PAPER_STYLE_HELP = (
    'ADDITIONALLY write a PDF of every figure in a reduced style for a note or paper:'
    ' no figure titles and no bookkeeping text (jet counts, HLT-matched fraction,'
    ' medians), keeping only what identifies the panel - the jet class and/or particle'
    ' type. The ordinary PNGs are still produced, unchanged, so this only ever ADDS'
    ' files')


# ---------------------------------------------------------------------------
# Output variants
# ---------------------------------------------------------------------------

def output_variants(outpath, paper_style):
    """Yield the (path, paper_style) pairs a figure should be rendered as.

    --paper-style is ADDITIVE: the ordinary PNG is produced either way, exactly as
    without the flag, and the flag adds a second rendering of the same figure as a
    PDF with the reduced text (no jet counts, no medians, no titles). That way one
    run serves both purposes - monitoring a production and illustrating a note -
    and the paper figures can never silently replace the diagnostic ones.

    PDF because these end up in LaTeX: it is vector, so it stays sharp at whatever
    size the document puts it.
    """
    yield outpath, False
    if paper_style:
        yield os.path.splitext(outpath)[0] + '.pdf', True


# Classes that ALSO get their own single-panel figure, beside the all-classes grid.
# A grid is right for scanning every class at once, but a note or talk usually wants
# one class on its own, at readable size; these three are the ones that get used that
# way - inclusive QCD, and the two extremes of the resonance classes.
SINGLE_CLASS_FIGURES = ('QCD', 'X_bb', 'X_qq')


def single_class_selection(requested, available):
    """Which classes to make single-panel figures for.

    `requested` is the --single-class-figures value (None for the default, or
    'none'/'' to switch it off); `available` is what was actually plotted, so asking
    for a class the run does not contain is silently skipped rather than failing.
    """
    if requested is None:
        names = list(SINGLE_CLASS_FIGURES)
    elif requested.strip().lower() in ('none', ''):
        return []
    else:
        names = [c.strip() for c in requested.split(',') if c.strip()]
    return [n for n in names if n in available]
