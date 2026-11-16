#!/usr/bin/env python3

'''
Submit a run.sh generation+reconstruction job to HTCondor.

A thin wrapper: every argument is named, so a command line is self-explanatory,
and each maps onto one of run.sh's positional arguments and is forwarded
unchanged. The exception is NEVENT, given as exactly one of --nevent (an event
count) or --target-njets (a jet count, translated to NEVENT here).

Two unrelated "output directories" are involved:
  - --output-path (required): where the job's own ntuple_*.root are written,
    i.e. run.sh's OUTPUT_PATH.
  - -o/--outputdir (default "condor_jobs"): where this script writes the condor
    submission files for the job. It matches the .gitignore "condor_*" pattern,
    so job output stays out of git.

Usage:
  python run_condor.py --backend BACKEND --proc PROC (--nevent NEVENT | --target-njets NJETS) --output-path OUTPUT_PATH --batch-size BATCH_SIZE --jobnum JOBNUM [--backend-opts OPTS]

Example:
  # one card, offline reconstruction, no pileup
  python run_condor.py --backend delphes --proc jetclass1/HToBB --nevent 5000 --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250 --jobnum 0 --backend-opts onlyFatJetNoPU

  # both offline and HLT reconstruction, no pileup
  python run_condor.py --backend delphes --proc jetclass1/HToBB --nevent 5000 --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250 --jobnum 0 --backend-opts onlyFatJetNoPU,onlyFatJetHLTNoPU

  # a one-off run, written to a separate output directory
  python run_condor.py --backend delphes --proc jetclass1/HToBB --nevent 100 --output-path /eos/user/l/llambrec/jetclass/output_timing_test --batch-size 100 --jobnum 0 --backend-opts onlyFatJetNoPU

  # the same process through CMS full simulation - ~2 min/event, so a job is
  # sized in tens of events, not thousands
  python run_condor.py --backend fullsim --proc jetclass1/HToBB --nevent 20 --output-path /eos/user/l/llambrec/jetclass/output_fullsim_test --batch-size 10 --jobnum 0

  # target a number of jets instead of events: NEVENT is derived here from
  # --target-njets using the process' measured jets-per-event ratio (JETS_PER_EVENT
  # below - only the families that have one)
  python run_condor.py --proc jetclass1/HToBB --target-njets 150000 --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250 --jobnum 0 --delphes-cards onlyFatJetNoPU
'''

import os
import sys
import argparse

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jobtools'))
import condortools as ct

THISDIR = os.path.dirname(os.path.abspath(__file__))
# Measured jets per generated event, by gen_configs family and then by process, used to
# translate a target jet count into NEVENT (see --target-njets).
#
# A family mapped to None has no measured table yet, and --target-njets raises
# NotImplementedError for it rather than guessing. To add one, fit the ratios from a
# timing scan (testing/test-production-time/plot_njets.py) and fill in the dict.
JETS_PER_EVENT = {
    # fitted from testing/test-production-time/output_20260831_jetclass1/
    'jetclass1': {
        'HToBB':       1.0,
        'HToCC':       1.0,
        'HToGG':       1.0,
        'HToWW2Q1L':   1.0,
        'HToWW4Q':     1.0,
        'TTBar':       2.0,
        'TTBarLep':    1.5,
        'WToQQ':       1.0,
        'ZJetsToNuNu': 0.3,
        'ZToQQ':       1.0,
    },
    'jetclass2': None,
    # yields are known per pThat bin (see gen_configs/jetclass2sb/README.md) but have
    # not been collected into a table here
    'jetclass2sb': None,
}
# Each backend's own default BACKEND_OPTS, mirrored here because the backends are
# shell files with nothing importable. Needed only so OUTPUT_PATH still lands in
# the right positional slot for run.sh when --backend-opts is omitted. Keep in
# sync with BACKEND_DEFAULT_OPTS in backends/<backend>.sh.
BACKENDS = ('delphes', 'fullsim')
RUNSH_DEFAULT_OPTS = {
    'delphes': 'onlyFatJet',
    'fullsim': 'offline+hlt',
}
# Requested memory per backend. A fullsim job runs the full HLT menu and RECO,
# which peak at ~3 GB, and is simply killed by condor at the delphes default.
DEFAULT_MEM = {
    'delphes': 2048,
    'fullsim': 4096,
}


def output_subdirs(backend, backend_opts):
    '''The subdirectories a backend writes under $OUTPUT_PATH/$PROC, given its
    BACKEND_OPTS. run_condor_loop.py uses this to pre-create them.'''
    if backend == 'delphes':
        return [c.strip() for c in backend_opts.split(',') if c.strip()]
    if backend == 'fullsim':
        return ['fullsim_{}'.format(backend_opts)]
    raise Exception('unknown backend {!r}'.format(backend))


def validate_proc(proc, thisdir):
    '''
    Check that `proc` resolves to a runnable process config under gen_configs/
    before any job is submitted. This catches a dropped mode suffix, e.g.
    "jetclass1/HToBB" instead of "jetclass1/HToBB/precompiled".

    run.sh does not fail loudly on that: with the suffix missing, $PROC holds
    only subdirectories, so its `cp -r` copies those subdirectories into
    proc_base/ rather than the process' generator configs. run_gen.sh is then
    absent, run.sh falls back to run_gen_default.sh, and the job exits 0 with a
    near-empty ntuple instead of crashing.

    Every real leaf process directory has at least one regular file directly
    inside it, while a directory holding only subdirectories is exactly the
    invalid case. Testing for "any file directly inside" rather than for expected
    filenames keeps this generic, since the per-family naming differs.
    '''
    procdir = os.path.join(thisdir, 'gen_configs', proc)
    if not os.path.isdir(procdir):
        raise Exception(
            '--proc {!r} does not resolve to a directory under gen_configs/ '
            '({!r} not found).'.format(proc, procdir))
    entries = os.listdir(procdir)
    if not any(os.path.isfile(os.path.join(procdir, e)) for e in entries):
        subdirs = sorted(e for e in entries if os.path.isdir(os.path.join(procdir, e)))
        hint = ''
        if subdirs:
            hint = ' Did you forget a mode suffix, e.g. {}?'.format(
                ' or '.join('{!r}'.format(proc + '/' + s) for s in subdirs))
        raise Exception(
            '--proc {!r} (gen_configs/{}) has no files directly inside it - it does not look '
            'like a runnable process config (only subdirector{} found: {}). run.sh would not '
            'fail loudly on this - see validate_proc()\'s own docstring for why.{}'.format(
                proc, proc, 'y' if len(subdirs) == 1 else 'ies', ', '.join(subdirs) or '<none>', hint))


def split_proc(proc):
    '''(family, process) for a PROC path, e.g. 'jetclass1/HToBB/precompiled' ->
    ('jetclass1', 'HToBB').

    Anything after the process name, such as jetclass1's precompiled/raw mode, is a
    variant of the same process and is dropped.
    '''
    parts = [p for p in proc.split('/') if p]
    if len(parts) < 2:
        raise ValueError(
            'cannot tell the family and process apart in --proc {!r}: expected'
            ' <family>/<process>[/<mode>], e.g. jetclass1/HToBB/precompiled or'
            ' jetclass2/train_qcd'.format(proc))
    return parts[0], parts[1]


def jets_per_event(proc):
    '''The measured jets per generated event for `proc`, from JETS_PER_EVENT.

    Raises NotImplementedError for a family that has no table yet, and ValueError for an
    unknown family or process. Never falls back to a guess: silently inventing a ratio
    would mis-size a whole production.
    '''
    family, process = split_proc(proc)
    if family not in JETS_PER_EVENT:
        raise ValueError(
            'unknown gen_configs family {!r} (from --proc {!r}). Known families: {}'.format(
                family, proc, ', '.join(sorted(JETS_PER_EVENT))))
    table = JETS_PER_EVENT[family]
    if table is None:
        raise NotImplementedError(
            'no jets-per-event table for the {!r} family yet, so a target jet count'
            ' cannot be translated into NEVENT for --proc {!r}. Give an explicit event'
            ' count instead, or measure the ratios and add them to JETS_PER_EVENT in'
            ' run_condor.py (see its own comment).'.format(family, proc))
    if process not in table:
        raise ValueError(
            'process {!r} (from --proc {!r}) has no entry in the {!r} jets-per-event'
            ' table. Known processes: {}'.format(
                process, proc, family, ', '.join(sorted(table))))
    ratio = table[process]
    if ratio <= 0:
        raise ValueError('{!r} has a non-positive jets-per-event ratio ({})'.format(
            process, ratio))
    return ratio


def nevent_for_target_njets(proc, target_njets):
    '''Translate a target jet count into NEVENT for `proc`.

    See jets_per_event() for where the ratio comes from and when this raises.
    '''
    ratio = jets_per_event(proc)
    nevent = round(target_njets / ratio)
    print('Translating target {:g} jets for {} (ratio {:g} jets/event) -> {} events'.format(
        target_njets, proc, ratio, nevent))
    return nevent


if __name__=='__main__':

    parser = argparse.ArgumentParser(
        description='Submit a run.sh job to condor. All arguments (NEVENT, however it was'
                     ' arrived at, included) are forwarded to run.sh unchanged.')
    parser.add_argument('--backend', required=True, choices=BACKENDS,
        help='detector simulation backend (same as run.sh positional arg 1): "delphes" (fast,'
             ' what every dataset so far was made with) or "fullsim" (CMS full simulation in'
             ' CMSSW - about 2 min/event, so size jobs accordingly)')
    parser.add_argument('--proc', required=True,
        help='process name, e.g. jetclass1/HToBB (same as run.sh positional arg 2)')
    nevent_group = parser.add_mutually_exclusive_group(required=True)
    nevent_group.add_argument('--nevent', type=int, default=None,
        help='total number of events (same as run.sh positional arg 3, but given as a flag'
             ' here rather than positionally - see --target-njets for why)')
    nevent_group.add_argument('--target-njets', type=float, default=None,
        help='target number of jets instead of NEVENT - translated to NEVENT here (not in'
             ' run.sh) via this process\' measured jets-per-event ratio. Only available'
             ' for families with a measured table (see JETS_PER_EVENT in run_condor.py);'
             ' raises for the others')
    parser.add_argument('--output-path', required=True,
        help='REQUIRED: output directory (same as run.sh positional arg 7) - where'
             ' this job\'s ntuple_*.root end up. Not to be confused with'
             ' -o/--outputdir below (a different thing - see module docstring)')
    parser.add_argument('--batch-size', type=int, required=True,
        help='number of events generated per batch (same as run.sh positional arg 4,'
             ' NEVENT_GEN there) - run.sh splits NEVENT into NEVENT/BATCH_SIZE batches,'
             ' each its own MG5+Pythia8+Delphes call, merged (hadd) at the end; must divide'
             ' NEVENT evenly, since run.sh drops any remainder rather than generating it')
    parser.add_argument('--jobnum', type=int, required=True,
        help='job number, used for output naming (same as run.sh positional arg 5)')
    parser.add_argument('--backend-opts', '--delphes-cards', dest='backend_opts', default=None,
        help='backend-specific options (same as run.sh optional positional arg 6). For'
             ' delphes: comma-separated card names, e.g. onlyFatJet,onlyFatJetHLT (default'
             ' "{}"). For fullsim: "offline+hlt" (default) or "offline". If omitted, the'
             ' backend\'s own default is passed explicitly, so --output-path still lands in'
             ' the right positional slot for run.sh. --delphes-cards is accepted as an alias,'
             ' so existing delphes command lines keep working.'.format(RUNSH_DEFAULT_OPTS['delphes']))
    parser.add_argument('--keep-intermediate', '--keep-delphes-output', dest='keep_intermediate',
        action='store_true',
        help='also copy the backend\'s intermediate detector files to --output-path, not just'
             ' the ntuple (same as run.sh positional arg 8; delphes: events_delphes_*.root,'
             ' fullsim: the AODSIM files). Default: off - production runs only need the'
             ' ntuples; the intermediate files are still produced and used locally to make the'
             ' ntuple either way, they just are not copied out unless this is set')
    parser.add_argument('-o', '--outputdir', default='condor_jobs',
        help='directory to write condor submission files into (default: condor_jobs) - NOT the'
             ' detector-output directory, see --output-path and module docstring')
    parser.add_argument('--cpus', type=int, default=1)
    parser.add_argument('--mem', type=int, default=None,
        help='requested memory in MB (default: {} for delphes, {} for fullsim - CMSSW\'s'
             ' HLT and RECO steps need several GB, a delphes job needs well under one)'.format(
                 DEFAULT_MEM['delphes'], DEFAULT_MEM['fullsim']))
    parser.add_argument('--disk', type=int, default=20480,
        help='requested disk in MB (default: 20480)')
    parser.add_argument('--jobflavour', default='workday',
        help='HTCondor job flavour, see https://batchdocs.web.cern.ch/local/submit.html'
             ' (default: workday, i.e. up to 8h)')
    parser.add_argument('--max-running', type=int, default=None,
        help='let at most this many of these jobs RUN at the same time, the rest waiting'
             ' idle in the queue. Implemented as an HTCondor concurrency limit, which the'
             ' negotiator enforces across every cluster sharing --concurrency-limit-name -'
             ' which is what makes it work here, since this script submits one cluster per'
             ' job. See condortools.concurrency_limit_for_max_running() for the mechanism.'
             ' Every job of the same production must be submitted with the SAME'
             ' --max-running and --concurrency-limit-name for the throttle to mean what it says')
    parser.add_argument('--concurrency-limit-name', default=None,
        help='name of the concurrency limit used by --max-running (default: <user>_jetclass).'
             ' The names are a pool-wide namespace, so this should be something nobody else'
             ' would pick; jobs sharing a name share the limit')
    parser.add_argument('--extra-env', default=None,
        help='comma-separated KEY=VALUE pairs, exported in the job before run.sh runs (e.g.'
             ' --extra-env MG5_PATH=/path/to/other/MG5,GRIDPACK_CACHE=/path/to/other/cache) -'
             ' for one-off toolchain-comparison runs without editing run.sh itself; MG5_PATH'
             ' is the only run.sh variable that actually reads an override this way (see its'
             ' own comment), GRIDPACK_CACHE is read directly by gen_configs/'
             ' run_gen_precompiled.sh/populate_gridpack_cache.sh, not run.sh')
    args = parser.parse_args()

    mem = args.mem if args.mem is not None else DEFAULT_MEM[args.backend]

    concurrency_limits = None
    if args.max_running is not None:
        name = args.concurrency_limit_name or '{}_jetclass'.format(
            os.environ.get('USER', 'jetclass'))
        concurrency_limits, effective = ct.concurrency_limit_for_max_running(args.max_running, name)
        print('Throttling to at most {} running job(s) via concurrency_limits = {}'.format(
            effective, concurrency_limits))

    thisdir = os.path.dirname(os.path.abspath(__file__))
    runsh = os.path.join(thisdir, 'run.sh')
    if not os.path.exists(runsh):
        raise Exception('run.sh not found at {}'.format(runsh))

    validate_proc(args.proc, thisdir)

    if args.target_njets is not None:
        nevent = nevent_for_target_njets(args.proc, args.target_njets)
    else:
        nevent = args.nevent

    # BACKEND_OPTS must be filled in explicitly when omitted, since OUTPUT_PATH
    # comes after it positionally and is always given.
    backend_opts = args.backend_opts if args.backend_opts is not None else RUNSH_DEFAULT_OPTS[args.backend]
    keep_intermediate = 'true' if args.keep_intermediate else 'false'
    runsh_args = [args.backend, args.proc, str(nevent), str(args.batch_size), str(args.jobnum),
                  backend_opts, args.output_path, keep_intermediate]
    command = '{} {}'.format(runsh, ' '.join(runsh_args))

    outputdir = os.path.abspath(args.outputdir)
    if not os.path.exists(outputdir):
        os.makedirs(outputdir)
    jobname = 'run_{}_{}_{}'.format(args.backend, args.proc.replace('/', '_'), args.jobnum)

    # Explicit cd, on top of jobtools' own cwd-based one, so the job works
    # wherever run_condor.py was invoked from.
    commands = [
        'cd {}'.format(thisdir),
        'echo "###starting###"',
    ]
    if args.extra_env:
        for pair in args.extra_env.split(','):
            pair = pair.strip()
            if not pair:
                continue
            if '=' not in pair:
                raise Exception('--extra-env entries must be KEY=VALUE, got {!r}'.format(pair))
            commands.append('export {}'.format(pair))
    commands += [
        command,
        'echo "###done###"',
    ]

    # Submit from inside the output directory, so the bare file names jobtools
    # writes and the directory condor_submit runs from agree: submitCondorJob()
    # does its own "cd <dir of jdname>; condor_submit <basename>", so a directory
    # prefix in the name would be applied twice.
    cwd = os.getcwd()
    os.chdir(outputdir)
    try:
        ct.submitCommandsAsCondorJob(
            jobname,
            commands,
            home='auto',
            cpus=args.cpus,
            mem=mem,
            disk=args.disk,
            jobflavour=args.jobflavour,
            concurrency_limits=concurrency_limits,
        )
    finally:
        os.chdir(cwd)

    print('Submitted condor job for backend={} proc={} jobnum={} nevent={} output_path={}'
          ' (opts={}, keep_intermediate={})'.format(
              args.backend, args.proc, args.jobnum, nevent, args.output_path,
              backend_opts, keep_intermediate))
    print('Job description: {}'.format(os.path.join(outputdir, jobname + '.txt')))
