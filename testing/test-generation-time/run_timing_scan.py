#!/usr/bin/env python3

'''
Timing scan: submit one condor job per (process, NEVENT) pair, each running
the full run.sh chain (gen + Delphes + ntupling), timing the whole run.sh
call with the bash builtin `time`, and appending
"NEVENT=... JOBNUM=... elapsed_sec=... njets=... size_bytes=... rc=..." to
that process's own results file once the job finishes. njets is the number
of entries in the output ntuple's "tree" (one entry per jet, per
makeNtuples.C); size_bytes is that same ntuple file's size on disk - both
measured *after* elapsed_sec has already been captured, so neither inflates
the timing measurement; both are -1 if run.sh failed or the ntuple is
missing. Used to check how per-job runtime (and jet yield, and output size)
scales with the number of events requested, and whether that scaling is
similar across processes - see README.md in this directory for the results
and conclusions.

All jobs (every process x every NEVENT value) are independent and run in
parallel; each writes its own detector output under --output-path (a
directory kept completely separate from routine production output - see
--output-path's help) and its own line to its process's results file
(--results-template) once done, so partial results can be inspected before
every job has finished.

Usage:
  # the single-process scan behind this directory's original README.md findings
  python3 run_timing_scan.py --procs HToBB --nevents 10,20,50,100,200,500,1000,2000,5000,10000

  # the same scan repeated for all 10 jetclass1 processes (100 jobs total) -
  # one results file per process, e.g. timing_results_HToBB.txt, timing_results_HToCC.txt, ...
  python3 run_timing_scan.py --procs HToBB,HToCC,HToGG,HToWW2Q1L,HToWW4Q,TTBar,TTBarLep,WToQQ,ZJetsToNuNu,ZToQQ \\
      --nevents 10,20,50,100,200,500,1000,2000,5000,10000
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
# deliberately NOT output_test (the routine-production output directory) -
# run.sh's optional 6th positional arg points it here instead, so these
# throwaway timing runs never mix into real output (see run.sh's own docstring)
DEFAULT_OUTPUT_PATH = '/eos/user/l/llambrec/jetclass/output_timing_test'
DEFAULT_CONDOR_DIR = os.path.join(THISDIR, 'condor')
# {proc} is substituted with each process's short name, e.g. HToBB - so
# multiple processes never share (or race on appending to) the same file
DEFAULT_RESULTS_TEMPLATE = os.path.join(THISDIR, 'timing_results_{proc}.txt')
# same LCG view run.sh itself sources for the ntuple-making (ROOT) step
LCG_SETUP = '/cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh'
NTUPLE_TREE_NAME = 'tree'  # see makeNtuples.C: one entry per jet


def normalize_proc(proc):
    '''Accept "HToGG", "jetclass1/HToGG", or "jetclass1/HToGG/precompiled" - return (short, full)
    where short="HToGG" (used for filenames/job names) and full="jetclass1/HToGG/precompiled"
    (run.sh's PROC positional arg 1).'''
    parts = [p for p in proc.split('/') if p not in ('jetclass1', 'precompiled', '')]
    if len(parts) != 1:
        raise ValueError('could not parse a single process name out of {!r}'.format(proc))
    short = parts[0]
    return short, 'jetclass1/{}/precompiled'.format(short)


def count_njets_command(ntuple_path):
    '''
    Bash snippet setting $NJETS to the number of entries in `ntuple_path`'s
    NTUPLE_TREE_NAME tree (i.e. jets, not events) - or -1 if $RC (from the
    preceding run.sh call) was nonzero or the file isn't there. Runs in a
    subshell so sourcing LCG_SETUP (needed for the `root` binary) doesn't
    pollute the rest of the job's environment - same reasoning as run.sh's
    own ntuple-making step.
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
    '''
    Bash snippet setting $SIZE_BYTES to `ntuple_path`'s size on disk in
    bytes, or -1 if $RC (from the preceding run.sh call) was nonzero or the
    file isn't there. Just a `stat` - no LCG/ROOT needed, unlike
    count_njets_command().
    '''
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
        help='comma-separated processes to test, e.g. HToBB,HToCC,TTBar'
             ' (bare name, jetclass1/<name>, or jetclass1/<name>/precompiled all accepted)')
    parser.add_argument('--nevents', default=DEFAULT_NEVENTS,
        help='comma-separated NEVENT values to test, one job each, per process')
    parser.add_argument('--card', default=DEFAULT_CARD,
        help='Delphes card name (run.sh positional arg 5)')
    parser.add_argument('--jobnum-base', type=int, default=0,
        help='first JOBNUM to use per process; each subsequent NEVENT value gets'
             ' jobnum_base+i (jobnums only need to be unique within one process\'s own'
             ' output subdirectory, since --output-path/<process>/... already separates'
             ' processes - so every process reuses the same jobnum range by default)')
    parser.add_argument('--output-path', default=DEFAULT_OUTPUT_PATH,
        help='detector-output directory (run.sh positional arg 6) - a dedicated'
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

    # pre-create every process's output subdirectory ONCE, serially, before
    # submitting any jobs - run.sh's own "mkdir -p" (done independently by
    # every job right before it copies its output to EOS) is NOT safe against
    # this: when the shared parent directory doesn't exist yet at all and
    # ~10-100 jobs race to create it for the first time simultaneously, EOS's
    # FUSE client on some worker nodes ends up with a stale/negative cache
    # entry for it that a few in-job retries don't reliably clear, causing
    # that job's copy-to-EOS step to fail for real (verified directly: the
    # directory existed fine server-side and from other clients throughout -
    # see testing/test-generation-time/README.md). Doing it here instead,
    # one directory at a time from a single process before any job starts,
    # means no worker node ever has to create a brand-new shared directory -
    # only ever write into one that's already real and already cached.
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
                    '{} {} {} {} {} {} {}'.format(
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
