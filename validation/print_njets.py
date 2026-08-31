#!/usr/bin/env python3

'''
Prints a per-process, per-card table of the actual jet yield (ROOT tree
entry count, i.e. njets - one entry per jet, per makeNtuples.C) found under
a production output directory, plus the number of ntuple files present per
(process, card) - the same table used to cross-check the output_jetclass1_10M
production run's dataset size/njets against expectations. See
test_hlt_vs_offline_njets.py for WHY the offline vs HLT ("card") counts
differ for a given process.

Usage:
  python3 print_njets.py --output-path /eos/user/l/llambrec/jetclass/output_jetclass1_10M

  # a subset of processes/cards, and/or a different njobs expectation
  python3 print_njets.py --output-path /eos/user/l/llambrec/jetclass/output_jetclass1_10M \\
      --procs HToBB,TTBar --cards onlyFatJetNoPU,onlyFatJetHLTNoPU --njobs-expected 13
'''

import os
import sys
import argparse
import glob
from concurrent.futures import ThreadPoolExecutor

import uproot

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(THISDIR)
sys.path.append(REPO_DIR)
from download_gridpack import normalize_proc

NTUPLE_TREE_NAME = 'tree'  # see makeNtuples.C: one entry per jet
DEFAULT_PROCS = 'HToBB,HToCC,HToGG,HToWW2Q1L,HToWW4Q,TTBar,TTBarLep,WToQQ,ZJetsToNuNu,ZToQQ'
DEFAULT_CARDS = 'onlyFatJetNoPU,onlyFatJetHLTNoPU'


def ntuple_dir(output_path, proc, card):
    # matches run.sh's own $OUTPUT_PATH/$PROC/$name layout, PROC always
    # jetclass1/<proc>/precompiled here (same scope as
    # test_hlt_vs_offline_njets.py - this repo's only production hierarchy so far)
    return os.path.join(output_path, 'jetclass1', proc, 'precompiled', card)


DEFAULT_MAX_WORKERS = 32


def count_one(path):
    '''
    NTUPLE_TREE_NAME's entry count (num_entries - a cheap read of the tree's
    basket index, not the branch data itself) for a single file - via
    uproot (pure Python/numpy), not a `root` subprocess: no LCG env to
    source, no ROOT interpreter startup. Returns None (rather than raising)
    if the file can't be opened/read (e.g. a job still mid-write), so the
    caller can skip it with a warning instead of the whole run aborting.
    '''
    try:
        with uproot.open(path) as f:
            return f[NTUPLE_TREE_NAME].num_entries
    except Exception as e:
        print('  WARNING: could not read {} ({}: {})'.format(path, type(e).__name__, e), file=sys.stderr)
        return None


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output-path', required=True,
        help='REQUIRED: production output directory, e.g. /eos/user/l/llambrec/jetclass/output_jetclass1_10M'
             ' (same thing run_condor.py/run_condor_loop.py call --output-path)')
    parser.add_argument('--procs', default=DEFAULT_PROCS,
        help='comma-separated jetclass1 process names (default: all 10, {})'.format(DEFAULT_PROCS))
    parser.add_argument('--cards', default=DEFAULT_CARDS,
        help='comma-separated Delphes card names/"versions" to compare (default: {})'.format(DEFAULT_CARDS))
    parser.add_argument('--njobs-expected', type=int, default=None,
        help='if given, also print how many of this many expected jobs/files are present per'
             ' (process, card), e.g. --njobs-expected 13')
    parser.add_argument('--max-workers', type=int, default=DEFAULT_MAX_WORKERS,
        help='how many files to read concurrently (default: {}) - reading each ntuple\'s'
             ' entry count is dominated by EOS network latency, not CPU, so this is a lot'
             ' faster than reading files one at a time'.format(DEFAULT_MAX_WORKERS))
    args = parser.parse_args()

    procs = [normalize_proc(p.strip()) for p in args.procs.split(',') if p.strip()]
    cards = [c.strip() for c in args.cards.split(',') if c.strip()]
    if not procs:
        raise Exception('--procs did not contain any process names')
    if not cards:
        raise Exception('--cards did not contain any card names')

    # glob every (proc, card)'s files first, then read them ALL concurrently
    # in one shared thread pool (not 20 separate small pools, one per proc/
    # card combo) - this is I/O-bound (EOS network latency), so overlapping
    # every file read across the whole run, not just within one row, is
    # what actually cuts the wall-clock time down.
    combos = [(proc, card, sorted(glob.glob(os.path.join(ntuple_dir(args.output_path, proc, card), 'ntuple_*.root'))))
              for proc in procs for card in cards]
    all_files = [path for _, _, files in combos for path in files]
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        counts = dict(zip(all_files, pool.map(count_one, all_files)))

    njobs_col = '{:>10}'.format('njobs' if args.njobs_expected is None else 'njobs/{}'.format(args.njobs_expected))
    header = '{:<14}{:<22}{}{:>16}{:>18}'.format('proc', 'card', njobs_col, 'total_njets', 'njets/job avg')
    print(header)
    print('-' * len(header))

    grand_total_njets = 0
    grand_total_jobs = 0
    for proc, card, files in combos:
        njobs = len(files)
        njets = sum(c for path in files if (c := counts[path]) is not None)
        avg = njets / njobs if njobs else 0
        grand_total_njets += njets
        grand_total_jobs += njobs
        njobs_str = str(njobs) if args.njobs_expected is None else '{}/{}'.format(njobs, args.njobs_expected)
        print('{:<14}{:<22}{:>10}{:>16}{:>18.0f}'.format(proc, card, njobs_str, njets, avg))

    print('-' * len(header))
    grand_avg = grand_total_njets / grand_total_jobs if grand_total_jobs else 0
    njobs_str = str(grand_total_jobs) if args.njobs_expected is None else '{}/{}'.format(
        grand_total_jobs, args.njobs_expected * len(procs) * len(cards))
    print('{:<14}{:<22}{:>10}{:>16}{:>18.0f}'.format('TOTAL', '', njobs_str, grand_total_njets, grand_avg))
