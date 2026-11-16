#!/usr/bin/env python3

'''Timing scan: submit one condor job per (process, NEVENT) pair, each running the full
run.sh chain and timing it.

Each job appends a line of NEVENT, JOBNUM, elapsed_sec, njets, size_bytes and rc to its
process' own results file. njets is the number of entries in the output ntuple, one per
jet, and size_bytes is that file's size on disk. Both are measured after the elapsed
time has been captured, so neither inflates it, and both are -1 if run.sh failed or the
ntuple is missing.

Used to check how per-job runtime, jet yield and output size scale with the number of
events requested, and whether that scaling is similar across processes.
'''

import os
import sys
import argparse

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(os.path.dirname(THISDIR))
sys.path.append(os.path.join(REPO_DIR, 'jobtools'))
import condortools as ct

DEFAULT_NEVENTS = '10,20,50,100,200,500,1000,2000,5000,10000'
DEFAULT_PROCS = 'HToBB'
DEFAULT_CARD = 'onlyFatJetNoPU'
# Deliberately not the routine-production output directory: run.sh's optional output
# argument points here instead, so these throwaway timing runs never mix into real
# output.
DEFAULT_OUTPUT_PATH = '/eos/user/l/llambrec/jetclass/output_timing_test'
DEFAULT_CONDOR_DIR = os.path.join(THISDIR, 'condor')
# {proc} is substituted with each process's short name, e.g. HToBB - so
# multiple processes never share (or race on appending to) the same file
DEFAULT_RESULTS_TEMPLATE = os.path.join(THISDIR, 'timing_results_{proc}.txt')
# same LCG view run.sh itself sources for the ntuple-making (ROOT) step
LCG_SETUP = '/cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh'
NTUPLE_TREE_NAME = 'tree'  # see makeNtuples.C: one entry per jet


def normalize_proc(proc):
    '''The bare process name, e.g. HToBB, from a full process path.'''
    parts = [p for p in proc.split('/') if p and p != 'precompiled']
    if parts and parts[0] in ('jetclass1', 'jetclass2'):
        family, rest = parts[0], parts[1:]
    else:
        rest = parts
        family = 'jetclass2' if rest and rest[0].startswith('train_') else 'jetclass1'
    if len(rest) != 1:
        raise ValueError('could not parse a single process name out of {!r}'.format(proc))
    short = rest[0]
    full = 'jetclass1/{}/precompiled'.format(short) if family == 'jetclass1' else 'jetclass2/{}'.format(short)
    return short, full


def count_njets_command(ntuple_path):
    '''The shell command that counts the output ntuple's entries into the results line.
    '''
    root_expr = ('std::cout << ((TTree*)TFile::Open("{path}")->Get("{tree}"))->GetEntries()'
                 ' << std::endl;').format(path=ntuple_path, tree=NTUPLE_TREE_NAME)
    return (
        'if [ "$RC" -eq 0 ] && [ -f "{path}" ]; then '
        'NJETS=$(source {lcg} 2>/dev/null; root -b -q -l -e \'{expr}\' 2>/dev/null | tail -1); '
        ': "${{NJETS:=-1}}"; '
        'else NJETS=-1; fi'
    ).format(path=ntuple_path, lcg=LCG_SETUP, expr=root_expr)


def file_size_command(ntuple_path):
    '''The shell command that records the output ntuple's size into the results line.'''
    return (
        'if [ "$RC" -eq 0 ] && [ -f "{path}" ]; then '
        'SIZE_BYTES=$(stat -c%s "{path}" 2>/dev/null); '
        ': "${{SIZE_BYTES:=-1}}"; '
        'else SIZE_BYTES=-1; fi'
    ).format(path=ntuple_path)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Submit one condor job per (process, NEVENT) pair, timing the full run.sh chain for each.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--procs', default=DEFAULT_PROCS,
        help='comma-separated processes to test, e.g. HToBB,HToCC,TTBar or train_qcd,train_higgs2p'
             ' - jetclass1 (bare name, jetclass1/<name>, or jetclass1/<name>/precompiled) and'
             ' jetclass2 (bare train_* name, or jetclass2/<name>) both accepted, see normalize_proc()')
    parser.add_argument('--nevents', default=DEFAULT_NEVENTS,
        help='comma-separated NEVENT values to test, one job each, per process')
    parser.add_argument('--card', default=DEFAULT_CARD,
        help='Delphes card name (run.sh positional arg 6, BACKEND_OPTS)')
    parser.add_argument('--jobnum-base', type=int, default=0,
        help='first JOBNUM to use per process; each subsequent NEVENT value gets'
             ' jobnum_base+i (jobnums only need to be unique within one process\'s own'
             ' output subdirectory, since --output-path/<process>/... already separates'
             ' processes - so every process reuses the same jobnum range by default)')
    parser.add_argument('--output-path', default=DEFAULT_OUTPUT_PATH,
        help='detector-output directory (run.sh positional arg 7) - a dedicated'
             ' directory for these throwaway timing runs, separate from routine'
             ' production output')
    parser.add_argument('--condor-dir', default=DEFAULT_CONDOR_DIR,
        help='directory to write condor submission files into (shared across processes -'
             ' job/log names are disambiguated by process+NEVENT, see --results-template)')
    parser.add_argument('--results-template', default=DEFAULT_RESULTS_TEMPLATE,
        help='file each job appends its "NEVENT=... elapsed_sec=..." line to;'
             ' "{proc}" is substituted with each process\'s short name')
    parser.add_argument('--mem', type=int, default=2048, help='requested memory in MB')
    parser.add_argument('--disk', type=int, default=20480, help='requested disk in MB')
    parser.add_argument('--jobflavour', default='workday',
        help='HTCondor job flavour, see https://batchdocs.web.cern.ch/local/submit.html')
    args = parser.parse_args()

    procs = [normalize_proc(p) for p in args.procs.split(',')]
    nevents = [int(x) for x in args.nevents.split(',')]
    runsh = os.path.join(REPO_DIR, 'run.sh')
    if not os.path.exists(runsh):
        raise Exception('run.sh not found at {}'.format(runsh))

    os.makedirs(args.condor_dir, exist_ok=True)

    # Create every process' output subdirectory here, serially, before any job starts.
    # run.sh's own "mkdir -p" is not enough: when many jobs race to create the same
    # brand-new shared directory, the EOS client on some worker nodes keeps a negative
    # cache entry that the in-job retries do not clear, and that job's copy to EOS then
    # fails for real. Creating them up front means no worker ever has to create a new
    # shared directory, only write into one that already exists.
    print('Pre-creating output directories...')
    for short, full in procs:
        d = os.path.join(args.output_path, full, args.card)
        os.makedirs(d, exist_ok=True)
        print('  {}'.format(d))

    n_submitted = 0
    cwd = os.getcwd()
    os.chdir(args.condor_dir)
    try:
        for short, full in procs:
            results_file = args.results_template.format(proc=short)
            results_dir = os.path.dirname(os.path.abspath(results_file))
            if results_dir:
                os.makedirs(results_dir, exist_ok=True)

            for i, n in enumerate(nevents):
                jobnum = args.jobnum_base + i
                # unique per (process, NEVENT) so job/log/description filenames never
                # collide across processes sharing --condor-dir
                jobname = 'timing_{}_{}'.format(short, n)
                ntuple_path = '{}/{}/{}/ntuple_{}.root'.format(args.output_path, full, args.card, jobnum)
                commands = [
                    'cd {}'.format(REPO_DIR),
                    'echo "###starting###"',
                    'START=$(date +%s)',
                    # run.sh's first argument is the detector backend; this scan
                    # times the Delphes chain, so it is pinned to "delphes" here
                    '{} delphes {} {} {} {} {} {}'.format(
                        runsh, full, n, n, jobnum, args.card, args.output_path),
                    'RC=$?',
                    'END=$(date +%s)',  # captured before njets/size measurement - doesn't inflate elapsed_sec
                    count_njets_command(ntuple_path),
                    file_size_command(ntuple_path),
                    'echo "NEVENT={} JOBNUM={} elapsed_sec=$((END-START)) njets=$NJETS size_bytes=$SIZE_BYTES rc=$RC" >> {}'.format(
                        n, jobnum, results_file),
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
                print('Submitted timing job for proc={} NEVENT={} (jobnum={})'.format(short, n, jobnum))
                n_submitted += 1
    finally:
        os.chdir(cwd)

    print('Submitted {} job(s) total ({} process(es) x {} NEVENT value(s)).'.format(
        n_submitted, len(procs), len(nevents)))
    print('Results will be written to: {}'.format(
        ', '.join(args.results_template.format(proc=short) for short, _ in procs)))
