#!/usr/bin/env python3

'''
Run every offline-vs-HLT plotting script in this directory over ONE sample, as
parallel condor jobs (one per script - they are independent, and the slowest is
otherwise the whole wall time).

Inputs follow exactly the same convention as the individual scripts: one or more
file paths/globs (quote globs so they reach the scripts rather than being
expanded by the shell) naming every ntuple of ONE sample, of either schema -
our own paired ntuples (delphes or fullsim backend) or the CMS offline+scouting
reference dataset (see ntuple_io.py; the scripts detect which automatically).
Everything else is left at the scripts' own defaults.

Usage:
  python3 run_all_plots.py FILE_OR_GLOB [FILE_OR_GLOB ...] --outdir DIR [options]

Examples:
  # our own fullsim production
  python3 run_all_plots.py \\
      '/eos/user/l/llambrec/jetclass/output_fullsim_630k_trial/jetclass2/*/fullsim_offline+hlt/ntuple_*.root' \\
      --outdir output_plots_fullsim_trial

  # the CMS reference dataset, both its samples pooled
  python3 run_all_plots.py \\
      '/eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/*/dnnTuples_nanov15_*.root' \\
      --outdir output_plots_fullsim_og

  # run them here instead of submitting (sequential, for a quick/small sample)
  python3 run_all_plots.py 'FILES...' --outdir output_plots_test --local

The jobs all write into the same --outdir, which is created here before any job
starts - never by the jobs themselves, since a shared EOS directory created by
several jobs racing each other is exactly what has bitten this repo before (see
run_condor_loop.py's own comment). Their file names don't collide.
'''

import os
import sys
import glob
import argparse
import subprocess

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(os.path.dirname(THISDIR))
sys.path.append(os.path.join(REPO_DIR, 'jobtools'))
import condortools as ct

# The LCG view the jobs set up before running anything. The plotting scripts need
# uproot/awkward/matplotlib, which interactively come from ~/.local - not a safe
# bet on a worker node (AFS needs a valid token there), whereas /cvmfs does not.
# Verified: LCG_104 carries uproot 4.3.7, awkward 1.10.3, matplotlib 3.7.1, and all
# four scripts run under it. Same view run.sh already uses for the ntuplizing step.
LCG_VIEW = '/cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh'

# One entry per job: (job name, script, extra arguments, requested memory in MB).
# `{outdir}` is substituted with the resolved output directory. The input files are
# inserted after the script name, before these extras.
#
# Memory: the per-particle reads are what cost - plot_nparticles' "types" figures and
# plot_particle_pt read jagged per-particle branches for every jet of the sample at
# once, which on a multi-million-jet sample is several GB; the jet-level ones read
# flat scalars only and need almost nothing.
# The CMS reference dataset's own offline selection. Every script can apply it, and
# each gets a second "_ptmatched" job that does - see ntuple_io.jet_selection_mask()
# for why: a sample that reaches below it (our fullsim ntuples made before 2026-10-05
# start at 120 GeV) is otherwise not comparable to the reference, and the unmatched
# version is still worth having since it uses all the data the sample contains.
# A no-op on a sample already cut there, so producing both is always safe.
PTMATCH_ARGS = ['--min-jet-pt', '200', '--max-jet-eta', '2.4', '--tag', 'ptmatched']

# One entry per script: (job name, script, extra arguments, requested memory in MB).
# `{outdir}` is substituted with the resolved output directory. The input files are
# inserted after the script name, before these extras. Each entry is submitted twice,
# plain and with PTMATCH_ARGS appended (see make_jobs()).
#
# Memory: the per-particle reads are what cost - plot_nparticles' "types" figures and
# plot_particle_pt read jagged per-particle branches for every jet of the sample at
# once, which on a multi-million-jet sample is several GB; the jet-level ones read
# flat scalars only and need almost nothing.
SCRIPTS = [
    ('jet_kinematics', 'plot_jet_kinematics.py', ['--outdir', '{outdir}'], 4096),
    ('particle_pt', 'plot_particle_pt.py', ['--output', '{outdir}/plot_particle_pt.png'], 16384),
    ('composition', 'plot_composition.py', ['--output', '{outdir}/plot_composition.png'], 16384),
    ('nparticles', 'plot_nparticles.py', ['--outdir', '{outdir}'], 16384),
]


def make_jobs():
    '''Every script twice: as-is, and restricted to the reference dataset's own offline
    selection (PTMATCH_ARGS). Returns [(job name, script, extras, memory)].'''
    jobs = []
    for name, script, extras, mem in SCRIPTS:
        jobs.append((name, script, extras, mem))
        jobs.append((name + '_ptmatched', script, extras + PTMATCH_ARGS, mem))
    return jobs


JOBS = make_jobs()


def expand_files(patterns):
    '''Same glob-or-literal handling as the plotting scripts' own expand_files() - used
    here only to fail fast on a pattern that matches nothing at all, since the jobs
    themselves re-expand the ORIGINAL pattern (passed through verbatim, so a job's
    command line stays short and readable rather than listing thousands of paths).'''
    files = []
    for pattern in patterns:
        matched = sorted(glob.glob(pattern))
        files.extend(matched if matched else [pattern])
    return files


def build_command(script, files, extras, outdir):
    '''The one shell command a job runs: the LCG view, then the script with the input
    patterns QUOTED (they contain globs and must reach python, not the job's own shell)
    and the job's own extra arguments.'''
    quoted = ' '.join("'{}'".format(f) for f in files)
    args = ' '.join(a.format(outdir=outdir) for a in extras)
    return 'python3 {} {} {}'.format(os.path.join(THISDIR, script), quoted, args)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('files', nargs='+',
        help='ntuple file(s)/glob(s) of ONE sample - quote globs (same convention as the'
             ' individual plotting scripts)')
    parser.add_argument('--outdir', required=True,
        help='directory every plot is written into (created here, before any job starts)')
    parser.add_argument('--local', action='store_true',
        help='run the scripts here, one after another, instead of submitting condor jobs')
    parser.add_argument('--jobs', default=None,
        help='comma-separated subset of jobs to run (default: all - {})'.format(
            ', '.join(name for name, _, _, _ in JOBS)))
    parser.add_argument('-o', '--condordir', default='condor_plots',
        help='directory for the condor submission files (default: condor_plots) - NOT the'
             ' plot output directory, which is --outdir')
    parser.add_argument('--jobflavour', default='workday',
        help='HTCondor job flavour (default: workday)')
    args = parser.parse_args()

    selected = [j for j in JOBS
                if args.jobs is None or j[0] in [s.strip() for s in args.jobs.split(',')]]
    if not selected:
        raise Exception('--jobs selected nothing - known jobs: {}'.format(
            ', '.join(name for name, _, _, _ in JOBS)))
    for name, script, _, _ in selected:
        if not os.path.exists(os.path.join(THISDIR, script)):
            raise Exception('{}: script {} not found next to this one'.format(name, script))

    if not expand_files(args.files):
        raise Exception('no input files given')

    outdir = os.path.abspath(args.outdir)
    os.makedirs(outdir, exist_ok=True)
    print('Plots will be written to {}'.format(outdir))

    if args.local:
        for name, script, extras, _ in selected:
            cmd = build_command(script, args.files, extras, outdir)
            print('\n=== {} ===\n{}'.format(name, cmd))
            rc = subprocess.run(['bash', '-c', 'source {} >/dev/null 2>&1; {}'.format(LCG_VIEW, cmd)]).returncode
            if rc != 0:
                print('WARNING: {} exited with status {}'.format(name, rc))
        sys.exit(0)

    condordir = os.path.abspath(args.condordir)
    os.makedirs(condordir, exist_ok=True)
    cwd = os.getcwd()
    os.chdir(condordir)   # jobtools writes its .sh/.txt relative to the cwd it submits from
    try:
        for name, script, extras, mem in selected:
            cmd = build_command(script, args.files, extras, outdir)
            print('=== submitting {} ==='.format(name))
            ct.submitCommandsAsCondorJob(
                'plots_{}'.format(name),
                ['cd {}'.format(THISDIR),
                 'source {}'.format(LCG_VIEW),
                 'echo "###starting###"',
                 cmd,
                 'echo "###done###"'],
                home='auto', cpus=1, mem=mem, disk=10240, jobflavour=args.jobflavour)
    finally:
        os.chdir(cwd)
    print('\nSubmitted {} job(s); submission files in {}'.format(len(selected), condordir))
    print('Plots will appear in {}'.format(outdir))
