#!/usr/bin/env python3

'''Plot elapsed per-job runtime against NEVENT, fitting a "fixed overhead plus linear"
model per process:

    elapsed_sec = intercept + slope * NEVENT

The intercept is the per-job fixed cost - sourcing the software stack, generator
startup, copying the gridpack, compiling the ntuplizer - none of which depends on
NEVENT; the slope is the marginal cost per event.

With several results files, one per process, all are drawn on the same axes: one colour
per process for both its markers and its dashed fit line. Each process is fitted
independently, so this checks whether their timing behaviour agrees rather than
assuming it.

Writes four combined files per run: runtime against NEVENT, plus a log-log version,
and, where jet counts are available, runtime against NJETS instead, fitted against
that. Points with no valid jet count are dropped from the per-jet plot only, with a
warning.

Also writes four files per process, the same data and fit one process at a time, with
the fit spelled out in the legend.

The fitting and plotting machinery is written for any y-quantity, not only runtime:
plot_size.py reuses it directly for ntuple file size.

Usage:
  # the original single-process file
  python plot_timing.py timing_results.txt

  # multiple processes together, one color per process
  python plot_timing.py timing_results_HToBB.txt timing_results_HToCC.txt timing_results_TTBar.txt

  # explicit labels/output instead of the derived-from-filename defaults
  python plot_timing.py timing_results_HToBB.txt timing_results_TTBar.txt \
      --labels HToBB TTBar --output output_plots/timing_scan_compare.png
'''

import os
import re
import argparse

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm

plt.rcParams.update({
    'font.size': 15,
    'axes.labelsize': 18,
    'xtick.labelsize': 14,
    'ytick.labelsize': 14,
    'legend.fontsize': 13,
})

# used only for a single-series plot (multi-series colors come from COLORMAP below)
MARKER_COLOR = 'darkorchid'
COLORMAP = cm.get_cmap('tab10')

THISDIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_SINGLE = os.path.join(THISDIR, 'output_plots', 'timing_scan.png')
DEFAULT_OUTPUT_MULTI = os.path.join(THISDIR, 'output_plots', 'timing_scan_all_processes.png')

LINE_PAT = re.compile(
    # The jet count and size fields are optional, so this parses a line with neither, with
    # only the jet count, or with both.
    r'NEVENT=(\d+)\s+JOBNUM=(\d+)\s+elapsed_sec=(\d+)\s+'
    r'(?:njets=(-?\d+)\s+)?(?:size_bytes=(-?\d+)\s+)?rc=(-?\d+)')
LABEL_PAT = re.compile(r'timing_results_(.+)\.txt$')


def label_for_file(fname):
    '''"timing_results_HToBB.txt" -> "HToBB"; anything else -> its filename stem.'''
    m = LABEL_PAT.search(os.path.basename(fname))
    if m:
        return m.group(1)
    return os.path.splitext(os.path.basename(fname))[0]


def resolve_labels(inputs, labels_arg):
    '''Shared --labels handling, also used by plot_size.py: validate against the number of
    inputs if given, else derive one from each filename.
    '''
    if labels_arg is not None:
        if len(labels_arg) != len(inputs):
            raise ValueError('--labels must have the same length as the number of input files ({})'.format(len(inputs)))
        return labels_arg
    return [label_for_file(f) for f in inputs]


def format_line(nevent, jobnum, elapsed_sec, njets=None, size_bytes=None, rc=0):
    '''Build one results line, preserving which optional fields were present, so a rewrite
    does not invent a field that was never there.
    '''
    parts = ['NEVENT={}'.format(nevent), 'JOBNUM={}'.format(jobnum), 'elapsed_sec={}'.format(elapsed_sec)]
    if njets is not None:
        parts.append('njets={}'.format(njets))
    if size_bytes is not None:
        parts.append('size_bytes={}'.format(size_bytes))
    parts.append('rc={}'.format(rc))
    return ' '.join(parts)


def load_results(fname):
    '''Parse a results file into (nevents, elapsed, njets, size_bytes) arrays, one entry per
    successful line, sorted by nevents.

    The jet count and size are NaN wherever the line lacks the field or it is -1, meaning
    the run failed. Callers that need them should drop the NaNs themselves.
    '''
    nevents, elapsed, njets, size_bytes = [], [], [], []
    with open(fname) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = LINE_PAT.match(line)
            if not m:
                raise ValueError('could not parse results line: {!r}'.format(line))
            nevent, jobnum, elapsed_sec = (int(x) for x in m.groups()[:3])
            njets_str, size_str = m.group(4), m.group(5)
            rc = int(m.group(6))
            if rc != 0:
                print('WARNING: {}: skipping NEVENT={} JOBNUM={} - nonzero rc={}'.format(
                    fname, nevent, jobnum, rc))
                continue
            nevents.append(nevent)
            elapsed.append(elapsed_sec)
            njets.append(float('nan') if (njets_str is None or int(njets_str) < 0) else int(njets_str))
            size_bytes.append(float('nan') if (size_str is None or int(size_str) < 0) else int(size_str))
    if not nevents:
        raise ValueError('no valid (rc=0) result lines found in {}'.format(fname))
    order = np.argsort(nevents)
    nevents = np.array(nevents, dtype=np.float64)[order]
    elapsed = np.array(elapsed, dtype=np.float64)[order]
    njets = np.array(njets, dtype=np.float64)[order]
    size_bytes = np.array(size_bytes, dtype=np.float64)[order]
    return nevents, elapsed, njets, size_bytes


def fit_linear(x, y):
    '''Ordinary least squares fit of y = intercept + slope*x. Returns (intercept, slope,
    r_squared).
    '''
    slope, intercept = np.polyfit(x, y, 1)
    pred = intercept + slope * x
    ss_res = np.sum((y - pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else float('nan')
    return intercept, slope, r_squared


def build_series(inputs, labels, x_of, y_of):
    '''Load every input file into one series per process, for an arbitrary (x, y) pair of
    quantities.

    x_of and y_of pick those quantities out of the loaded arrays, which is what lets the
    same logic serve runtime against events or jets, and file size as well. Entries where
    either is NaN are dropped, and a file left with fewer than two usable points is skipped
    with a warning.
    '''
    series = []
    for i, (fname, label) in enumerate(zip(inputs, labels)):
        nevents, elapsed, njets, size_bytes = load_results(fname)
        x = x_of(nevents, elapsed, njets, size_bytes)
        y = y_of(nevents, elapsed, njets, size_bytes)
        valid = ~np.isnan(x) & ~np.isnan(y)
        n_dropped = np.count_nonzero(~valid)
        if n_dropped:
            print('WARNING: {}: dropping {} point(s) with missing data for this plot'.format(fname, n_dropped))
        x, y = x[valid], y[valid]
        if len(x) < 2:
            print('WARNING: {}: fewer than 2 usable points - skipping'.format(fname))
            continue
        order = np.argsort(x)
        x, y = x[order], y[order]

        intercept, slope, r_squared = fit_linear(x, y)
        color = MARKER_COLOR if len(inputs) == 1 else COLORMAP(i % COLORMAP.N)
        series.append(dict(label=label, x=x, y=y, intercept=intercept, slope=slope,
                            r_squared=r_squared, color=color))
    return series


def print_fits(series, xname, yname='elapsed_sec', yunit='s'):
    '''Print each series' fitted intercept, slope and R^2.'''
    for s in series:
        print('{}: {} = {:.2f} + {:.4f} * {}  (R^2 = {:.3f})'.format(
            s['label'], yname, s['intercept'], s['slope'], xname, s['r_squared']))
        for x, y in zip(s['x'], s['y']):
            pred = s['intercept'] + s['slope'] * x
            print('  {}={:>6.0f}  observed={:>9.2f} {}  predicted={:>9.2f} {}  residual={:+.2f}'.format(
                xname, x, y, yunit, pred, yunit, y - pred))


def make_plot(series, output, xlabel, xname, ylabel='Elapsed time [s]', log=False, individual=False):
    '''Draw every series and its fit on one figure.

    With individual=True, for a single-series plot, the scatter is labelled "<process>
    measured" and the fit line gets its own legend entry spelling out the fit. With
    individual=False, the usual multi-process case, each process has one legend entry and
    its fit line shares it.
    '''
    fig, ax = plt.subplots(figsize=(9, 7))

    all_x = np.concatenate([s['x'] for s in series])
    if log:
        x_fit = np.logspace(np.log10(all_x.min() * 0.5), np.log10(all_x.max() * 1.5), 200)
    else:
        x_fit = np.linspace(0, all_x.max() * 1.05, 200)

    for s in series:
        marker_label = '{} measured'.format(s['label']) if individual else s['label']
        ax.scatter(s['x'], s['y'], color=s['color'], zorder=3, label=marker_label)
        y_fit = s['intercept'] + s['slope'] * x_fit
        fit_label = 'Fit: {:.1f} + {:.4f} * {}'.format(s['intercept'], s['slope'], xname) if individual else None
        ax.plot(x_fit, y_fit, color=s['color'], linestyle='--', zorder=2, label=fit_label)

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if log:
        ax.set_xscale('log')
        ax.set_yscale('log')
    ax.grid(True, alpha=0.3, which='both' if log else 'major')
    ax.set_axisbelow(True)
    ax.legend(loc='best', ncol=2 if (not individual and len(series) > 5) else 1)
    fig.tight_layout()

    outdir = os.path.dirname(os.path.abspath(output))
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir)
    fig.savefig(output, dpi=150)
    plt.close(fig)
    print('Saved plot to {}'.format(output))


def generate_all_plots(inputs, labels, output, y_of, ylabel, yname, yunit='s',
                        x2_of=None, x2_label=None, x2_name=None,
                        individual_prefix='timing_scan', do_individual=True):
    '''Write the combined and per-process plots for one y-quantity.

    This is what __main__ uses for runtime, factored out so plot_size.py can reuse it for a
    different y-quantity.

    x2_of and its labels name a second x-quantity to plot against as well, alongside the
    always-present NEVENT one; pass None to skip it.
    '''
    outbase, outext = os.path.splitext(output)
    outext = outext or '.png'
    event_xlabel = 'Number of generated events'
    x_of_event = lambda nevents, elapsed, njets, size_bytes: nevents

    event_series = build_series(inputs, labels, x_of_event, y_of)
    print_fits(event_series, 'NEVENT', yname, yunit)
    make_plot(event_series, output, event_xlabel, 'NEVENT', ylabel, log=False)
    make_plot(event_series, '{}_log{}'.format(outbase, outext), event_xlabel, 'NEVENT', ylabel, log=True)

    x2_series = []
    if x2_of is not None:
        x2_series = build_series(inputs, labels, x2_of, y_of)
        if x2_series:
            print_fits(x2_series, x2_name, yname, yunit)
            make_plot(x2_series, '{}_per_jet{}'.format(outbase, outext), x2_label, x2_name, ylabel, log=False)
            make_plot(x2_series, '{}_per_jet_log{}'.format(outbase, outext), x2_label, x2_name, ylabel, log=True)
        else:
            print('No files had usable data for the {} plot - skipping it'
                  ' (run the relevant backfill_*.py on older results files, or rerun run_timing_scan.py)'.format(x2_name))

    if do_individual:
        outdir = os.path.dirname(os.path.abspath(output)) or '.'
        for s in event_series:
            base = os.path.join(outdir, '{}_{}'.format(individual_prefix, s['label']))
            make_plot([s], '{}{}'.format(base, outext), event_xlabel, 'NEVENT', ylabel, log=False, individual=True)
            make_plot([s], '{}_log{}'.format(base, outext), event_xlabel, 'NEVENT', ylabel, log=True, individual=True)
        for s in x2_series:
            base = os.path.join(outdir, '{}_{}_per_jet'.format(individual_prefix, s['label']))
            make_plot([s], '{}{}'.format(base, outext), x2_label, x2_name, ylabel, log=False, individual=True)
            make_plot([s], '{}_log{}'.format(base, outext), x2_label, x2_name, ylabel, log=True, individual=True)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Scatter plot of run_timing_scan.py results, with a fixed-overhead + linear fit per process.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputs', nargs='+',
        help='results file(s) written by run_timing_scan.py, e.g. timing_results_HToBB.txt'
             ' timing_results_TTBar.txt ... (one per process to compare - given explicitly,'
             ' not auto-discovered)')
    parser.add_argument('--labels', nargs='*', default=None,
        help='one label per input file, in order (default: derived from each filename)')
    parser.add_argument('--output', default=None,
        help='output plot file for the vs-NEVENT version (default: output_plots/timing_scan.png'
             ' for a single input file, output_plots/timing_scan_all_processes.png for multiple);'
             ' the vs-NJETS version is written alongside it with a "_per_jet" suffix')
    args = parser.parse_args()

    inputs = args.inputs
    labels = resolve_labels(inputs, args.labels)
    output = args.output or (DEFAULT_OUTPUT_SINGLE if len(inputs) == 1 else DEFAULT_OUTPUT_MULTI)

    generate_all_plots(
        inputs, labels, output,
        y_of=lambda nevents, elapsed, njets, size_bytes: elapsed,
        ylabel='Elapsed time [s]', yname='elapsed_sec', yunit='s',
        x2_of=lambda nevents, elapsed, njets, size_bytes: njets,
        x2_label='Number of jets', x2_name='NJETS',
        individual_prefix='timing_scan', do_individual=True,
    )
