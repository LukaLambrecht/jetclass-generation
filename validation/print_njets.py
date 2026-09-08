#!/usr/bin/env python3

'''
Diagnostics for a production output directory: per (family/proc/card) and
per-process ("gridpack type", e.g. train_higgs2p vs train_qcd, or HToBB vs
TTBar) jet yield (ROOT tree entry count, i.e. njets - one entry per jet, per
makeNtuples.C/makeNtuplesPaired.C) and ntuple size on disk, PLUS a full
per-label breakdown (jet_label branch) with QCD_* vs everything-else
aggregates - e.g. to check what fraction of a jetclass2 signal process' own
output is actually signal-labeled vs QCD-fallback-labeled (see
compare-to-central-jetclass2/ and the X->ff njets/event discussion this was
written for), or to sanity-check a process' label composition against its
own py8.dat decay branching ratios.

Directories are auto-discovered under --output-path (rather than assuming a
fixed jetclass1 process list/layout) by globbing for ntuple_*.root and
parsing each file's path relative to --output-path as
<family>/<proc>/.../<card>/ntuple_*.root - i.e. "jetclass1/HToBB/precompiled/
onlyFatJetNoPU/..." or "jetclass2/train_higgs2p/onlyFatJet/..." (proc is
always the path component right after the family, whatever comes between
proc and card - "precompiled"/"raw" for jetclass1, nothing for jetclass2).
This works unchanged for both process families and needs no update when new
processes are added under gen_configs/. --procs/--cards optionally restrict
to a subset (bare names, e.g. "HToBB,TTBar" or "train_higgs2p").

Per-label counts are read directly off each file's jet_label branch (an int
index into FatJetMatching.h's own labels_ vector - see load_label_names(),
which parses that vector straight out of the header so it can never drift
out of sync with it) and aggregated with np.bincount, so this reads the
same amount of data uproot would need anyway for num_entries plus the
label values - no extra passes over the files.

Usage:
  python3 print_njets.py --output-path /eos/user/l/llambrec/jetclass/output_jetclass2_5M

  # a subset of processes/cards, and/or a different njobs expectation
  python3 print_njets.py --output-path /eos/user/l/llambrec/jetclass/output_jetclass1_10M \\
      --procs HToBB,TTBar --cards onlyFatJetNoPU,onlyFatJetHLTNoPU --njobs-expected 13

  # skip the (possibly long) per-label table, just the njets/size summary
  python3 print_njets.py --output-path /eos/user/l/llambrec/jetclass/output_jetclass2_5M --no-labels
'''

import os
import sys
import re
import glob
import argparse
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import uproot

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(THISDIR)
DEFAULT_LABEL_HEADER = os.path.join(REPO_DIR, 'delphes_analyzers', 'FatJetMatching.h')

NTUPLE_TREE_NAME = 'tree'  # see makeNtuples.C/makeNtuplesPaired.C: one entry per jet
NTUPLE_GLOB = 'ntuple_*.root'
LABEL_BRANCH = 'jet_label'  # int index into load_label_names()'s list, same branch name
                             # in both makeNtuples.C and makeNtuplesPaired.C

DEFAULT_MAX_WORKERS = 32
BYTES_PER_GB = 1e9  # decimal GB, matching how EOS/most tools report file sizes


def load_label_names(header_path):
    '''
    Parse FatJetMatching.h's own `std::vector<std::string> labels_{...}`
    initializer list straight out of the header (rather than hardcoding a
    second copy of ~200 label strings here that could silently drift out of
    sync with it) and return it as an ordered list - labels_[i] is exactly
    what a jet_label value of i means, for both the v2 X_*/X_YY_*/QCD_*
    scheme and the v1 Top_*/W_*/Z_*/H_*/QCD_all labels appended after it
    (see FatJetMatching.h's own useV1Labels_/labels_ comments).
    '''
    with open(header_path) as f:
        text = f.read()
    anchor = text.index('labels_{')
    start = text.index('{', anchor)
    depth = 0
    end = None
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        raise ValueError('{}: could not find the closing brace of labels_{{...}}'.format(header_path))
    block = re.sub(r'//.*', '', text[start + 1:end])  # strip line comments before pulling out strings
    labels = re.findall(r'"([^"]*)"', block)
    if not labels:
        raise ValueError('{}: parsed labels_{{...}} but found no quoted label strings inside it'.format(header_path))
    return labels


def is_qcd_label(name):
    '''Every QCD-fallback label (v2's 27-way flavor split, and v1's single QCD_all
    catch-all) is named QCD_*; every signal label (X_*, X_YY_*, Top_*, W_*, Z_*, H_*)
    is not - see FatJetMatching.h's labels_ vector.'''
    return name.startswith('QCD_')


def discover_ntuple_dirs(output_path):
    '''
    Find every directory under output_path holding ntuple_*.root files, and
    group their paths by (family, proc, card) parsed out of each file's
    path relative to output_path - see module docstring for the two
    layouts this covers. Returns {(family, proc, card): [file paths...]},
    files sorted, dict insertion-ordered by first appearance (stably
    re-sorted by the caller before printing).
    '''
    found = {}
    pattern = os.path.join(output_path, '**', NTUPLE_GLOB)
    for path in sorted(glob.glob(pattern, recursive=True)):
        rel = os.path.relpath(os.path.dirname(path), output_path)
        parts = [p for p in rel.split(os.sep) if p]
        if len(parts) < 3 or parts[0] not in ('jetclass1', 'jetclass2'):
            print('WARNING: skipping ntuple file in unrecognized directory layout: {}'.format(path), file=sys.stderr)
            continue
        family, proc, card = parts[0], parts[1], parts[-1]
        found.setdefault((family, proc, card), []).append(path)
    if not found:
        raise Exception('no {} files found anywhere under {!r}'.format(NTUPLE_GLOB, output_path))
    return found


def read_one(path, nlabels):
    '''
    Per-file (label_counts, size_bytes): label_counts is an nlabels-length
    np.bincount of the jet_label branch (so njets for this file is simply
    label_counts.sum()) and size_bytes is the file's size on disk. Reading
    the branch already costs what num_entries alone would (uproot has to
    read the basket to get either), so this gets the full per-label
    breakdown for free. Returns None (rather than raising) if the file
    can't be read (e.g. a job still mid-write), so the caller can skip it
    with a warning instead of the whole run aborting.
    '''
    try:
        with uproot.open(path) as f:
            values = f[NTUPLE_TREE_NAME][LABEL_BRANCH].array(library='np')
        size_bytes = os.path.getsize(path)
        if values.size and (values.min() < 0 or values.max() >= nlabels):
            print('WARNING: {}: jet_label value(s) outside [0, {}) - label list may be out of sync '
                  'with FatJetMatching.h (out-of-range entries excluded from the label breakdown, '
                  'still counted in njets/size)'.format(path, nlabels), file=sys.stderr)
            values = values[(values >= 0) & (values < nlabels)]
        return np.bincount(values, minlength=nlabels), size_bytes
    except Exception as e:
        print('  WARNING: could not read {} ({}: {})'.format(path, type(e).__name__, e), file=sys.stderr)
        return None


def format_bytes(n):
    return '{:.2f} GB'.format(n / BYTES_PER_GB) if n >= BYTES_PER_GB else '{:.1f} MB'.format(n / 1e6)


def print_overview_table(rows_by_combo, njobs_expected):
    '''Per (family, proc, card) table: njobs, njets, size, njets/job, bytes/jet - the
    same table print_njets.py always printed, just auto-discovered instead of assuming
    a fixed jetclass1 proc/card list.'''
    njobs_col = '{:>10}'.format('njobs' if njobs_expected is None else 'njobs/{}'.format(njobs_expected))
    header = '{:<11}{:<16}{:<20}{}{:>14}{:>16}{:>14}'.format(
        'family', 'proc', 'card', njobs_col, 'njets', 'size', 'njets/job')
    print(header)
    print('-' * len(header))

    grand_njets = grand_size = grand_njobs = 0
    for (family, proc, card), (njobs, njets, size_bytes) in rows_by_combo:
        avg = njets / njobs if njobs else 0
        grand_njets += njets
        grand_size += size_bytes
        grand_njobs += njobs
        njobs_str = str(njobs) if njobs_expected is None else '{}/{}'.format(njobs, njobs_expected)
        print('{:<11}{:<16}{:<20}{:>10}{:>14}{:>16}{:>14.0f}'.format(
            family, proc, card, njobs_str, njets, format_bytes(size_bytes), avg))

    print('-' * len(header))
    print('{:<11}{:<16}{:<20}{:>10}{:>14}{:>16}{:>14.0f}'.format(
        'TOTAL', '', '', grand_njobs, grand_njets, format_bytes(grand_size),
        grand_njets / grand_njobs if grand_njobs else 0))


def print_per_proc_summary(per_proc, label_names):
    '''Per gridpack type (proc, summed over cards): njets/size, plus how many of its
    jets are signal-labeled vs QCD-fallback-labeled - the "aggregated counts for QCD_*
    and everything else, per gridpack type" the diagnostics were asked for.'''
    qcd_mask = np.array([is_qcd_label(n) for n in label_names])

    # proc here is "<family>/<proc>" (see per_proc_rows in __main__), which can run
    # well past a fixed 16-char width (e.g. "jetclass2/train_higgs2p" = 23 chars) -
    # size the column to whatever's actually longest instead of a fixed guess, so
    # rows with different-length names don't throw the later columns out of line
    # with each other.
    proc_width = max([len('proc'), len('TOTAL')] + [len(proc) for proc, _ in per_proc]) + 2
    row_fmt = '{{:<{}}}{{:>14}}{{:>16}}{{:>16}}{{:>9.1f}}%{{:>16}}{{:>9.1f}}%'.format(proc_width)
    header_fmt = '{{:<{}}}{{:>14}}{{:>16}}{{:>16}}{{:>10}}{{:>16}}{{:>10}}'.format(proc_width)

    header = header_fmt.format('proc', 'njets', 'size', 'non-QCD', '(%)', 'QCD_*', '(%)')
    print(header)
    print('-' * len(header))

    grand_counts = np.zeros(len(label_names), dtype=np.int64)
    grand_size = 0
    for proc, (counts, size_bytes) in per_proc:
        njets = int(counts.sum())
        n_qcd = int(counts[qcd_mask].sum())
        n_sig = njets - n_qcd
        grand_counts += counts
        grand_size += size_bytes
        print(row_fmt.format(
            proc, njets, format_bytes(size_bytes), n_sig,
            100 * n_sig / njets if njets else 0, n_qcd, 100 * n_qcd / njets if njets else 0))

    print('-' * len(header))
    total_njets = int(grand_counts.sum())
    total_qcd = int(grand_counts[qcd_mask].sum())
    total_sig = total_njets - total_qcd
    print(row_fmt.format(
        'TOTAL', total_njets, format_bytes(grand_size), total_sig,
        100 * total_sig / total_njets if total_njets else 0,
        total_qcd, 100 * total_qcd / total_njets if total_njets else 0))


def print_label_breakdown(proc, counts, label_names, top_labels):
    njets = int(counts.sum())
    print('\n{} - per-label breakdown ({} jets total):'.format(proc, njets))
    header = '  {:<20}{:>12}{:>10}'.format('label', 'count', '(%)')
    print(header)
    print('  ' + '-' * (len(header) - 2))
    nonzero = [(name, int(c)) for name, c in zip(label_names, counts) if c > 0]
    nonzero.sort(key=lambda x: -x[1])
    shown = nonzero if top_labels is None else nonzero[:top_labels]
    for name, c in shown:
        flag = ' [QCD]' if is_qcd_label(name) else ''
        print('  {:<20}{:>12}{:>9.1f}%{}'.format(name, c, 100 * c / njets if njets else 0, flag))
    if top_labels is not None and len(nonzero) > top_labels:
        rest = sum(c for _, c in nonzero[top_labels:])
        print('  {:<20}{:>12}{:>9.1f}%  ({} more label(s))'.format(
            '... other', rest, 100 * rest / njets if njets else 0, len(nonzero) - top_labels))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output-path', required=True,
        help='REQUIRED: production output directory, e.g. /eos/user/l/llambrec/jetclass/output_jetclass2_5M'
             ' (same thing run_condor.py/run_condor_loop.py call --output-path)')
    parser.add_argument('--procs', default=None,
        help='comma-separated bare process names to restrict to, e.g. "train_higgs2p,train_qcd" or'
             ' "HToBB,TTBar" (default: every process auto-discovered under --output-path)')
    parser.add_argument('--cards', default=None,
        help='comma-separated Delphes card names to restrict to, e.g. "onlyFatJet" (default: every'
             ' card auto-discovered under --output-path)')
    parser.add_argument('--njobs-expected', type=int, default=None,
        help='if given, also print how many of this many expected jobs/files are present per'
             ' (family, proc, card), e.g. --njobs-expected 100')
    parser.add_argument('--label-header', default=DEFAULT_LABEL_HEADER,
        help='FatJetMatching.h to read the labels_ vector (jet_label index -> name) from'
             ' (default: {})'.format(os.path.relpath(DEFAULT_LABEL_HEADER, REPO_DIR)))
    parser.add_argument('--top-labels', type=int, default=None,
        help='if given, cap each per-process label breakdown to this many labels (by count,'
             ' descending), with the remainder summed into one "... other" line (default:'
             ' show every non-zero label)')
    parser.add_argument('--no-labels', action='store_true',
        help='skip the per-label breakdown entirely (still prints the njets/size overview'
             ' and per-proc QCD_*/non-QCD summary, without needing to read jet_label at all'
             ' - just num_entries - for a faster, size/njobs-only check)')
    parser.add_argument('--max-workers', type=int, default=DEFAULT_MAX_WORKERS,
        help='how many files to read concurrently (default: {}) - reading each ntuple\'s'
             ' jet_label branch is dominated by EOS network latency, not CPU, so this is a lot'
             ' faster than reading files one at a time'.format(DEFAULT_MAX_WORKERS))
    args = parser.parse_args()

    label_names = load_label_names(args.label_header)

    combos = discover_ntuple_dirs(args.output_path)
    if args.procs is not None:
        wanted_procs = {p.strip() for p in args.procs.split(',') if p.strip()}
        combos = {k: v for k, v in combos.items() if k[1] in wanted_procs}
    if args.cards is not None:
        wanted_cards = {c.strip() for c in args.cards.split(',') if c.strip()}
        combos = {k: v for k, v in combos.items() if k[2] in wanted_cards}
    if not combos:
        raise Exception('--procs/--cards filtered out everything discovered under {!r}'.format(args.output_path))

    if args.no_labels:
        # cheap path: num_entries + getsize only, no branch data read at all
        def count_one_cheap(path):
            try:
                with uproot.open(path) as f:
                    return f[NTUPLE_TREE_NAME].num_entries, os.path.getsize(path)
            except Exception as e:
                print('  WARNING: could not read {} ({}: {})'.format(path, type(e).__name__, e), file=sys.stderr)
                return None

        all_files = [path for files in combos.values() for path in files]
        with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
            results = dict(zip(all_files, pool.map(count_one_cheap, all_files)))

        rows_by_combo = []
        for combo in sorted(combos):
            files = combos[combo]
            ok = [results[p] for p in files if results[p] is not None]
            njets = sum(n for n, _ in ok)
            size_bytes = sum(s for _, s in ok)
            rows_by_combo.append((combo, (len(files), njets, size_bytes)))
        print_overview_table(rows_by_combo, args.njobs_expected)
        raise SystemExit(0)

    all_files = [path for files in combos.values() for path in files]
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        results = dict(zip(all_files, pool.map(lambda p: read_one(p, len(label_names)), all_files)))

    rows_by_combo = []
    per_combo_counts = {}
    for combo in sorted(combos):
        files = combos[combo]
        ok = [results[p] for p in files if results[p] is not None]
        counts = sum((c for c, _ in ok), np.zeros(len(label_names), dtype=np.int64))
        size_bytes = sum(s for _, s in ok)
        per_combo_counts[combo] = (counts, size_bytes)
        rows_by_combo.append((combo, (len(files), int(counts.sum()), size_bytes)))

    print_overview_table(rows_by_combo, args.njobs_expected)

    # aggregate per (family, proc) - i.e. per gridpack type, summed over cards
    per_proc = {}
    for (family, proc, card), (counts, size_bytes) in per_combo_counts.items():
        key = (family, proc)
        prev_counts, prev_size = per_proc.get(key, (np.zeros(len(label_names), dtype=np.int64), 0))
        per_proc[key] = (prev_counts + counts, prev_size + size_bytes)
    per_proc_rows = [('{}/{}'.format(family, proc), v) for (family, proc), v in sorted(per_proc.items())]

    print()
    print_per_proc_summary(per_proc_rows, label_names)

    for proc, (counts, _) in per_proc_rows:
        print_label_breakdown(proc, counts, label_names, args.top_labels)
