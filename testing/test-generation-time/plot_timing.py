#!/usr/bin/env python3

'''
Plot elapsed per-job runtime (as measured by run_timing_scan.py) versus
NEVENT, and fit a simple "fixed overhead + linear in NEVENT" model:

    elapsed_sec = intercept + slope * NEVENT

via ordinary least squares. The intercept is the per-job fixed cost
(sourcing the software stack, MG5/Pythia8 startup, copying the gridpack,
ACLiC-compiling makeNtuples.C++ - none of which depend on NEVENT); the
slope is the marginal cost per event actually generated/reconstructed/
ntupled. See README.md in this directory for the numbers this produced and
what they imply for planning larger production runs.

Usage:
  python plot_timing.py [--input timing_results.txt] [--output output_plots/timing_scan.png]
'''

import os
import re
import argparse

import numpy as np
import matplotlib.pyplot as plt

THISDIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(THISDIR, 'timing_results.txt')
DEFAULT_OUTPUT = os.path.join(THISDIR, 'output_plots', 'timing_scan.png')

LINE_PAT = re.compile(
    r'NEVENT=(\d+)\s+JOBNUM=(\d+)\s+elapsed_sec=(\d+)\s+rc=(-?\d+)')


def load_results(fname):
    '''Parse a run_timing_scan.py results file into (nevent, elapsed_sec) arrays, one row per line.'''
    nevents, elapsed = [], []
    with open(fname) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            m = LINE_PAT.match(line)
            if not m:
                raise ValueError('could not parse results line: {!r}'.format(line))
            nevent, jobnum, elapsed_sec, rc = (int(x) for x in m.groups())
            if rc != 0:
                print('WARNING: skipping NEVENT={} JOBNUM={} - nonzero rc={}'.format(nevent, jobnum, rc))
                continue
            nevents.append(nevent)
            elapsed.append(elapsed_sec)
    if not nevents:
        raise ValueError('no valid (rc=0) result lines found in {}'.format(fname))
    return np.array(nevents, dtype=np.float64), np.array(elapsed, dtype=np.float64)


def fit_linear(nevents, elapsed):
    '''Ordinary least squares fit of elapsed_sec = intercept + slope*nevent. Returns (intercept, slope, r_squared).'''
    slope, intercept = np.polyfit(nevents, elapsed, 1)
    pred = intercept + slope * nevents
    ss_res = np.sum((elapsed - pred) ** 2)
    ss_tot = np.sum((elapsed - np.mean(elapsed)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else float('nan')
    return intercept, slope, r_squared


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Scatter plot of run_timing_scan.py results, with a fixed-overhead + linear fit.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--input', default=DEFAULT_INPUT,
        help='results file written by run_timing_scan.py (one "NEVENT=... elapsed_sec=..." line per job)')
    parser.add_argument('--output', default=DEFAULT_OUTPUT,
        help='output plot file')
    args = parser.parse_args()

    nevents, elapsed = load_results(args.input)
    order = np.argsort(nevents)
    nevents, elapsed = nevents[order], elapsed[order]

    intercept, slope, r_squared = fit_linear(nevents, elapsed)
    print('Fit: elapsed_sec = {:.1f} + {:.4f} * NEVENT  (R^2 = {:.3f})'.format(intercept, slope, r_squared))
    for n, e in zip(nevents, elapsed):
        pred = intercept + slope * n
        print('  NEVENT={:>6.0f}  observed={:>4.0f} s  predicted={:>5.1f} s  residual={:+.1f} s'.format(
            n, e, pred, e - pred))

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(nevents, elapsed, color='crimson', zorder=3, label='measured')

    x_fit = np.linspace(0, nevents.max() * 1.05, 200)
    y_fit = intercept + slope * x_fit
    ax.plot(x_fit, y_fit, color='steelblue', linestyle='--', zorder=2,
            label='fit: {:.0f} s + {:.3f} s/event ($R^2$={:.3f})'.format(intercept, slope, r_squared))

    ax.set_xlabel('NEVENT')
    ax.set_ylabel('Elapsed time [s]')
    ax.set_title('run.sh full-chain timing scan')
    ax.grid(True, alpha=0.3)
    ax.set_axisbelow(True)
    ax.legend(loc='best')
    fig.tight_layout()

    outdir = os.path.dirname(os.path.abspath(args.output))
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir)
    fig.savefig(args.output, dpi=150)
    print('Saved plot to {}'.format(args.output))
