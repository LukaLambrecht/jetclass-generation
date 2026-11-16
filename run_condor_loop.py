#!/usr/bin/env python3

'''
Submit --njobs jobs per process, for one or more processes. run_condor.py
submits a single job for a single process; this is the loop around it.

NEVENT (or the target jet count, via --target-njets-per-job) is PER JOB, not
split across jobs: each of the --njobs jobs independently generates that many
events. JOBNUM runs from --jobnum-base to --jobnum-base+njobs-1 per process,
reused across processes rather than globally unique, since each process already
gets its own output subdirectory.

As in run_condor.py, --output-path (the jobs' ntuple_*.root) and -o/--outputdir
(this script's condor submission files) are two different directories.

By default all the jobs of one process go into one condor cluster, which is
tidier for the queue and is what lets --max-materialize throttle how many run at
a time. With --job-per-cluster each job is instead its own cluster, submitted
through a separate run_condor.py call; that is the only mode in which
--target-njets-per-job is translated by run_condor.py rather than here.

Every argument is named, so a command line is self-explanatory.

Usage:
  # 10 jobs of 5000 events each, for 2 processes (20 condor jobs total)
  python run_condor_loop.py --backend delphes --procs jetclass1/HToBB,jetclass1/HToCC --njobs 10 \\
      --nevents-per-job 5000 --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250

  # same, but targeting a jet count per job instead (see run_condor.py's own
  # --target-njets docs for the njets-per-event map this needs)
  python run_condor_loop.py --backend delphes --procs jetclass1/HToBB,jetclass1/HToCC --njobs 10 \\
      --target-njets-per-job 150000 --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250

  # both offline and HLT cards, no pileup
  python run_condor_loop.py --backend delphes --procs jetclass1/HToBB,jetclass1/HToCC --njobs 10 \\
      --nevents-per-job 5000 --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250 \\
      --backend-opts onlyFatJetNoPU,onlyFatJetHLTNoPU

  # a fullsim trial: one cluster per process, at most 200 of its jobs running at a time
  python run_condor_loop.py --backend fullsim --procs jetclass2/train_qcd --njobs 625 \\
      --nevents-per-job 320 --batch-size 80 --max-materialize 200 \\
      --output-path /eos/user/l/llambrec/jetclass/output_fullsim_630k_trial
'''

import os
import sys
import argparse
import subprocess

THISDIR = os.path.dirname(os.path.abspath(__file__))
RUN_CONDOR_PY = os.path.join(THISDIR, 'run_condor.py')
DEFAULT_NJETS_MAP = os.path.join(THISDIR, 'run_configs', 'njets_per_nevents.json')
sys.path.insert(0, THISDIR)
from run_condor import (BACKENDS, DEFAULT_MEM, RUNSH_DEFAULT_OPTS, nevent_for_target_njets,
                         output_subdirs, validate_proc)
sys.path.insert(0, os.path.join(THISDIR, 'jobtools'))
import condortools as ct


def submit_clusters(args, procs, backend_opts):
    '''Submit one condor cluster per process, holding all of its --njobs jobs.

    The per-job argument lists are built here rather than by calling run_condor.py
    once per job, so this repeats the small amount of translation that script does
    (NEVENT, the per-backend memory default, the concurrency limit). Everything
    that actually differs between the jobs of one process is just JOBNUM.
    '''
    runsh = os.path.join(THISDIR, 'run.sh')
    if not os.path.exists(runsh):
        raise Exception('run.sh not found at {}'.format(runsh))
    for pair in (args.extra_env or '').split(','):
        if pair.strip() and '=' not in pair:
            raise Exception('--extra-env entries must be KEY=VALUE, got {!r}'.format(pair))
    keep = 'true' if args.keep_intermediate else 'false'
    mem = args.mem if args.mem is not None else DEFAULT_MEM[args.backend]

    concurrency_limits = None
    if args.max_running is not None:
        name = args.concurrency_limit_name or '{}_jetclass'.format(
            os.environ.get('USER', 'jetclass'))
        concurrency_limits, effective = ct.concurrency_limit_for_max_running(args.max_running, name)
        print('Throttling to at most {} running job(s) ACROSS all clusters via'
              ' concurrency_limits = {}'.format(effective, concurrency_limits))
    if args.max_materialize is not None:
        print('Limiting EACH cluster to {} materialized job(s) at a time (max_materialize)'.format(
            args.max_materialize))

    outputdir = os.path.abspath(args.outputdir)
    if not os.path.exists(outputdir):
        os.makedirs(outputdir)

    # Submit from inside the output directory, as the per-job path does.
    cwd = os.getcwd()
    os.chdir(outputdir)
    try:
        for proc in procs:
            if args.target_njets_per_job is not None:
                nevent = nevent_for_target_njets(proc, args.target_njets_per_job,
                                                 args.njets_map or DEFAULT_NJETS_MAP)
            else:
                nevent = args.nevents_per_job
            arglists = [' '.join([args.backend, proc, str(nevent), str(args.batch_size),
                                  str(args.jobnum_base + i), backend_opts,
                                  args.output_path, keep])
                        for i in range(args.njobs)]
            jobname = 'run_{}_{}'.format(args.backend, proc.replace('/', '_'))
            print('=== {}: one cluster of {} job(s) ==='.format(proc, len(arglists)))
            ct.submitArgsAsCondorCluster(
                jobname, runsh, arglists,
                # Explicit cd, on top of jobtools' own, so the job works
                # wherever this script was invoked from.
                prelude=(['cd {}'.format(THISDIR), 'echo "###starting###"']
                         + ['export {}'.format(pp.strip())
                            for pp in (args.extra_env or '').split(',') if pp.strip()]),
                epilogue=['echo "###done###"'],
                home='auto', cpus=args.cpus, mem=mem, disk=args.disk,
                jobflavour=args.jobflavour,
                concurrency_limits=concurrency_limits,
                max_materialize=args.max_materialize)
    finally:
        os.chdir(cwd)
    print('Submitted {} cluster(s) of {} job(s) each ({} job(s) total).'.format(
        len(procs), args.njobs, len(procs) * args.njobs))


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
             ' to run_condor.py as --output-path) - where every job\'s '
             ' ntuple_*.root ends up. Not to be confused with -o/--outputdir below (a different'
             ' thing - see module docstring)')
    parser.add_argument('--batch-size', type=int, required=True,
        help='number of events generated per batch, forwarded unchanged to run_condor.py'
             ' (same as run.sh positional arg 4, NEVENT_GEN there - see run_condor.py\'s own'
             ' docs for what this does and why it must divide the per-job NEVENT evenly)')
    parser.add_argument('--backend', required=True, choices=BACKENDS,
        help='detector simulation backend, forwarded unchanged to run_condor.py - see its docs')
    parser.add_argument('--backend-opts', '--delphes-cards', dest='backend_opts', default=None,
        help='backend-specific options (forwarded unchanged - see run_condor.py). For delphes'
             ' this is the comma-separated card list, and --delphes-cards still works as an'
             ' alias')
    parser.add_argument('--keep-intermediate', '--keep-delphes-output', dest='keep_intermediate',
        action='store_true',
        help='forwarded to run_condor.py as --keep-intermediate (default: off - production'
             ' runs only need the ntuples, see run_condor.py\'s own docs)')
    parser.add_argument('-o', '--outputdir', default='condor_jobs',
        help='directory to write condor submission files into (forwarded to run_condor.py) -'
             ' NOT the detector-output directory, see --output-path and module docstring')
    parser.add_argument('--cpus', type=int, default=1)
    parser.add_argument('--mem', type=int, default=None,
        help='requested memory in MB; left to run_condor.py\'s own per-backend default'
             ' (2048 for delphes, 4096 for fullsim) if not given')
    parser.add_argument('--disk', type=int, default=20480, help='requested disk in MB')
    parser.add_argument('--jobflavour', default='workday',
        help='HTCondor job flavour, see https://batchdocs.web.cern.ch/local/submit.html')
    parser.add_argument('--max-materialize', type=int, default=None,
        help='let at most this many of a cluster\'s jobs exist in the queue at a time (idle +'
             ' running), the rest being created as earlier ones finish - HTCondor\'s own'
             ' late-materialization throttle, and the standard way to limit how many jobs run.'
             ' Note it is PER CLUSTER, i.e. per process here: with two processes and'
             ' --max-materialize 200, up to 400 jobs can run. Use --max-running instead (or as'
             ' well) for a cap across everything. Not available with --job-per-cluster, where'
             ' every job is its own cluster')
    parser.add_argument('--job-per-cluster', action='store_true',
        help='submit each job as its own cluster, via a separate run_condor.py call (the older'
             ' behaviour), instead of one cluster per process')
    parser.add_argument('--max-running', type=int, default=None,
        help='at most this many jobs RUN at a time, the rest waiting idle. Unlike'
             ' --max-materialize this is enforced by the negotiator ACROSS clusters, so it'
             ' covers every process this loop submits (and anything else using the same'
             ' --concurrency-limit-name). Works in both submission modes - see run_condor.py')
    parser.add_argument('--concurrency-limit-name', default=None,
        help='name of the concurrency limit used by --max-running (default: <user>_jetclass)'
             ' - see run_condor.py\'s own help')
    parser.add_argument('--extra-env', default=None,
        help='forwarded unchanged to run_condor.py as --extra-env - see its own docs')
    args = parser.parse_args()

    procs = [p.strip() for p in args.procs.split(',') if p.strip()]
    if not procs:
        raise Exception('--procs did not contain any process names')
    # Validate every requested process before creating any directory or
    # submitting anything. run_condor.py validates too, but only as the loop
    # reaches each process, so a mistake affecting the whole --procs list would
    # otherwise submit everything up to the first bad one before failing.
    for proc in procs:
        validate_proc(proc, THISDIR)
    backend_opts = args.backend_opts if args.backend_opts is not None \
        else RUNSH_DEFAULT_OPTS[args.backend]
    subdirs = output_subdirs(args.backend, backend_opts)

    # Create every (process, output subdirectory) pair here, serially, before any
    # job starts. run.sh's own "mkdir -p" is not enough: when many jobs race to
    # create the same brand-new shared directory, the EOS client on some worker
    # nodes keeps a negative cache entry that the in-job retries do not clear,
    # and that job's copy to EOS then fails for real. Creating them up front means
    # no worker node ever has to create a new shared directory.
    print('Pre-creating output directories...')
    for proc in procs:
        for sub in subdirs:
            d = os.path.join(args.output_path, proc, sub)
            os.makedirs(d, exist_ok=True)
            print('  {}'.format(d))

    if not args.job_per_cluster:
        submit_clusters(args, procs, backend_opts)
        sys.exit(0)

    if args.max_materialize is not None:
        raise Exception('--max-materialize needs the jobs of a process to share one cluster, '
                        'which --job-per-cluster disables; drop one of the two '
                        '(--max-running works in either mode)')

    n_submitted, n_failed = 0, 0
    for proc in procs:
        for i in range(args.njobs):
            jobnum = args.jobnum_base + i
            cmd = [sys.executable, RUN_CONDOR_PY, '--backend', args.backend, '--proc', proc]
            if args.target_njets_per_job is not None:
                cmd += ['--target-njets', str(args.target_njets_per_job)]
                if args.njets_map is not None:
                    cmd += ['--njets-map', args.njets_map]
            else:
                cmd += ['--nevent', str(args.nevents_per_job)]
            cmd += ['--output-path', args.output_path]
            cmd += ['--batch-size', str(args.batch_size), '--jobnum', str(jobnum)]
            if args.backend_opts is not None:
                cmd += ['--backend-opts', args.backend_opts]
            if args.keep_intermediate:
                cmd.append('--keep-intermediate')
            if args.max_running is not None:
                cmd += ['--max-running', str(args.max_running)]
            if args.concurrency_limit_name is not None:
                cmd += ['--concurrency-limit-name', args.concurrency_limit_name]
            cmd += ['-o', args.outputdir, '--cpus', str(args.cpus),
                    '--disk', str(args.disk), '--jobflavour', args.jobflavour]
            # left to run_condor.py's own per-backend default when not given
            if args.mem is not None:
                cmd += ['--mem', str(args.mem)]
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
