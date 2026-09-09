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

The SAME --output-path can also point at the real FullSim/scouting
reference dataset this whole Delphes pipeline is trying to mimic (see
hlteff/README.md's own "Data source" section and ntuple_io.py for the full
description) - e.g. --output-path /eos/cms/store/cmst3/group/vhcc/
ScoutingAK8/2024/train, which holds <sample>/dnnTuples_nanov15_*.root.
Those are auto-discovered too (family="fullsim", proc=<sample>,
card="paired" - offline+HLT are already one combined row there, see
ntuple_io.py), letting the exact same command compare our own output
against it directly - see "Cross-schema label handling" below.

Per-label counts are read directly off each file's jet_label branch (an int
index into FatJetMatching.h's own labels_ vector - see ntuple_io.load_label_names(),
which parses that vector straight out of the header so it can never drift
out of sync with it) and aggregated with np.bincount, so this reads the
same amount of data uproot would need anyway for num_entries plus the
label values - no extra passes over the files.

Label scheme, per family - two independent choices, see --coarse-labels:

  - DEFAULT (each dataset's own native/raw labels, not cross-schema
    comparable by name): "ours" procs use our own fine-grained v2
    X_*/QCD_*/... (or v1 Top_*/W_*/Z_*/H_*) label scheme (see
    ntuple_io.load_label_names()); "fullsim" procs use fullsim's own
    native fj_label integer code directly (see
    ntuple_io.load_fullsim_raw_labels()) - printed as "fj_label=<N>" since
    we don't have DNNTuples' own (unpublished) string names for it, just
    the raw codes themselves. This is what you want to study a single
    dataset's own composition on its own terms.

  - --coarse-labels: both families collapse onto ntuple_io.py's own
    coarse, cross-schema CATEGORY_NAMES buckets instead (Top/W/Z/H2p/HWW/
    HZZ/QCD/other) - "ours" via each fine-grained label's name (see
    ntuple_io.classify_ours_label()), "fullsim" via its own boolean
    category flags (see ntuple_io.load_fullsim_categories()). This is what
    you want to compare an "ours" proc against a "fullsim" one directly,
    at the cost of not being a fine-grained comparison (the two schemes'
    fine-grained label names don't correspond 1:1 - see classify_ours_label()'s
    own docstring for why these 8 buckets do correspond well enough).

Either way, the per-proc summary table's QCD_*/non-QCD split is unaffected
by this choice - it's always computed the same way (fullsim's own
fj_isQCD flag, read alongside fj_label even in the default raw-fj_label
mode, so a raw label's QCD-ness doesn't require knowing DNNTuples' own
name for it either).

Usage:
  python3 print_njets.py --output-path /eos/user/l/llambrec/jetclass/output_jetclass2_5M

  # compare directly against the real FullSim/scouting reference dataset -
  # each shown with its own native/raw labels by default
  python3 print_njets.py --output-path /eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train

  # ...or --coarse-labels for a directly comparable Top/W/Z/H2p/HWW/HZZ/QCD/other
  # breakdown across an "ours" proc and a fullsim one
  python3 print_njets.py --output-path /eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train --coarse-labels

  # a subset of processes/cards, and/or a different njobs expectation
  python3 print_njets.py --output-path /eos/user/l/llambrec/jetclass/output_jetclass1_10M \\
      --procs HToBB,TTBar --cards onlyFatJetNoPU,onlyFatJetHLTNoPU --njobs-expected 13

  # skip the (possibly long) per-label table, just the njets/size summary
  python3 print_njets.py --output-path /eos/user/l/llambrec/jetclass/output_jetclass2_5M --no-labels
'''

import os
import sys
import glob
import argparse
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import uproot

import ntuple_io as nio

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(THISDIR)
DEFAULT_LABEL_HEADER = nio.DEFAULT_LABEL_HEADER

NTUPLE_TREE_NAME = 'tree'  # see makeNtuples.C/makeNtuplesPaired.C: one entry per jet
NTUPLE_GLOB = 'ntuple_*.root'          # "ours" - see makeNtuples.C/makeNtuplesPaired.C
FULLSIM_GLOB = 'dnnTuples_nanov15_*.root'  # fullsim - see ntuple_io.py
LABEL_BRANCH = 'jet_label'  # int index into ntuple_io.load_label_names()'s list ("ours" only -
                             # same branch name in both makeNtuples.C and makeNtuplesPaired.C)

DEFAULT_MAX_WORKERS = 32
BYTES_PER_GB = 1e9  # decimal GB, matching how EOS/most tools report file sizes


def nlabels_for(family, label_names, coarse):
    '''How long a (family, coarse) combo's raw bincount is, at READ time (see read_one()) -
    "ours" is always its own fine-grained list regardless of --coarse-labels (collapsing
    "ours" onto the coarse scheme happens as a display-time post-processing step instead,
    see resolve_display(), since it doesn't change what needs to be read); a "fullsim" proc
    reads either the coarse category flags (len(CATEGORY_NAMES)) or raw fj_label
    (FULLSIM_RAW_LABEL_CAP) depending on --coarse-labels, since those are different branches.'''
    if family != 'fullsim':
        return len(label_names)
    return len(nio.CATEGORY_NAMES) if coarse else nio.FULLSIM_RAW_LABEL_CAP


def resolve_display(family, counts, cat_idx_partial, label_names, coarse):
    '''
    Turns one proc's raw (counts, cat_idx_partial) - as read by read_one()/aggregated by
    the caller - into (display_names, display_counts, qcd_mask) ready for
    print_per_proc_summary()/print_label_breakdown(), applying whichever label scheme
    --coarse-labels selects (see module docstring's "Label scheme, per family"):

      - fullsim + coarse: names=CATEGORY_NAMES, counts unchanged (already read that way),
        qcd_mask = name == 'QCD'.
      - fullsim + raw (default): names resolved per-value via
        ntuple_io.resolve_fullsim_label_names(), from cat_idx_partial (the
        combined-across-files per-value category index - see read_one()); qcd_mask =
        category == 'QCD'. A value with no resolved category at all (cat_idx_partial
        entry still -1 - shouldn't happen for a value with nonzero count, but a defensive
        fallback rather than an IndexError if it somehow does) prints as plain
        "fj_label=<N>".
      - ours + coarse: counts COLLAPSED from the fine-grained label_names onto
        CATEGORY_NAMES via ntuple_io.classify_ours_label(), qcd_mask = name == 'QCD'.
      - ours + raw (default): unchanged fine-grained label_names/counts, qcd_mask via
        ntuple_io.is_qcd_label().
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
    '''
    Find every directory under output_path holding either NTUPLE_GLOB
    ("ours") or FULLSIM_GLOB (fullsim) files, and group their paths by
    (family, proc, card) parsed out of each file's path relative to
    output_path - see module docstring for the layouts this covers.
    Returns {(family, proc, card): [file paths...]}, files sorted, dict
    insertion-ordered by first appearance (stably re-sorted by the caller
    before printing).
    '''
    found = {}
    for path in sorted(glob.glob(os.path.join(output_path, '**', NTUPLE_GLOB), recursive=True)):
        rel = os.path.relpath(os.path.dirname(path), output_path)
        parts = [p for p in rel.split(os.sep) if p]
        if len(parts) < 3 or parts[0] not in ('jetclass1', 'jetclass2'):
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


def read_one(path, family, nlabels, coarse):
    '''
    Per-file (label_counts, size_bytes, cat_idx_partial): label_counts is an
    nlabels-length np.bincount over whichever category index applies to
    (family, coarse) - see nlabels_for() for which branches that reads and
    resolve_display() for how it's turned into display names - and
    size_bytes is the file's size on disk. Reading the branch(es) already
    costs what num_entries alone would (uproot has to read the basket to
    get either), so this gets the full per-label breakdown for free.
    cat_idx_partial is only ever non-None for fullsim's raw (non-coarse)
    mode: an nlabels-length int8 array, cat_idx_partial[value] = the index
    into ntuple_io.CATEGORY_NAMES[:-1] that raw fj_label VALUE co-occurred
    with in THIS file, or -1 if never seen here. The caller combines these
    across every file for a proc (a value is consistently exactly one
    category dataset-wide - see ntuple_io.load_fullsim_raw_labels()'s own
    docstring) to recover each value's true category, which resolve_display()
    then turns into both a fine-grained name (via
    ntuple_io.resolve_fullsim_label_names()) and QCD-ness. Returns None
    (rather than raising) if the file can't be read (e.g. a job still
    mid-write), so the caller can skip it with a warning instead of the
    whole run aborting.
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
    return '{:.2f} GB'.format(n / BYTES_PER_GB) if n >= BYTES_PER_GB else '{:.1f} MB'.format(n / 1e6)


def print_overview_table(rows_by_combo, njobs_expected):
    '''Per (family, proc, card) table: njobs, njets, size, njets/job, bytes/jet - the
    same table print_njets.py always printed, just auto-discovered instead of assuming
    a fixed jetclass1 proc/card list. family/proc/card column widths are sized to
    whatever's actually longest (rather than a fixed guess) - needed once fullsim procs
    entered the picture (e.g. "QCD_PT-mixed_TuneCP5_13p6TeV_pythia8_new" is 41 chars,
    far past what any of our own proc names ever needed), same reasoning as
    print_per_proc_summary()'s own dynamic proc_width.'''
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
    '''Per gridpack type/sample (proc, summed over cards): njets/size, plus how many of
    its jets are signal-labeled vs QCD-fallback-labeled - the "aggregated counts for QCD_*
    and everything else, per gridpack type" the diagnostics were asked for. `per_proc` is
    a list of (proc_label, names, counts, qcd_mask, size_bytes) - already resolved by
    resolve_display() (see __main__), so this table's QCD/non-QCD split is the same
    numbers either way regardless of --coarse-labels, only the per-row names/counts
    passed to print_label_breakdown() alongside it differ.'''
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
    '''names/counts/qcd_mask are resolve_display()'s own output for this proc (see
    module docstring's "Label scheme, per family" for what `coarse` selects).'''
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
        help='how many files to read concurrently (default: {}) - reading each ntuple\'s'
             ' jet_label branch is dominated by EOS network latency, not CPU, so this is a lot'
             ' faster than reading files one at a time'.format(DEFAULT_MAX_WORKERS))
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

    # nlabels varies per (family, --coarse-labels) - see nlabels_for() - resolved once
    # per file here so the single shared thread pool below can dispatch each file's
    # read_one() call correctly regardless of which combo it's from
    file_family = {path: family for (family, _, _), files in combos.items() for path in files}
    file_nlabels = {path: nlabels_for(family, label_names, args.coarse_labels)
                     for path, family in file_family.items()}

    all_files = list(file_family.keys())
    with ThreadPoolExecutor(max_workers=args.max_workers) as pool:
        results = dict(zip(all_files, pool.map(
            lambda p: read_one(p, file_family[p], file_nlabels[p], args.coarse_labels), all_files)))

    def combine_cat_idx_partials(partials, nlabels):
        '''partials: list of per-file/per-combo cat_idx_partial arrays, possibly containing
        None (fullsim-coarse/"ours" files never produce one - see read_one()) - combine
        them (first non--1 entry wins per value; a value's category is consistent
        dataset-wide by construction, so there's nothing to actually reconcile - see
        ntuple_io.load_fullsim_raw_labels()'s own docstring), or return None if none of
        them produced one (nothing to aggregate).'''
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
