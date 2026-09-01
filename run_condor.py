#!/usr/bin/env python3

'''
Submit a run.sh generation+reconstruction job to HTCondor.

This is a thin wrapper: every argument is named (no positional arguments at
all - deliberately, so a command line is self-explanatory without having to
cross-reference run.sh's own positional-arg order to know what a bare
number means), and maps 1:1 onto one of run.sh's own positional arguments
(see run.sh's own header) - forwarded unchanged, run.sh itself is not
touched by any of this - except NEVENT, which is given via exactly one of
--nevent (a plain event count) or --target-njets (a target JET count
instead - translated to NEVENT here, in this script, before run.sh is ever
invoked).

--output-path is REQUIRED (run.sh itself still falls back to its own
hardcoded default if invoked directly without going through this script -
that default is untouched, but this wrapper no longer lets you fall into it
by accident). Note there are two different, unrelated "output directories"
involved:
  - --output-path (required): where the JOB'S OWN detector-level output
    (events_delphes_*.root, ntuple_*.root) is written - this is run.sh's
    OUTPUT_PATH, positional arg 6.
  - -o/--outputdir (optional, default "condor"): where THIS SCRIPT writes
    the condor submission files (.sh/.txt/log) for the job it submits - has
    nothing to do with the job's own detector output.

Usage:
  python run_condor.py --proc PROC (--nevent NEVENT | --target-njets NJETS) --output-path OUTPUT_PATH --batch-size BATCH_SIZE --jobnum JOBNUM [--delphes-cards DELPHES_CARD_NAMES]

Example:
  # one card, offline reconstruction, no pileup
  python run_condor.py --proc jetclass1/HToBB --nevent 5000 --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250 --jobnum 0 --delphes-cards onlyFatJetNoPU

  # both offline and HLT reconstruction, no pileup
  python run_condor.py --proc jetclass1/HToBB --nevent 5000 --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250 --jobnum 0 --delphes-cards onlyFatJetNoPU,onlyFatJetHLTNoPU

  # a one-off/exploratory run, written to a separate output directory
  python run_condor.py --proc jetclass1/HToBB --nevent 100 --output-path /eos/user/l/llambrec/jetclass/output_timing_test --batch-size 100 --jobnum 0 --delphes-cards onlyFatJetNoPU

  # target a number of JETS instead of events: NEVENT is derived here (in
  # this script, not run.sh) from --target-njets using the process's
  # measured jets-per-event ratio in --njets-map (default:
  # run_configs/njets_per_nevents.json, see testing/test-generation-time/
  # plot_njets.py for how those ratios were measured)
  python run_condor.py --proc jetclass1/HToBB --target-njets 150000 --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250 --jobnum 0 --delphes-cards onlyFatJetNoPU
'''

import os
import sys
import json
import argparse

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jobtools'))
import condortools as ct
from download_gridpack import normalize_proc

THISDIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_NJETS_MAP = os.path.join(THISDIR, 'run_configs', 'njets_per_nevents.json')
# run.sh's own default for DELPHES_CARD_NAMES (positional arg 5) - mirrored
# here (not imported - run.sh has no importable defaults) only so that
# OUTPUT_PATH (positional arg 6, always given now that --output-path is
# required) can still be placed correctly even when delphes_cards is
# omitted; run.sh's own behavior/default is otherwise completely untouched
RUNSH_DEFAULT_DELPHES_CARDS = 'onlyFatJet'


def validate_proc(proc, thisdir):
    '''
    Sanity-check that `proc` (run.sh's PROC positional arg, e.g.
    "jetclass1/HToBB/precompiled") actually resolves to a runnable process
    config directory under gen_configs/, before ever submitting a job for
    it - catches the mistake that motivated this check: passing
    "jetclass1/HToBB" (missing the "/precompiled" or "/raw" mode suffix).

    run.sh's own `cp -r $GENCFG_PATH/$PROC/* proc_base/` does NOT fail
    loudly on that mistake - with the suffix missing, $PROC only has
    subdirectories (precompiled/, raw/) under it, so that cp copies those
    SUBDIRECTORIES themselves into proc_base/ instead of the process' own
    MG5/Pythia8 config files. proc_base/run_gen.sh then doesn't exist, run.sh
    falls back to run_gen_default.sh, which has nothing real to generate
    from - the job still runs to completion and exits 0, just with an
    empty/near-empty ntuple (a handful of KB, no real jets) instead of a
    real crash. Exactly this happened once submitting
    output_jetclass1_5M_sync_mg311 (100 jobs, "/precompiled" dropped from
    every --proc) - all 100 "succeeded" in a few minutes with ~7.5KB
    ntuples before it was noticed.

    Every real leaf process directory in gen_configs/ (jetclass1/*/precompiled,
    jetclass1/*/raw, jetclass2/train_*) has at least one regular file
    directly inside it; a directory holding only further subdirectories
    (e.g. gen_configs/jetclass1/HToBB itself, vs. .../HToBB/precompiled) is
    exactly the invalid case above. Checking for "any file directly inside",
    rather than hardcoding expected filenames (which differ between
    jetclass1's py8.dat/mg5_step2_templ.dat and jetclass2's own naming,
    e.g. train_qcd's py8_main.cc/py8_params.dat/py8_templ.dat/run_gen.sh),
    keeps this generic to whatever gen_configs/ currently holds or grows to.
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


def nevent_for_target_njets(proc, target_njets, njets_map_path):
    '''
    Translate a target jet count into NEVENT for `proc`, using the
    (process -> jets per event) ratios in the JSON file at njets_map_path
    (keyed by the same bare process name normalize_proc() extracts from
    PROC, e.g. "HToBB" out of "jetclass1/HToBB" - see run_configs/
    njets_per_nevents.json). Deliberately raises rather than falling back
    to anything if the map is missing or doesn't cover this process -
    silently guessing NEVENT would be worse than an explicit error here.
    '''
    if not os.path.exists(njets_map_path):
        raise Exception(
            '--target-njets was given but the njets-per-event map {!r} does not exist - '
            'either create it (see run_configs/njets_per_nevents.json for the format: '
            '{{"<process>": <jets per event>, ...}}, e.g. from '
            'testing/test-generation-time/plot_njets.py\'s fitted ratios) or point '
            '--njets-map at an existing one.'.format(njets_map_path))
    with open(njets_map_path) as f:
        njets_map = json.load(f)
    short = normalize_proc(proc)
    if short not in njets_map:
        raise Exception(
            '--target-njets was given but {!r} (process {!r}) has no entry in {!r}. '
            'Known processes: {}'.format(short, proc, njets_map_path, ', '.join(sorted(njets_map))))
    ratio = njets_map[short]
    if ratio <= 0:
        raise Exception('{!r} has a non-positive jets-per-event ratio ({}) in {!r}'.format(
            short, ratio, njets_map_path))
    nevent = round(target_njets / ratio)
    print('Translating target {:g} jets for {} (ratio {:g} jets/event, from {}) -> {} events'.format(
        target_njets, short, ratio, njets_map_path, nevent))
    return nevent


if __name__=='__main__':

    parser = argparse.ArgumentParser(
        description='Submit a run.sh job to condor. All arguments (NEVENT, however it was'
                     ' arrived at, included) are forwarded to run.sh unchanged.')
    parser.add_argument('--proc', required=True,
        help='process name, e.g. jetclass1/HToBB (same as run.sh positional arg 1)')
    nevent_group = parser.add_mutually_exclusive_group(required=True)
    nevent_group.add_argument('--nevent', type=int, default=None,
        help='total number of events (same as run.sh positional arg 2, but given as a flag'
             ' here rather than positionally - see --target-njets for why)')
    nevent_group.add_argument('--target-njets', type=float, default=None,
        help='target number of jets instead of NEVENT - translated to NEVENT here (not in'
             ' run.sh) via --njets-map')
    parser.add_argument('--njets-map', default=DEFAULT_NJETS_MAP,
        help='JSON file mapping process name -> jets per event, used only with --target-njets'
             ' (default: run_configs/njets_per_nevents.json)')
    parser.add_argument('--output-path', required=True,
        help='REQUIRED: detector-output directory (same as run.sh positional arg 6) - where'
             ' this job\'s events_delphes_*.root/ntuple_*.root end up. Not to be confused with'
             ' -o/--outputdir below (a different thing - see module docstring)')
    parser.add_argument('--batch-size', type=int, required=True,
        help='number of events generated per batch (same as run.sh positional arg 3,'
             ' NEVENT_GEN there) - run.sh splits NEVENT into NEVENT/BATCH_SIZE batches,'
             ' each its own MG5+Pythia8+Delphes call, merged (hadd) at the end; must divide'
             ' NEVENT evenly, since run.sh drops any remainder rather than generating it')
    parser.add_argument('--jobnum', type=int, required=True,
        help='job number, used for output naming (same as run.sh positional arg 4)')
    parser.add_argument('--delphes-cards', default=None,
        help='comma-separated Delphes card names, e.g. onlyFatJet,onlyFatJetHLT'
             ' (same as run.sh optional positional arg 5; if omitted, run.sh\'s own default'
             ' ("{}") is passed explicitly, so --output-path still lands in the right'
             ' positional slot for run.sh)'.format(RUNSH_DEFAULT_DELPHES_CARDS))
    parser.add_argument('--keep-delphes-output', action='store_true',
        help='also copy events_delphes_*.root to --output-path, not just the ntuple (same as'
             ' run.sh positional arg 7; default: off - production runs only need the ntuples,'
             ' the Delphes ROOT file is still produced and used locally to make the ntuple'
             ' either way, it just isn\'t copied out unless this is set)')
    parser.add_argument('-o', '--outputdir', default='condor',
        help='directory to write condor submission files into (default: condor) - NOT the'
             ' detector-output directory, see --output-path and module docstring')
    parser.add_argument('--cpus', type=int, default=1)
    parser.add_argument('--mem', type=int, default=2048,
        help='requested memory in MB (default: 2048)')
    parser.add_argument('--disk', type=int, default=20480,
        help='requested disk in MB (default: 20480)')
    parser.add_argument('--jobflavour', default='workday',
        help='HTCondor job flavour, see https://batchdocs.web.cern.ch/local/submit.html'
             ' (default: workday, i.e. up to 8h)')
    parser.add_argument('--extra-env', default=None,
        help='comma-separated KEY=VALUE pairs, exported in the job before run.sh runs (e.g.'
             ' --extra-env MG5_PATH=/path/to/other/MG5,GRIDPACK_CACHE=/path/to/other/cache) -'
             ' for one-off toolchain-comparison runs without editing run.sh itself; MG5_PATH'
             ' is the only run.sh variable that actually reads an override this way (see its'
             ' own comment), GRIDPACK_CACHE is read directly by gen_configs/'
             ' run_gen_precompiled.sh/populate_gridpack_cache.sh, not run.sh')
    args = parser.parse_args()

    thisdir = os.path.dirname(os.path.abspath(__file__))
    runsh = os.path.join(thisdir, 'run.sh')
    if not os.path.exists(runsh):
        raise Exception('run.sh not found at {}'.format(runsh))

    validate_proc(args.proc, thisdir)

    if args.target_njets is not None:
        nevent = nevent_for_target_njets(args.proc, args.target_njets, args.njets_map)
    else:
        nevent = args.nevent

    # DELPHES_CARD_NAMES (run.sh positional arg 5) must be filled in explicitly
    # if omitted, since OUTPUT_PATH (arg 6) is always given now
    delphes_cards = args.delphes_cards if args.delphes_cards is not None else RUNSH_DEFAULT_DELPHES_CARDS
    keep_delphes_output = 'true' if args.keep_delphes_output else 'false'
    runsh_args = [args.proc, str(nevent), str(args.batch_size), str(args.jobnum), delphes_cards,
                  args.output_path, keep_delphes_output]
    command = '{} {}'.format(runsh, ' '.join(runsh_args))

    outputdir = os.path.abspath(args.outputdir)
    if not os.path.exists(outputdir):
        os.makedirs(outputdir)
    jobname = 'run_{}_{}'.format(args.proc.replace('/', '_'), args.jobnum)

    # explicit cd, in addition to jobtools' own cwd-based cd, so the job
    # works regardless of where run_condor.py happened to be invoked from
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

    # chdir into the output directory so the job/executable/log file names
    # jobtools writes (bare names, e.g. "run_..._0.sh") and the directory
    # condor_submit itself runs from agree - condortools.submitCondorJob()
    # does its own "cd <dir of jdname>; condor_submit <basename>", so a
    # directory prefix baked into the name would otherwise be applied twice
    cwd = os.getcwd()
    os.chdir(outputdir)
    try:
        ct.submitCommandsAsCondorJob(
            jobname,
            commands,
            home='auto',
            cpus=args.cpus,
            mem=args.mem,
            disk=args.disk,
            jobflavour=args.jobflavour,
        )
    finally:
        os.chdir(cwd)

    print('Submitted condor job for proc={} jobnum={} nevent={} output_path={} (cards={}, keep_delphes_output={})'.format(
        args.proc, args.jobnum, nevent, args.output_path, delphes_cards, keep_delphes_output))
    print('Job description: {}'.format(os.path.join(outputdir, jobname + '.txt')))
