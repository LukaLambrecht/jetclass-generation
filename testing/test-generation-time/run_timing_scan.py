#!/usr/bin/env python3

'''
Timing scan: submit one condor job per NEVENT value, each running the full
run.sh chain (gen + Delphes + ntupling) for a given process, timing the
whole run.sh call with the bash builtin `time`, and appending
"NEVENT=... JOBNUM=... elapsed_sec=... rc=..." to a shared results file
once each job finishes. Used to check how per-job runtime scales with the
number of events requested - see README.md in this directory for the
results and conclusions of the scan this script was built for.

Jobs are independent and run in parallel (one per NEVENT value); each writes
its own detector output under --output-path (a directory kept completely
separate from routine production output - see --output-path's help) and its
own line to --results-file once done, so partial results can be inspected
before every job has finished.

Usage:
  # the exact scan behind this directory's README.md findings
  python3 run_timing_scan.py --nevents 10,20,50,100,200,500,1000,2000,5000,10000

  # a quicker/smaller scan
  python3 run_timing_scan.py --nevents 10,100,1000 --proc jetclass1/HToCC/precompiled
'''

import os
import sys
import argparse

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(os.path.dirname(THISDIR))
sys.path.append(os.path.join(REPO_DIR, 'jobtools'))
import condortools as ct

DEFAULT_NEVENTS = '10,20,50,100,200,500,1000,2000,5000,10000'
DEFAULT_PROC = 'jetclass1/HToBB/precompiled'
DEFAULT_CARD = 'onlyFatJetNoPU'
# deliberately NOT output_test (the routine-production output directory) -
# run.sh's optional 6th positional arg points it here instead, so these
# throwaway timing runs never mix into real output (see run.sh's own docstring)
DEFAULT_OUTPUT_PATH = '/eos/user/l/llambrec/jetclass/output_timing_test'
DEFAULT_CONDOR_DIR = os.path.join(THISDIR, 'condor')
DEFAULT_RESULTS_FILE = os.path.join(THISDIR, 'timing_results.txt')

if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Submit one condor job per NEVENT value, timing the full run.sh chain for each.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--nevents', default=DEFAULT_NEVENTS,
        help='comma-separated NEVENT values to test, one job each')
    parser.add_argument('--proc', default=DEFAULT_PROC,
        help='process to run (run.sh positional arg 1)')
    parser.add_argument('--card', default=DEFAULT_CARD,
        help='Delphes card name (run.sh positional arg 5)')
    parser.add_argument('--jobnum-base', type=int, default=0,
        help='first JOBNUM to use; each subsequent NEVENT value gets jobnum_base+i,'
             ' so distinct runs of this script can be pointed at the same --output-path'
             ' without colliding - pass a base past whatever jobnums already exist there')
    parser.add_argument('--output-path', default=DEFAULT_OUTPUT_PATH,
        help='detector-output directory (run.sh positional arg 6) - a dedicated'
             ' directory for these throwaway timing runs, separate from routine'
             ' production output')
    parser.add_argument('--condor-dir', default=DEFAULT_CONDOR_DIR,
        help='directory to write condor submission files into')
    parser.add_argument('--results-file', default=DEFAULT_RESULTS_FILE,
        help='file each job appends its "NEVENT=... elapsed_sec=..." line to')
    parser.add_argument('--mem', type=int, default=2048, help='requested memory in MB')
    parser.add_argument('--disk', type=int, default=20480, help='requested disk in MB')
    parser.add_argument('--jobflavour', default='workday',
        help='HTCondor job flavour, see https://batchdocs.web.cern.ch/local/submit.html')
    args = parser.parse_args()

    nevents = [int(x) for x in args.nevents.split(',')]
    runsh = os.path.join(REPO_DIR, 'run.sh')
    if not os.path.exists(runsh):
        raise Exception('run.sh not found at {}'.format(runsh))

    os.makedirs(args.condor_dir, exist_ok=True)
    results_dir = os.path.dirname(os.path.abspath(args.results_file))
    if results_dir:
        os.makedirs(results_dir, exist_ok=True)

    cwd = os.getcwd()
    os.chdir(args.condor_dir)
    try:
        for i, n in enumerate(nevents):
            jobnum = args.jobnum_base + i
            jobname = 'timing_{}'.format(n)
            commands = [
                'cd {}'.format(REPO_DIR),
                'echo "###starting###"',
                'START=$(date +%s)',
                '{} {} {} {} {} {} {}'.format(
                    runsh, args.proc, n, n, jobnum, args.card, args.output_path),
                'RC=$?',
                'END=$(date +%s)',
                'echo "NEVENT={} JOBNUM={} elapsed_sec=$((END-START)) rc=$RC" >> {}'.format(
                    n, jobnum, args.results_file),
                'echo "###done###"',
            ]
            ct.submitCommandsAsCondorJob(
                jobname,
                commands,
                home='auto',
                cpus=1,
                mem=args.mem,
                disk=args.disk,
                jobflavour=args.jobflavour,
            )
            print('Submitted timing job for NEVENT={} (jobnum={})'.format(n, jobnum))
    finally:
        os.chdir(cwd)

    print('Results will be appended to: {}'.format(args.results_file))
