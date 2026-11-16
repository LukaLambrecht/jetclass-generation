#!/usr/bin/env python3

'''Plot number of jets against NEVENT, fitting a line through the origin per process:

    njets = a * NEVENT

No intercept, unlike plot_timing.py's fits: there is no reason to expect a nonzero jet
count at zero events. `a` is the mean jet yield per generated event, and comparing it
across processes shows which produce more than one selected jet per event on average.

Same combined-plot style as plot_timing.py: one colour per process, used for both its
markers and its dashed fit line, one legend entry each.

Writes --output on linear axes plus a log-log version alongside it.
'''

import os
import argparse

import numpy as np
import matplotlib.pyplot as plt

from plot_timing import load_results, label_for_file, MARKER_COLOR, COLORMAP

plt.rcParams.update({
    'font.size': 15,
    'axes.labelsize': 18,
    'xtick.labelsize': 14,
    'ytick.labelsize': 14,
    'legend.fontsize': 13,
})

THISDIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT = os.path.join(THISDIR, 'output_plots', 'njets_scan_all_processes.png')


def fit_through_origin(x, y):
    '''Least-squares slope of a line through the origin.'''
    a = np.sum(x * y) / np.sum(x ** 2)
    pred = a * x
    ss_res = np.sum((y - pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else float('nan')
    return a, r_squared


def build_series(inputs, labels):
    '''Group the loaded results into one labelled series per process.'''
    series = []
    for i, (fname, label) in enumerate(zip(inputs, labels)):
        nevents, elapsed, njets, size_bytes = load_results(fname)
        valid = ~np.isnan(njets)
        n_dropped = np.count_nonzero(~valid)
        if n_dropped:
            print('WARNING: {}: dropping {} point(s) with no valid njets'.format(fname, n_dropped))
        x, y = nevents[valid], njets[valid]
        if len(x) < 2:
            print('WARNING: {}: fewer than 2 usable points - skipping'.format(fname))
            continue
        order = np.argsort(x)
        x, y = x[order], y[order]

        a, r_squared = fit_through_origin(x, y)
        color = MARKER_COLOR if len(inputs) == 1 else COLORMAP(i % COLORMAP.N)
        series.append(dict(label=label, x=x, y=y, a=a, r_squared=r_squared, color=color))
    return series


def print_fits(series):
    '''Print each process' fitted jets-per-event slope.'''
    for s in series:
        print('{}: njets = {:.4f} * NEVENT  (R^2 = {:.3f})'.format(s['label'], s['a'], s['r_squared']))
        for x, y in zip(s['x'], s['y']):
            pred = s['a'] * x
            print('  NEVENT={:>6.0f}  observed={:>6.0f} jets  predicted={:>7.1f} jets  residual={:+.1f}'.format(
                x, y, pred, y - pred))


def print_events_needed(series, target_njets):
    '''Print how many events each process needs for a target jet count, from its fitted slope.
    '''
    print('Events needed to reach {:g} jets:'.format(target_njets))
    for s in series:
        nevent_needed = target_njets / s['a']
        print('  {:<14} {:>12.0f} events  (njets/event = {:.4f})'.format(
            s['label'] + ':', nevent_needed, s['a']))


def make_plot(series, output, log=False):
    '''Draw every series and its fit on one figure, on linear or log axes.'''
    fig, ax = plt.subplots(figsize=(9, 7))

    all_x = np.concatenate([s['x'] for s in series])
    if log:
        x_fit = np.logspace(np.log10(all_x.min() * 0.5), np.log10(all_x.max() * 1.5), 200)
    else:
        x_fit = np.linspace(0, all_x.max() * 1.05, 200)

    for s in series:
        ax.scatter(s['x'], s['y'], color=s['color'], zorder=3, label=s['label'])
        ax.plot(x_fit, s['a'] * x_fit, color=s['color'], linestyle='--', zorder=2)

    ax.set_xlabel('Number of generated events')
    ax.set_ylabel('Number of jets')
    if log:
        ax.set_xscale('log')
        ax.set_yscale('log')
    ax.grid(True, alpha=0.3, which='both' if log else 'major')
    ax.set_axisbelow(True)
    ax.legend(loc='best', ncol=2 if len(series) > 5 else 1)
    fig.tight_layout()

    outdir = os.path.dirname(os.path.abspath(output))
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir)
    fig.savefig(output, dpi=150)
    plt.close(fig)
    print('Saved plot to {}'.format(output))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Scatter plot of njets vs NEVENT (see run_timing_scan.py), with a through-origin linear fit per process.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputs', nargs='+',
        help='results file(s) written by run_timing_scan.py (with njets= - see backfill_njets.py'
             ' for older files), e.g. timing_results_HToBB.txt timing_results_TTBar.txt ...'
             ' (given explicitly, not auto-discovered)')
    parser.add_argument('--labels', nargs='*', default=None,
        help='one label per input file, in order (default: derived from each filename)')
    parser.add_argument('--output', default=DEFAULT_OUTPUT,
        help='output plot file (linear axes); the log-log version is written alongside it'
             ' with a "_log" suffix')
    parser.add_argument('--target-njets', type=float, default=None,
        help='if given, also print the NEVENT needed to reach this many jets, per process'
             ' (the through-origin fit inverted: NEVENT = target_njets / a)')
    args = parser.parse_args()

    inputs = args.inputs
    if args.labels is not None:
        if len(args.labels) != len(inputs):
            raise ValueError('--labels must have the same length as the number of input files ({})'.format(len(inputs)))
        labels = args.labels
    else:
        labels = [label_for_file(f) for f in inputs]

    series = build_series(inputs, labels)
    if not series:
        raise SystemExit('No files had usable njets= data - nothing to plot'
                          ' (run backfill_njets.py on older results files, or rerun with the current run_timing_scan.py)')
    print_fits(series)

    if args.target_njets is not None:
        print_events_needed(series, args.target_njets)

    outbase, outext = os.path.splitext(args.output)
    outext = outext or '.png'
    make_plot(series, args.output, log=False)
    make_plot(series, '{}_log{}'.format(outbase, outext), log=True)
