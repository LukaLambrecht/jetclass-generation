#!/usr/bin/env python3

'''
Submit --njobs run_condor.py jobs per process, for one or more processes -
run_condor.py itself only ever submits a single job for a single process,
this is the loop around it.

NEVENT (or the target jet count, via --target-njets-per-job) is PER JOB, not
split across jobs - each of the --njobs jobs for a given process
independently generates that many events/jets, exactly as if you'd called
run_condor.py that many times by hand with the same NEVENT and different
JOBNUM. JOBNUM itself is swept from --jobnum-base to --jobnum-base+njobs-1
for each process (reused across processes, not globally unique - fine,
since each process already gets its own output subdirectory, same
reasoning as testing/test-generation-time/run_timing_scan.py's own
--jobnum-base).

--output-path is REQUIRED (this is run.sh's OUTPUT_PATH, positional arg 6 -
where the jobs' own events_delphes_*.root/ntuple_*.root end up; NOT the
same thing as -o/--outputdir, which is where THIS script's condor
submission files go - see run_condor.py's own docstring for the same
distinction).

This is a thin loop: every actual job is a separate `python run_condor.py
...` subprocess call, so all the real submission logic (including the
--nevents-per-job/--target-njets-per-job -> NEVENT translation) lives
there, unchanged - this script only builds the (process, jobnum) grid and
forwards everything else.

Every argument is named (no positional arguments at all - same reasoning as
run_condor.py: a command line should be self-explanatory without having to
know run.sh's own positional-arg order to know what a bare number means).

Usage:
  # 10 jobs of 5000 events each, for 2 processes (20 condor jobs total)
  python run_condor_loop.py --procs jetclass1/HToBB,jetclass1/HToCC --njobs 10 \\
      --nevents-per-job 5000 --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250

  # same, but targeting a jet count per job instead (see run_condor.py's own
  # --target-njets docs for the njets-per-event map this needs)
  python run_condor_loop.py --procs jetclass1/HToBB,jetclass1/HToCC --njobs 10 \\
      --target-njets-per-job 150000 --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250

  # both offline and HLT cards, no pileup
  python run_condor_loop.py --procs jetclass1/HToBB,jetclass1/HToCC --njobs 10 \\
      --nevents-per-job 5000 --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250 \\
      --delphes-cards onlyFatJetNoPU,onlyFatJetHLTNoPU
'''

import os
import sys
import argparse
import subprocess

THISDIR = os.path.dirname(os.path.abspath(__file__))
RUN_CONDOR_PY = os.path.join(THISDIR, 'run_condor.py')
sys.path.insert(0, THISDIR)
from run_condor import RUNSH_DEFAULT_DELPHES_CARDS, validate_proc


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Submit --njobs run_condor.py jobs per process, for one or more processes.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--procs', required=True,
        help='comma-separated process names, e.g. jetclass1/HToBB,jetclass1/HToCC'
             ' (each forwarded to run_condor.py as its own PROC, unchanged)')
    parser.add_argument('--njobs', type=int, required=True,
        help='number of jobs to submit per process (each with the same'
             ' --nevents-per-job/--target-njets-per-job)')
    parser.add_argument('--jobnum-base', type=int, default=0,
        help='first JOBNUM to use per process; each subsequent job gets jobnum_base+i'
             ' (reused across processes, not globally unique - see module docstring)')
    nevent_group = parser.add_mutually_exclusive_group(required=True)
    nevent_group.add_argument('--nevents-per-job', type=int, default=None,
        help='total number of events PER JOB (forwarded to run_condor.py as --nevent)')
    nevent_group.add_argument('--target-njets-per-job', type=float, default=None,
        help='target number of jets PER JOB instead of --nevents-per-job (forwarded to'
             ' run_condor.py as --target-njets - see its own docs for the translation)')
    parser.add_argument('--njets-map', default=None,
        help='forwarded to run_condor.py as --njets-map, if given (default: let run_condor.py'
             ' use its own default, run_configs/njets_per_nevents.json)')
    parser.add_argument('--output-path', required=True,
        help='REQUIRED: detector-output directory (same as run.sh positional arg 6, forwarded'
             ' to run_condor.py as --output-path) - where every job\'s events_delphes_*.root/'
             ' ntuple_*.root ends up. Not to be confused with -o/--outputdir below (a different'
             ' thing - see module docstring)')
    parser.add_argument('--batch-size', type=int, required=True,
        help='number of events generated per batch, forwarded unchanged to run_condor.py'
             ' (same as run.sh positional arg 3, NEVENT_GEN there - see run_condor.py\'s own'
             ' docs for what this does and why it must divide the per-job NEVENT evenly)')
    parser.add_argument('--delphes-cards', default=None,
        help='comma-separated Delphes card names (forwarded unchanged - see run_condor.py)')
    parser.add_argument('--keep-delphes-output', action='store_true',
        help='forwarded to run_condor.py as --keep-delphes-output (default: off - production'
             ' runs only need the ntuples, see run_condor.py\'s own docs)')
    parser.add_argument('-o', '--outputdir', default='condor',
        help='directory to write condor submission files into (forwarded to run_condor.py) -'
             ' NOT the detector-output directory, see --output-path and module docstring')
    parser.add_argument('--cpus', type=int, default=1)
    parser.add_argument('--mem', type=int, default=2048, help='requested memory in MB')
    parser.add_argument('--disk', type=int, default=20480, help='requested disk in MB')
    parser.add_argument('--jobflavour', default='workday',
        help='HTCondor job flavour, see https://batchdocs.web.cern.ch/local/submit.html')
    parser.add_argument('--extra-env', default=None,
        help='forwarded unchanged to run_condor.py as --extra-env - see its own docs')
    args = parser.parse_args()

    procs = [p.strip() for p in args.procs.split(',') if p.strip()]
    if not procs:
        raise Exception('--procs did not contain any process names')
    # validate ALL requested procs upfront, before creating any output
    # directory or submitting a single job - run_condor.py itself validates
    # too, but only proc-by-proc as the loop below reaches it, so a mistake
    # affecting every proc (e.g. a missing "/precompiled" suffix applied to
    # the whole --procs list - see validate_proc()'s own docstring for the
    # incident that motivated this) would otherwise still submit everything
    # up to the first bad one before failing
    for proc in procs:
        validate_proc(proc, THISDIR)
    cards = [c.strip() for c in
             (args.delphes_cards if args.delphes_cards is not None else RUNSH_DEFAULT_DELPHES_CARDS).split(',')
             if c.strip()]

    # pre-create every (process, card) output subdirectory ONCE, serially,
    # before submitting any jobs - run.sh's own "mkdir -p" (done
    # independently by every job right before it copies its output to EOS)
    # is NOT safe against this: when the shared parent directory doesn't
    # exist yet at all and many jobs race to create it for the first time
    # simultaneously, EOS's FUSE client on some worker nodes can end up
    # with a stale/negative cache entry for it that a few in-job retries
    # don't reliably clear, causing that job's copy-to-EOS step to fail for
    # real (this is exactly what happened in an earlier 100-job test - see
    # testing/test-generation-time/README.md). Doing it here instead, one
    # directory at a time from a single process before any job starts,
    # means no worker node ever has to create a brand-new shared directory.
    print('Pre-creating output directories...')
    for proc in procs:
        for card in cards:
            d = os.path.join(args.output_path, proc, card)
            os.makedirs(d, exist_ok=True)
            print('  {}'.format(d))

    n_submitted, n_failed = 0, 0
    for proc in procs:
        for i in range(args.njobs):
            jobnum = args.jobnum_base + i
            cmd = [sys.executable, RUN_CONDOR_PY, '--proc', proc]
            if args.target_njets_per_job is not None:
                cmd += ['--target-njets', str(args.target_njets_per_job)]
                if args.njets_map is not None:
                    cmd += ['--njets-map', args.njets_map]
            else:
                cmd += ['--nevent', str(args.nevents_per_job)]
            cmd += ['--output-path', args.output_path]
            cmd += ['--batch-size', str(args.batch_size), '--jobnum', str(jobnum)]
            if args.delphes_cards is not None:
                cmd += ['--delphes-cards', args.delphes_cards]
            if args.keep_delphes_output:
                cmd.append('--keep-delphes-output')
            cmd += ['-o', args.outputdir, '--cpus', str(args.cpus), '--mem', str(args.mem),
                    '--disk', str(args.disk), '--jobflavour', args.jobflavour]
            if args.extra_env:
                cmd += ['--extra-env', args.extra_env]

            print('=== proc={} jobnum={} ==='.format(proc, jobnum))
            ret = subprocess.run(cmd).returncode
            if ret == 0:
                n_submitted += 1
            else:
                n_failed += 1
                print('WARNING: run_condor.py exited with status {} for proc={} jobnum={}'.format(
                    ret, proc, jobnum))

    print('Submitted {} job(s) total ({} process(es) x {} job(s) each), {} failed to submit.'.format(
        n_submitted, len(procs), args.njobs, n_failed))
    if n_failed:
        sys.exit(1)
