#!/usr/bin/env python3

'''
Submit a run.sh generation+reconstruction job to HTCondor.

This is a thin wrapper: the positional arguments are exactly run.sh's own
positional arguments (see run.sh's own header), forwarded unchanged. It
submits a single condor job that calls run.sh with those arguments, using
the submission tooling in jobtools/.

Usage:
  python run_condor.py PROC NEVENT NEVENT_GEN JOBNUM [DELPHES_CARD_NAMES]

Example:
  # one card, offline reconstruction, no pileup
  python run_condor.py jetclass1/HToBB 5000 250 0 onlyFatJetNoPU

  # both offline and HLT reconstruction, no pileup
  python run_condor.py jetclass1/HToBB 5000 250 0 onlyFatJetNoPU,onlyFatJetHLTNoPU
'''

import os
import sys
import argparse

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jobtools'))
import condortools as ct


if __name__=='__main__':

    parser = argparse.ArgumentParser(
        description='Submit a run.sh job to condor. Positional arguments are forwarded to run.sh unchanged.')
    parser.add_argument('proc',
        help='process name, e.g. jetclass1/HToBB (same as run.sh positional arg 1)')
    parser.add_argument('nevent', type=int,
        help='total number of events (same as run.sh positional arg 2)')
    parser.add_argument('nevent_gen', type=int,
        help='events per generation batch (same as run.sh positional arg 3)')
    parser.add_argument('jobnum', type=int,
        help='job number, used for output naming (same as run.sh positional arg 4)')
    parser.add_argument('delphes_cards', nargs='?', default=None,
        help='comma-separated Delphes card names, e.g. onlyFatJet,onlyFatJetHLT'
             ' (same as run.sh optional positional arg 5; if omitted, run.sh uses its own default)')
    parser.add_argument('-o', '--outputdir', default='condor',
        help='directory to write condor submission files into (default: condor)')
    parser.add_argument('--cpus', type=int, default=1)
    parser.add_argument('--mem', type=int, default=2048,
        help='requested memory in MB (default: 2048)')
    parser.add_argument('--disk', type=int, default=20480,
        help='requested disk in MB (default: 20480)')
    parser.add_argument('--jobflavour', default='workday',
        help='HTCondor job flavour, see https://batchdocs.web.cern.ch/local/submit.html'
             ' (default: workday, i.e. up to 8h)')
    args = parser.parse_args()

    thisdir = os.path.dirname(os.path.abspath(__file__))
    runsh = os.path.join(thisdir, 'run.sh')
    if not os.path.exists(runsh):
        raise Exception('run.sh not found at {}'.format(runsh))

    runsh_args = [args.proc, str(args.nevent), str(args.nevent_gen), str(args.jobnum)]
    if args.delphes_cards is not None:
        runsh_args.append(args.delphes_cards)
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

    print('Submitted condor job for proc={} jobnum={} (cards={})'.format(
        args.proc, args.jobnum, args.delphes_cards or '<run.sh default>'))
    print('Job description: {}'.format(os.path.join(outputdir, jobname + '.txt')))
