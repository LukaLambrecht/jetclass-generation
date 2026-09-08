#!/usr/bin/env python3

'''
Plot ntuple file size (size_bytes=, see run_timing_scan.py/backfill_size.py)
versus NEVENT and NJETS, fitting the same "fixed overhead + linear" model
plot_timing.py uses for runtime:

    size_MB = intercept + slope * NEVENT   (or NJETS)

The intercept is a per-file fixed overhead (ROOT/TTree file structure -
headers, branch metadata, basket bookkeeping - present even for a
near-empty ntuple); the slope is the marginal size per event/jet actually
written.

This script does not reimplement any of the fitting/plotting/printing -
it calls straight into plot_timing.py's generate_all_plots() (see there
for the full behavior: one color per process, combined + individual
plots, log-log versions, "<process> measured"/"Fit: ..." legends for the
individual ones, etc.) with ntuple size (converted from the stored
size_bytes to MB) as the y-quantity instead of elapsed_sec, and its own
"size_scan" file-naming prefix instead of "timing_scan".

Usage:
  python plot_size.py timing_results_HToBB.txt timing_results_HToCC.txt timing_results_TTBar.txt
'''

import os
import argparse

from plot_timing import label_for_file, resolve_labels, generate_all_plots

THISDIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_SINGLE = os.path.join(THISDIR, 'output_plots', 'size_scan.png')
DEFAULT_OUTPUT_MULTI = os.path.join(THISDIR, 'output_plots', 'size_scan_all_processes.png')

BYTES_PER_MB = 1e6  # decimal MB, matching how EOS/most tools report file sizes


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Scatter plot of ntuple size vs NEVENT/NJETS (see run_timing_scan.py), with a fixed-overhead + linear fit per process.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('inputs', nargs='+',
        help='results file(s) written by run_timing_scan.py, with size_bytes= (see backfill_size.py'
             ' for older files), e.g. timing_results_HToBB.txt timing_results_TTBar.txt ...'
             ' (given explicitly, not auto-discovered)')
    parser.add_argument('--labels', nargs='*', default=None,
        help='one label per input file, in order (default: derived from each filename)')
    parser.add_argument('--output', default=None,
        help='output plot file for the vs-NEVENT version (default: output_plots/size_scan.png'
             ' for a single input file, output_plots/size_scan_all_processes.png for multiple);'
             ' the vs-NJETS version is written alongside it with a "_per_jet" suffix')
    args = parser.parse_args()

    inputs = args.inputs
    labels = resolve_labels(inputs, args.labels)
    output = args.output or (DEFAULT_OUTPUT_SINGLE if len(inputs) == 1 else DEFAULT_OUTPUT_MULTI)

    generate_all_plots(
        inputs, labels, output,
        y_of=lambda nevents, elapsed, njets, size_bytes: size_bytes / BYTES_PER_MB,
        ylabel='Ntuple size [MB]', yname='size_MB', yunit='MB',
        x2_of=lambda nevents, elapsed, njets, size_bytes: njets,
        x2_label='Number of jets', x2_name='NJETS',
        individual_prefix='size_scan', do_individual=True,
    )
