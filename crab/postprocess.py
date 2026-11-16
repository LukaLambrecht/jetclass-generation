#!/usr/bin/env python3

'''Merge a production's per-job ntuples into a few large ones, with hadd.

A full round leaves thousands of files of a few MB each, since CRAB writes one per job
and splits them over counter directories. Every downstream tool then pays a per-file
cost unrelated to the amount of data, which dominates the runtime of the validation and
plotting scripts. Merging to ~2 GB files removes most of that.

The merged files go to a separate --dest tree, in the layout every reader here already
understands:

    <dest>/<family>/<proc>/<card>/ntuple_merged_<i>.root

so the validation scripts work on it unchanged. Nothing under --input is touched;
check the output, and see --verify, before removing the originals.

Grouping is one group per process, except that a real card is never merged away:
  * CRAB layout, <family>/<proc>/<timestamp>/<counter>/ - timestamp and counter are
    bookkeeping, not physics, so everything for a process is merged together, across
    several tasks if need be. The output card is --card-name.
  * local layout, <family>/<proc>/.../<card>/ - <card> is a real detector
    configuration, so those are different datasets, merged separately, each keeping
    its own card.

Modes:
  --mode local    hadd each output file in turn, in this terminal.
  --mode condor   one condor job per output file, all submitted at once. Re-running
                  skips only outputs that already exist on disk, so check the queue
                  first: a merge still in flight would get a duplicate job.
Both run the same hadd commands; --dry-run prints them and does nothing.

Usage:
  python postprocess.py --input /eos/user/l/llambrec/jetclass/output_jetclass2sb_4M --dry-run
  python postprocess.py --input /eos/user/l/llambrec/jetclass/output_jetclass2sb_4M
  python postprocess.py --input /eos/user/l/llambrec/jetclass/output_jetclass2_4M --mode condor
'''

import os
import re
import sys
import glob
import time
import shutil
import argparse
import subprocess
import tempfile
from collections import defaultdict

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(THISDIR)
sys.path.append(os.path.join(REPO_DIR, 'jobtools'))

NTUPLE_GLOB = 'ntuple_*.root'
MERGED_PREFIX = 'ntuple_merged_'
DEFAULT_CARD_NAME = 'merged'
DEFAULT_TARGET_GB = 2.0
BYTES_PER_GB = 1e9

# A CRAB output directory ends in <timestamp>/<counter>/, with the timestamp as
# YYMMDD_HHMMSS and the counter as four digits. Matching both is what distinguishes
# it from a local production, whose last component is a real detector card.
CRAB_TIMESTAMP_RE = re.compile(r'^\d{6}_\d{6}$')
CRAB_COUNTER_RE = re.compile(r'^\d{4}$')

# hadd comes from ROOT. el9 nodes usually have one on PATH; if not, fall back to the
# LCG view INSTALL.md uses. Kept as a shell fragment because it has to run inside the
# condor job too, not only here.
ROOT_SETUP = ('command -v hadd >/dev/null 2>&1 || '
              'source /cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh'
              ' >/dev/null 2>&1')

# Scratch directory for a condor merge, deliberately not '.': condortools makes every
# job cd back to the submission directory, which is on EOS, so a relative path would
# have hadd write its multi-GB temporary onto EOS and lose the write-then-copy safety
# this relies on. HTCondor points _CONDOR_SCRATCH_DIR at local disk on the worker.
CONDOR_SCRATCH = '${_CONDOR_SCRATCH_DIR:-.}'


def discover(input_path, procs=None):
    '''Map group -> sorted list of input files.

    A group is (family, proc, card, outdir_rel): the first three for reporting, the last
    being where the merged output goes relative to --dest.
    '''
    groups = defaultdict(list)
    pattern = os.path.join(input_path, '**', NTUPLE_GLOB)
    for path in glob.glob(pattern, recursive=True):
        rel = os.path.relpath(os.path.dirname(path), input_path)
        parts = rel.split(os.sep)
        if len(parts) < 2:
            continue
        family, proc = parts[0], parts[1]
        if len(parts) >= 4 and CRAB_TIMESTAMP_RE.match(parts[-2]) and CRAB_COUNTER_RE.match(parts[-1]):
            # CRAB: collapse timestamp+counter, merge the whole process together
            card = None
            outdir_rel = os.path.join(family, proc)
        else:
            # local production: the last component is a real card, keep it
            card = parts[-1]
            outdir_rel = rel
        groups[(family, proc, card, outdir_rel)].append(path)
    if procs:
        wanted = {p.strip() for p in procs.split(',') if p.strip()}
        groups = {k: v for k, v in groups.items() if k[1] in wanted}
    return {k: sorted(v) for k, v in groups.items()}


def plan_chunks(files, target_bytes):
    '''Split files into chunks of at most target_bytes of input, never splitting a file.

    A single file larger than the target gets a chunk to itself.
    '''
    chunks, cur, cur_size = [], [], 0
    for f in files:
        try:
            sz = os.path.getsize(f)
        except OSError:
            sz = 0
        if cur and cur_size + sz > target_bytes:
            chunks.append(cur)
            cur, cur_size = [], 0
        cur.append(f)
        cur_size += sz
    if cur:
        chunks.append(cur)
    return chunks


def hadd_command(out_path, inputs, tmpdir):
    '''The shell commands that produce one merged file.

    hadd writes to a scratch file and the result is moved into place only on success, so an
    interrupted merge never leaves a half-written ntuple under --dest that would later look
    like a valid input.
    '''
    tmp = os.path.join(tmpdir, os.path.basename(out_path))
    return [
        ROOT_SETUP,
        'mkdir -p {}'.format(os.path.dirname(out_path)),
        'hadd -f {} {}'.format(tmp, ' '.join(inputs)),
        'cp {} {}'.format(tmp, out_path),
        'rm -f {}'.format(tmp),
    ]


def abbreviate(cmds, keep=2):
    '''Shorten a long input list for logging: show the first few paths and say how many
    follow.
    '''
    out = []
    for c in cmds:
        if c.startswith('hadd '):
            parts = c.split()
            head, inputs = parts[:3], parts[3:]
            if len(inputs) > keep:
                c = ' '.join(head + inputs[:keep]) + ' ... (+{} more)'.format(len(inputs) - keep)
        out.append(c)
    return out


def format_bytes(n):
    '''Human-readable size, in GB or MB.'''
    return '{:.1f} GB'.format(n / BYTES_PER_GB) if n >= BYTES_PER_GB else '{:.0f} MB'.format(n / 1e6)


def main():
    '''Discover the inputs, plan the merges, and run or submit them.'''
    parser = argparse.ArgumentParser(
        description='hadd a production\'s per-job ntuples into a few large ones.',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-i', '--input', required=True, type=os.path.abspath,
        help='production output directory to merge (the one passed to --output-path/--outlfn)')
    parser.add_argument('-d', '--dest', default=None, type=lambda p: os.path.abspath(p),
        help='where to write the merged tree (default: <input>_merged). Must differ from'
             ' --input, so the originals stay readable until you have checked the result')
    parser.add_argument('--procs', default=None,
        help='comma-separated bare process names to restrict to, e.g. "QCD_PT-470to600"')
    parser.add_argument('--target-size-gb', type=float, default=DEFAULT_TARGET_GB,
        help='approximate size of each merged file (default: {}). Chunking by SIZE rather'
             ' than by file count keeps the outputs uniform across processes whose per-job'
             ' files differ in size'.format(DEFAULT_TARGET_GB))
    parser.add_argument('--card-name', default=DEFAULT_CARD_NAME,
        help='card directory name for merged CRAB output (default: {}); local productions'
             ' keep their own card'.format(DEFAULT_CARD_NAME))
    parser.add_argument('--mode', choices=['local', 'condor'], default='local',
        help='local: hadd sequentially here. condor: one job per output file (default: local)')
    parser.add_argument('--force', action='store_true',
        help='re-merge and overwrite outputs that already exist (default: skip them, so an'
             ' interrupted run can simply be repeated). NOTE the skip is based on the output'
             ' file EXISTING, which an in-flight condor job has not created yet - so'
             ' re-running in condor mode while merges are still queued submits a SECOND job'
             ' for the same output, and the two race on the final copy. Check the queue first')
    parser.add_argument('--verify', action='store_true',
        help='after merging (local mode only), reopen each output and check its entry count'
             ' equals the sum over its inputs')
    parser.add_argument('--dry-run', action='store_true', help='print what would be done')
    # condor-only
    parser.add_argument('--jobflavour', default='workday', help='condor job flavour (default: workday)')
    parser.add_argument('--max-running', type=int, default=None,
        help='cap how many merge jobs run at once (condor mode)')
    parser.add_argument('--condordir', default=None,
        help='where condor submit files go (default: <repo>/condor_postprocess)')
    parser.add_argument('--mem', type=int, default=4096, help='condor memory in MB (default: 4096)')
    parser.add_argument('--disk', type=int, default=20480, help='condor disk in MB (default: 20480)')
    args = parser.parse_args()

    dest = args.dest if args.dest is not None else args.input.rstrip('/') + '_merged'
    if os.path.abspath(dest) == os.path.abspath(args.input):
        raise SystemExit('ERROR: --dest must differ from --input')

    groups = discover(args.input, args.procs)
    if not groups:
        raise SystemExit('ERROR: no {} found under {}'.format(NTUPLE_GLOB, args.input))

    # ---- plan ----
    target_bytes = args.target_size_gb * BYTES_PER_GB
    tasks = []   # (out_path, inputs)
    print('{:<12} {:<22} {:<10} {:>7} {:>10}  {:>5}'.format(
        'family', 'proc', 'card', 'files', 'size', 'out'))
    print('-' * 76)
    tot_files = tot_bytes = tot_out = 0
    for (family, proc, card, outdir_rel) in sorted(groups):
        files = groups[(family, proc, card, outdir_rel)]
        outcard = card if card is not None else args.card_name
        outdir = os.path.join(dest, outdir_rel if card is not None
                              else os.path.join(outdir_rel, args.card_name))
        chunks = plan_chunks(files, target_bytes)
        size = sum(os.path.getsize(f) for f in files if os.path.exists(f))
        for i, chunk in enumerate(chunks):
            tasks.append((os.path.join(outdir, '{}{}.root'.format(MERGED_PREFIX, i)), chunk))
        print('{:<12} {:<22} {:<10} {:>7} {:>10}  {:>5}'.format(
            family, proc, outcard, len(files), format_bytes(size), len(chunks)))
        tot_files += len(files); tot_bytes += size; tot_out += len(chunks)
    print('-' * 76)
    print('{:<12} {:<22} {:<10} {:>7} {:>10}  {:>5}'.format(
        'TOTAL', '', '', tot_files, format_bytes(tot_bytes), tot_out))
    print('\ndest: {}'.format(dest))

    if not args.force:
        skipped = [t for t in tasks if os.path.exists(t[0])]
        tasks = [t for t in tasks if not os.path.exists(t[0])]
        if skipped:
            print('skipping {} output file(s) that already exist (--force to redo)'.format(len(skipped)))
    if not tasks:
        print('nothing to do.')
        return

    # ---- execute ----
    if args.mode == 'local':
        tmpdir = tempfile.mkdtemp(prefix='postprocess_')
        try:
            t0 = time.time()
            for i, (out_path, inputs) in enumerate(tasks):
                cmds = hadd_command(out_path, inputs, tmpdir)
                print('\n---- [{}/{}] {} ({} inputs) ----'.format(
                    i + 1, len(tasks), out_path, len(inputs)))
                if args.dry_run:
                    for c in abbreviate(cmds):
                        print('   {}'.format(c))
                    continue
                rc = subprocess.call(['bash', '-c', ' && '.join(cmds)])
                if rc != 0:
                    print('ERROR: hadd failed for {} (exit {})'.format(out_path, rc), file=sys.stderr)
                    continue
                print('   done in {:.0f}s total elapsed'.format(time.time() - t0))
                if args.verify:
                    verify_one(out_path, inputs)
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)
    else:
        import condortools as ct
        condordir = args.condordir or os.path.join(REPO_DIR, 'condor_postprocess')
        if args.dry_run:
            for out_path, inputs in tasks:
                print('\n---- {} ({} inputs) ----'.format(out_path, len(inputs)))
                for c in abbreviate(hadd_command(out_path, inputs, CONDOR_SCRATCH)):
                    print('   {}'.format(c))
            print('\n(dry run: would submit {} condor job(s) from {})'.format(len(tasks), condordir))
            return
        if not os.path.exists(condordir):
            os.makedirs(condordir)
        cwd = os.getcwd()
        os.chdir(condordir)
        try:
            commandsets = [hadd_command(out_path, inputs, CONDOR_SCRATCH)
                           for out_path, inputs in tasks]
            concurrency = None
            if args.max_running is not None:
                concurrency = ct.concurrency_limit_for_max_running(args.max_running, 'jcpostproc')
            ct.submitCommandsAsCondorJobs('postprocess', commandsets, home='auto',
                                          cpus=1, mem=args.mem, disk=args.disk,
                                          jobflavour=args.jobflavour,
                                          concurrency_limits=concurrency)
        finally:
            os.chdir(cwd)
        print('\nsubmitted {} merge job(s); submit files and logs in {}'.format(len(tasks), condordir))


def verify_one(out_path, inputs):
    '''Reopen a merged file and check its entry count against the sum over its inputs.
    '''
    try:
        import uproot
        with uproot.open(out_path) as f:
            got = f['tree'].num_entries
        want = 0
        for p in inputs:
            with uproot.open(p) as f:
                want += f['tree'].num_entries
        flag = 'OK' if got == want else 'MISMATCH'
        print('   verify: {} entries (inputs sum to {}) - {}'.format(got, want, flag))
        return got == want
    except Exception as e:
        print('   verify: FAILED to check ({}: {})'.format(type(e).__name__, e), file=sys.stderr)
        return False


if __name__ == '__main__':
    main()
