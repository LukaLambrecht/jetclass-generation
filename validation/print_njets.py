#!/usr/bin/env python3

'''Diagnostics for a production output directory: jet yield and ntuple size per
(family/proc/card) and per process, plus a full per-label breakdown with QCD against
everything-else aggregates.

Useful to check what fraction of a signal process' output is actually signal-labelled
rather than QCD-fallback-labelled, or to sanity-check a process' label composition
against its own decay branching ratios.

Directories are auto-discovered under --output-path by globbing for ntuples and parsing
each path relative to it as <family>/<proc>/.../<card>/, with proc always the component
right after the family, whatever lies between proc and card. This works unchanged for
every process family and needs no update when processes are added. --procs and --cards
optionally restrict to a subset.

The same --output-path can point at the CMS offline+scouting reference dataset instead,
whose samples are discovered the same way, letting one command compare our output
against it directly.

Per-label counts are read off each file's label branch and aggregated with bincount, so
this reads no more data than the entry count alone would need.

The label scheme is chosen with --coarse-labels:

  - by default each dataset uses its own native labels, which is what you want to study
    one dataset's composition on its own terms. The reference dataset's labels print as
    raw codes, since the upstream string names are not published.
  - with --coarse-labels both collapse onto ntuple_io.py's coarse cross-schema
    categories, which is what you want to compare the two directly, at the cost of not
    being fine-grained: the two fine-grained schemes do not correspond one to one.

Either way the per-proc QCD against non-QCD split is unaffected, being always computed
the same way, so a raw label's QCD-ness never requires knowing its upstream name.

Usage:
  python3 print_njets.py --output-path /eos/user/l/llambrec/jetclass/output_jetclass2_5M

  # compare directly against the reference dataset, each with its own native labels
  python3 print_njets.py --output-path /eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train

  # ...or a directly comparable coarse breakdown across both
  python3 print_njets.py --output-path /eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train --coarse-labels

  # a subset of processes/cards, and/or a different njobs expectation
  python3 print_njets.py --output-path /eos/user/l/llambrec/jetclass/output_jetclass1_10M \
      --procs HToBB,TTBar --cards onlyFatJetNoPU,onlyFatJetHLTNoPU --njobs-expected 13

  # skip the (possibly long) per-label table
  python3 print_njets.py --output-path /eos/user/l/llambrec/jetclass/output_jetclass2_5M --no-labels
'''

import os
import sys
import glob
import time
import argparse
import threading
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import uproot

import ntuple_io as nio

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(THISDIR)
DEFAULT_LABEL_HEADER = nio.DEFAULT_LABEL_HEADER

# The process families our own productions write under <output-path>/<family>/<proc>/...
# (i.e. the top-level subdirectory names of gen_configs/). Anything else under
# --output-path is either a fullsim reference dataset (matched by FULLSIM_GLOB
# instead) or an unrecognized layout. Extend this when a new gen_configs/ family is
# added - "jetclass2sb" is the pThat-binned QCD set behind the offline+scouting
# reference dataset, see gen_configs/jetclass2sb/README.md.
#
# Matched case-insensitively (see discover_ntuple_dirs()): a production writes this
# directory name from its own --procs argument, so a dataset whose family name was
# capitalized differently stays readable. Keep the entries here lowercase.
OURS_FAMILIES = ('jetclass1', 'jetclass2', 'jetclass2sb')

NTUPLE_TREE_NAME = 'tree'  # see makeNtuples.C/makeNtuplesPaired.C: one entry per jet
NTUPLE_GLOB = 'ntuple_*.root'          # "ours" - see makeNtuples.C/makeNtuplesPaired.C
FULLSIM_GLOB = 'dnnTuples_nanov15_*.root'  # fullsim - see ntuple_io.py
LABEL_BRANCH = 'jet_label'  # int index into ntuple_io.load_label_names()'s list ("ours" only -
                             # same branch name in both makeNtuples.C and makeNtuplesPaired.C)

# PROCESSES, not threads. Reading one ntuple is dominated by uproot's own per-file
# Python work (opening the file, parsing the directory/TTree structure), which holds
# the GIL - measured on a full production: ~20 files/s regardless of whether 32, 64 or
# 128 THREADS were used, with the process pegged at ~95% of a single core. Running 4
# separate processes instead gave ~18 files/s EACH, i.e. it scales nearly linearly with
# processes and not at all with threads. Left at a dozen or so rather than cpu_count()
# because lxplus nodes are shared.
DEFAULT_MAX_WORKERS = min(12, os.cpu_count() or 8)
CHUNKSIZE = 8  # files per task sent to a worker process; amortizes IPC over ~10k files
BYTES_PER_GB = 1e9  # decimal GB, matching how EOS/most tools report file sizes


def nlabels_for(family, label_names, coarse):
    '''How long one (family, coarse) combination's raw bincount is at read time.'''
    if family != 'fullsim':
        return len(label_names)
    return len(nio.CATEGORY_NAMES) if coarse else nio.FULLSIM_RAW_LABEL_CAP


def resolve_display(family, counts, cat_idx_partial, label_names, coarse):
    '''Turn one proc's raw counts into (names, counts, qcd_mask) ready for display, resolving
    the label names for its family and scheme.
    '''
    if family == 'fullsim':
        if coarse:
            names = nio.CATEGORY_NAMES
            return names, counts, np.array([n == 'QCD' for n in names])

        value_to_category = {}
        if cat_idx_partial is not None:
            for value in np.nonzero(counts)[0]:
                cat_idx = cat_idx_partial[value]
                if cat_idx >= 0:
                    value_to_category[int(value)] = nio.CATEGORY_NAMES[cat_idx]
        resolved = nio.resolve_fullsim_label_names(value_to_category)
        names = [resolved.get(i, 'fj_label={}'.format(i)) for i in range(len(counts))]
        qcd_mask = np.array([value_to_category.get(i) == 'QCD' for i in range(len(counts))])
        return names, counts, qcd_mask

    if coarse:
        names = nio.CATEGORY_NAMES
        coarse_counts = np.zeros(len(names), dtype=np.int64)
        for name, c in zip(label_names, counts):
            coarse_counts[names.index(nio.classify_ours_label(name))] += c
        return names, coarse_counts, np.array([n == 'QCD' for n in names])

    return label_names, counts, np.array([nio.is_qcd_label(n) for n in label_names])


def discover_ntuple_dirs(output_path):
    '''Find every directory under output_path holding ntuples of either schema.'''
    found = {}
    for path in sorted(glob.glob(os.path.join(output_path, '**', NTUPLE_GLOB), recursive=True)):
        rel = os.path.relpath(os.path.dirname(path), output_path)
        parts = [p for p in rel.split(os.sep) if p]
        if len(parts) < 3 or parts[0].lower() not in OURS_FAMILIES:
            print('WARNING: skipping ntuple file in unrecognized directory layout: {}'.format(path), file=sys.stderr)
            continue
        family, proc, card = parts[0], parts[1], parts[-1]
        found.setdefault((family, proc, card), []).append(path)
    for path in sorted(glob.glob(os.path.join(output_path, '**', FULLSIM_GLOB), recursive=True)):
        rel = os.path.relpath(os.path.dirname(path), output_path)
        parts = [p for p in rel.split(os.sep) if p]
        if len(parts) < 1:
            print('WARNING: skipping fullsim file in unrecognized directory layout: {}'.format(path), file=sys.stderr)
            continue
        proc = parts[-1]  # immediate parent dir = sample name, e.g. "H0HpHm_mixed_new"
        # offline+HLT are already one combined row per fullsim file (see
        # ntuple_io.py) - "paired" here is just a fixed, descriptive card
        # name, not parsed out of the path like "ours"' own card is
        found.setdefault(('fullsim', proc, 'paired'), []).append(path)
    if not found:
        raise Exception('no {} or {} files found anywhere under {!r}'.format(
            NTUPLE_GLOB, FULLSIM_GLOB, output_path))
    return found


def _count_one_cheap(path):
    '''Entry count and size only, with no branch data. At module level so a process pool can
    pickle it.
    '''
    try:
        with uproot.open(path) as f:
            return f[NTUPLE_TREE_NAME].num_entries, os.path.getsize(path)
    except Exception as e:
        print('  WARNING: could not read {} ({}: {})'.format(path, type(e).__name__, e), file=sys.stderr)
        return None


def _read_one_star(args):
    '''read_one(*args), for mapping a process pool over argument tuples.'''
    return read_one(*args)


class Progress:
    '''"n of total files" progress indicator for the pooled reads, ticked from the main
    process.
    '''

    PRINT_EVERY_SEC = 0.5    # tty: at most this often
    PRINT_EVERY_FRAC = 0.1   # non-tty: every 10% of the files

    def __init__(self, total, label='reading', stream=sys.stderr):
        '''Start the counter at zero.'''
        self.total = total
        self.label = label
        self.stream = stream
        self.isatty = hasattr(stream, 'isatty') and stream.isatty()
        self.done = 0
        self.failed = 0
        self.t0 = time.time()
        self.last_t = 0.0
        self.next_frac = self.PRINT_EVERY_FRAC
        self.lock = threading.Lock()

    def tick(self, ok=True):
        '''Record one more finished file and redraw the line.'''
        with self.lock:
            self.done += 1
            if not ok:
                self.failed += 1
            if self.isatty:
                now = time.time()
                if now - self.last_t < self.PRINT_EVERY_SEC and self.done < self.total:
                    return
                self.last_t = now
                self.stream.write('\r' + self._line() + '   ')
            else:
                if self.done < self.total and self.done / self.total < self.next_frac:
                    return
                self.next_frac += self.PRINT_EVERY_FRAC
                self.stream.write(self._line() + '\n')
            self.stream.flush()

    def _line(self):
        '''Write the current progress line in place.'''
        el = time.time() - self.t0
        rate = self.done / el if el > 0 else 0.0
        eta = (self.total - self.done) / rate if rate > 0 else 0.0
        msg = '  {} {}/{} files ({:.0f}%)  {:.0f} files/s'.format(
            self.label, self.done, self.total, 100.0 * self.done / self.total, rate)
        if self.done < self.total:
            msg += '  eta {:.0f}s'.format(eta)
        else:
            msg += '  in {:.0f}s'.format(el)
        if self.failed:
            msg += '  [{} unreadable]'.format(self.failed)
        return msg

    def finish(self):
        '''Close off the progress line.'''
        if self.isatty:
            self.stream.write('\r' + self._line() + '   \n')
            self.stream.flush()


def read_one(path, family, nlabels, coarse):
    '''Per-file (label_counts, size_bytes, cat_idx_partial), with label_counts a bincount over
    the file's label branch.
    '''
    try:
        size_bytes = os.path.getsize(path)
        if family == 'fullsim':
            if coarse:
                cats, njets = nio.load_fullsim_categories([path])
                idx = np.zeros(njets, dtype=np.int64)
                for i, name in enumerate(nio.CATEGORY_NAMES):
                    idx[cats == name] = i
                return np.bincount(idx, minlength=nlabels), size_bytes, None

            values, category_flags, njets = nio.load_fullsim_raw_labels([path])
            if values.size and (values.min() < 0 or values.max() >= nlabels):
                print('WARNING: {}: fj_label value(s) outside [0, {}) - FULLSIM_RAW_LABEL_CAP may need'
                      ' raising (out-of-range entries excluded from the label breakdown, still counted'
                      ' in njets/size)'.format(path, nlabels), file=sys.stderr)
                mask = (values >= 0) & (values < nlabels)
                values = values[mask]
                category_flags = {name: flags[mask] for name, flags in category_flags.items()}
            counts = np.bincount(values, minlength=nlabels)
            cat_idx_partial = np.full(nlabels, -1, dtype=np.int8)
            for i, name in enumerate(nio.CATEGORY_NAMES[:-1]):
                in_cat = values[category_flags[name]]
                if in_cat.size:
                    cat_idx_partial[np.unique(in_cat)] = i
            return counts, size_bytes, cat_idx_partial

        with uproot.open(path) as f:
            values = f[NTUPLE_TREE_NAME][LABEL_BRANCH].array(library='np')
        if values.size and (values.min() < 0 or values.max() >= nlabels):
            print('WARNING: {}: jet_label value(s) outside [0, {}) - label list may be out of sync '
                  'with FatJetMatching.h (out-of-range entries excluded from the label breakdown, '
                  'still counted in njets/size)'.format(path, nlabels), file=sys.stderr)
            values = values[(values >= 0) & (values < nlabels)]
        return np.bincount(values, minlength=nlabels), size_bytes, None
    except Exception as e:
        print('  WARNING: could not read {} ({}: {})'.format(path, type(e).__name__, e), file=sys.stderr)
        return None


def format_bytes(n):
    '''Human-readable size.'''
    return '{:.2f} GB'.format(n / BYTES_PER_GB) if n >= BYTES_PER_GB else '{:.1f} MB'.format(n / 1e6)


def print_overview_table(rows_by_combo, njobs_expected):
    '''Per (family, proc, card): job count, jets, size, jets per job and bytes per jet.
    '''
    combo_keys = [combo for combo, _ in rows_by_combo]
    family_width = max([len('family')] + [len(f) for f, _, _ in combo_keys]) + 2
    proc_width = max([len('proc')] + [len(p) for _, p, _ in combo_keys]) + 2
    card_width = max([len('card')] + [len(c) for _, _, c in combo_keys]) + 2

    njobs_col = '{:>10}'.format('njobs' if njobs_expected is None else 'njobs/{}'.format(njobs_expected))
    row_fmt = '{{:<{}}}{{:<{}}}{{:<{}}}{{:>10}}{{:>14}}{{:>16}}{{:>14.0f}}'.format(
        family_width, proc_width, card_width)
    header_fmt = '{{:<{}}}{{:<{}}}{{:<{}}}{{}}{{:>14}}{{:>16}}{{:>14}}'.format(
        family_width, proc_width, card_width)

    header = header_fmt.format('family', 'proc', 'card', njobs_col, 'njets', 'size', 'njets/job')
    print(header)
    print('-' * len(header))

    grand_njets = grand_size = grand_njobs = 0
    for (family, proc, card), (njobs, njets, size_bytes) in rows_by_combo:
        avg = njets / njobs if njobs else 0
        grand_njets += njets
        grand_size += size_bytes
        grand_njobs += njobs
        njobs_str = str(njobs) if njobs_expected is None else '{}/{}'.format(njobs, njobs_expected)
        print(row_fmt.format(family, proc, card, njobs_str, njets, format_bytes(size_bytes), avg))

    print('-' * len(header))
    print(row_fmt.format(
        'TOTAL', '', '', grand_njobs, grand_njets, format_bytes(grand_size),
        grand_njets / grand_njobs if grand_njobs else 0))


def print_per_proc_summary(per_proc):
    '''Per process, summed over cards: jets and size, plus how many of its jets are signal
    rather than QCD-labelled.
    '''
    # proc here is "<family>/<proc>" (see per_proc_rows in __main__), which can run
    # well past a fixed 16-char width (e.g. "jetclass2/train_higgs2p" = 23 chars) -
    # size the column to whatever's actually longest instead of a fixed guess, so
    # rows with different-length names don't throw the later columns out of line
    # with each other.
    proc_width = max([len('proc'), len('TOTAL')] + [len(proc) for proc, _, _, _, _ in per_proc]) + 2
    row_fmt = '{{:<{}}}{{:>14}}{{:>16}}{{:>16}}{{:>9.1f}}%{{:>16}}{{:>9.1f}}%'.format(proc_width)
    header_fmt = '{{:<{}}}{{:>14}}{{:>16}}{{:>16}}{{:>10}}{{:>16}}{{:>10}}'.format(proc_width)

    header = header_fmt.format('proc', 'njets', 'size', 'non-QCD', '(%)', 'QCD_*', '(%)')
    print(header)
    print('-' * len(header))

    grand_njets = grand_qcd = grand_size = 0
    for proc, names, counts, qcd_mask, size_bytes in per_proc:
        njets = int(counts.sum())
        n_qcd = int(counts[qcd_mask].sum())
        n_sig = njets - n_qcd
        grand_njets += njets
        grand_qcd += n_qcd
        grand_size += size_bytes
        print(row_fmt.format(
            proc, njets, format_bytes(size_bytes), n_sig,
            100 * n_sig / njets if njets else 0, n_qcd, 100 * n_qcd / njets if njets else 0))

    print('-' * len(header))
    grand_sig = grand_njets - grand_qcd
    print(row_fmt.format(
        'TOTAL', grand_njets, format_bytes(grand_size), grand_sig,
        100 * grand_sig / grand_njets if grand_njets else 0,
        grand_qcd, 100 * grand_qcd / grand_njets if grand_njets else 0))


def print_label_breakdown(proc, names, counts, qcd_mask, top_labels, coarse):
    '''The per-label table for one proc, from resolve_display()'s output.'''
    njets = int(counts.sum())
    print('\n{} - per-{}label breakdown ({} jets total):'.format(
        proc, 'coarse (cross-schema) ' if coarse else '', njets))
    label_width = max([len('label')] + [len(n) for n, c in zip(names, counts) if c > 0]) + 2
    header = '  {:<{}}{:>12}{:>10}'.format('label', label_width, 'count', '(%)')
    print(header)
    print('  ' + '-' * (len(header) - 2))
    nonzero = [(name, int(c), bool(q)) for name, c, q in zip(names, counts, qcd_mask) if c > 0]
    nonzero.sort(key=lambda x: -x[1])
    shown = nonzero if top_labels is None else nonzero[:top_labels]
    for name, c, is_qcd in shown:
        flag = ' [QCD]' if is_qcd else ''
        print('  {:<{}}{:>12}{:>9.1f}%{}'.format(name, label_width, c, 100 * c / njets if njets else 0, flag))
    if top_labels is not None and len(nonzero) > top_labels:
        rest = sum(c for _, c, _ in nonzero[top_labels:])
        print('  {:<{}}{:>12}{:>9.1f}%  ({} more label(s))'.format(
            '... other', label_width, rest, 100 * rest / njets if njets else 0, len(nonzero) - top_labels))


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
    parser.add_argument('--coarse-labels', action='store_true',
        help='collapse the per-label breakdown onto ntuple_io.py\'s coarse, cross-schema'
             ' CATEGORY_NAMES buckets (Top/W/Z/H2p/HWW/HZZ/QCD/other) for BOTH families,'
             ' instead of each dataset\'s own native/raw labels (our own fine-grained'
             ' label list, or fullsim\'s raw fj_label integer code) - use this specifically'
             ' to compare an "ours" proc against a "fullsim" one directly; the default'
             ' (off) is better for studying a single dataset\'s own composition on its own'
             ' terms, since it doesn\'t collapse anything - see module docstring\'s'
             ' "Label scheme, per family"')
    parser.add_argument('--max-workers', type=int, default=DEFAULT_MAX_WORKERS,
        help='how many worker PROCESSES to read with (default: {}) - see DEFAULT_MAX_WORKERS:'
             ' the per-file cost is uproot\'s own Python work, which is GIL-bound, so this'
             ' scales with processes and not with threads'.format(DEFAULT_MAX_WORKERS))
    args = parser.parse_args()

    label_names = nio.load_label_names(args.label_header)

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
        all_files = [path for files in combos.values() for path in files]
        progress = Progress(len(all_files), label='reading (no labels)')
        results = {}
        with ProcessPoolExecutor(max_workers=args.max_workers) as pool:
            for path, r in zip(all_files, pool.map(_count_one_cheap, all_files, chunksize=CHUNKSIZE)):
                results[path] = r
                progress.tick(ok=r is not None)
        progress.finish()

        rows_by_combo = []
        for combo in sorted(combos):
            files = combos[combo]
            ok = [results[p] for p in files if results[p] is not None]
            njets = sum(n for n, _ in ok)
            size_bytes = sum(s for _, s in ok)
            rows_by_combo.append((combo, (len(files), njets, size_bytes)))
        print_overview_table(rows_by_combo, args.njobs_expected)
        raise SystemExit(0)

    # nlabels varies per (family, --coarse-labels) - see nlabels_for() - resolved once
    # per file here so the single shared thread pool below can dispatch each file's
    # read_one() call correctly regardless of which combo it's from
    file_family = {path: family for (family, _, _), files in combos.items() for path in files}
    file_nlabels = {path: nlabels_for(family, label_names, args.coarse_labels)
                     for path, family in file_family.items()}

    all_files = list(file_family.keys())
    progress = Progress(len(all_files), label='reading')
    work = [(p, file_family[p], file_nlabels[p], args.coarse_labels) for p in all_files]
    results = {}
    with ProcessPoolExecutor(max_workers=args.max_workers) as pool:
        for path, r in zip(all_files, pool.map(_read_one_star, work, chunksize=CHUNKSIZE)):
            results[path] = r
            progress.tick(ok=r is not None)
    progress.finish()

    def combine_cat_idx_partials(partials, nlabels):
        '''Merge the per-file category observations into one value-to-category mapping, tolerating
        the files that carry none.
        '''
        real = [p for p in partials if p is not None]
        if not real:
            return None
        combined = np.full(nlabels, -1, dtype=np.int8)
        for p in real:
            combined = np.where(combined == -1, p, combined)
        return combined

    rows_by_combo = []
    per_combo_counts = {}
    for combo in sorted(combos):
        family = combo[0]
        files = combos[combo]
        nlabels = nlabels_for(family, label_names, args.coarse_labels)
        ok = [results[p] for p in files if results[p] is not None]
        counts = sum((c for c, _, _ in ok), np.zeros(nlabels, dtype=np.int64))
        size_bytes = sum(s for _, s, _ in ok)
        cat_idx_partial = combine_cat_idx_partials([cp for _, _, cp in ok], nlabels)
        per_combo_counts[combo] = (counts, size_bytes, cat_idx_partial)
        rows_by_combo.append((combo, (len(files), int(counts.sum()), size_bytes)))

    print_overview_table(rows_by_combo, args.njobs_expected)

    # aggregate per (family, proc) - i.e. per gridpack type/sample, summed over cards
    # (only "ours" ever has more than one card per proc - see discover_ntuple_dirs())
    per_proc = {}
    for (family, proc, card), (counts, size_bytes, cat_idx_partial) in per_combo_counts.items():
        key = (family, proc)
        nlabels = nlabels_for(family, label_names, args.coarse_labels)
        prev_counts, prev_size, prev_cat = per_proc.get(key, (np.zeros(nlabels, dtype=np.int64), 0, None))
        per_proc[key] = (prev_counts + counts, prev_size + size_bytes,
                          combine_cat_idx_partials([prev_cat, cat_idx_partial], nlabels))
    per_proc_rows = [
        ('{}/{}'.format(family, proc),) + resolve_display(family, counts, cat_idx_partial, label_names, args.coarse_labels)
        + (size,)
        for (family, proc), (counts, size, cat_idx_partial) in sorted(per_proc.items())
    ]  # each row: (proc_label, names, counts, qcd_mask, size_bytes)

    print()
    print_per_proc_summary(per_proc_rows)

    for proc, names, counts, qcd_mask, _ in per_proc_rows:
        print_label_breakdown(proc, names, counts, qcd_mask, args.top_labels, args.coarse_labels)
