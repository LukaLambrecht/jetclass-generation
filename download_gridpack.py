#!/usr/bin/env python3

'''
Pre-populate the persistent gridpack cache (see
gen_configs/populate_gridpack_cache.sh) for one or more jetclass1
"precompiled" processes, without generating any events.

run_gen_precompiled.sh already does this lazily, as a side effect of the
first generation job that needs a given process - this script just does that
same download+extract+patch step ahead of time, for as many processes as
asked, in parallel condor jobs by default (one job per process). Useful to
run once before submitting the actual generation jobs, so:
  - the (network-bound, ~1 min) download only ever happens once per process,
    instead of racing across many simultaneous generation jobs the first
    time each process is used;
  - generation jobs never pay that latency themselves.

This only touches the gridpack cache - it does not generate LHE/HepMC events
and does not touch $OUTPUT_PATH. The cache layout this produces is exactly
the one run_gen_precompiled.sh itself produces and expects (both call the
same gen_configs/populate_gridpack_cache.sh), so its output for a given
process is indistinguishable from that process having simply been run once
already - e.g. for HToBB/HToCC, already populated by earlier generation runs.

Note this really is just a download: the "precompiled" gridpacks are fetched
already-compiled from https://github.com/jet-universe/jetclass_generation
(see populate_gridpack_cache.sh) - nothing is recompiled from the raw
MadGraph process cards here (that only happens for the non-precompiled
"raw" configs, via the normal run.sh/run_gen_default.sh path).

Usage:
  # submit one condor job per process, populating the shared default cache
  python3 download_gridpack.py HToGG HToWW2Q1L HToWW4Q TTBar TTBarLep WToQQ ZJetsToNuNu ZToQQ

  # equivalently, jetclass1/<name> or jetclass1/<name>/precompiled also accepted
  python3 download_gridpack.py jetclass1/HToGG

  # run locally instead of via condor (e.g. for a single quick test)
  python3 download_gridpack.py HToGG --local

  # populate a different cache directory
  python3 download_gridpack.py HToGG -o /path/to/other_gridpack_cache
'''

import os
import sys
import argparse

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jobtools'))
import condortools as ct

THISDIR = os.path.dirname(os.path.abspath(__file__))
GENCFG_PATH = os.path.join(THISDIR, 'gen_configs')
JETCLASS1_DIR = os.path.join(GENCFG_PATH, 'jetclass1')

# same defaults as run.sh, so the cache this populates is the one
# run.sh/run_gen_precompiled.sh actually read from unless overridden
DEFAULT_MG5_PATH = '/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2'
DEFAULT_GRIDPACK_CACHE = '/eos/user/l/llambrec/jetclass/gridpack_cache'


def normalize_proc(proc):
    '''Accept "HToGG", "jetclass1/HToGG", or "jetclass1/HToGG/precompiled" - return bare "HToGG".'''
    parts = [p for p in proc.split('/') if p not in ('jetclass1', 'precompiled', '')]
    if len(parts) != 1:
        raise ValueError('could not parse a single process name out of {!r}'.format(proc))
    return parts[0]


def gridpack_name_for_proc(proc):
    '''
    Read GRIDPACK_NAME out of gen_configs/jetclass1/<proc>/precompiled/run_gen.sh,
    rather than assuming it always equals `proc` (true for every process
    today, but that file is the actual source of truth the generation jobs
    themselves use, so read it rather than duplicate the assumption here).
    '''
    run_gen = os.path.join(JETCLASS1_DIR, proc, 'precompiled', 'run_gen.sh')
    if not os.path.exists(run_gen):
        raise ValueError('no precompiled config found for process {!r} (expected {})'.format(proc, run_gen))
    with open(run_gen) as f:
        for line in f:
            line = line.strip()
            if line.startswith('export GRIDPACK_NAME='):
                return line.split('=', 1)[1].strip()
    raise ValueError('{} does not set GRIDPACK_NAME'.format(run_gen))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Pre-populate the gridpack cache for one or more jetclass1 processes, without generating events.',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('procs', nargs='+',
        help='process names to download the gridpack for, e.g. HToGG HToWW2Q1L TTBar'
             ' (bare name, jetclass1/<name>, or jetclass1/<name>/precompiled all accepted)')
    parser.add_argument('-o', '--output-dir', default=DEFAULT_GRIDPACK_CACHE,
        help='gridpack cache directory to populate (GRIDPACK_CACHE) - should match'
             ' the one run.sh/run_gen_precompiled.sh actually use, so the generation'
             ' jobs find what got downloaded here instead of re-downloading it')
    parser.add_argument('--mg5-path', default=DEFAULT_MG5_PATH,
        help='MG5_PATH used to patch the gridpack\'s hardcoded install path (same role as in run.sh)')
    parser.add_argument('--condor-dir', default='condor',
        help='directory to write condor submission files into (default: condor, same as run_condor.py)')
    parser.add_argument('--local', action='store_true',
        help='run locally, one process after another, instead of submitting condor jobs')
    parser.add_argument('--cpus', type=int, default=1)
    parser.add_argument('--mem', type=int, default=2048, help='requested memory in MB')
    parser.add_argument('--disk', type=int, default=4096, help='requested disk in MB')
    parser.add_argument('--jobflavour', default='espresso',
        help='HTCondor job flavour, see https://batchdocs.web.cern.ch/local/submit.html'
             ' (default: espresso, i.e. up to 20 min - this is just a download+extract'
             ' of an already-precompiled gridpack, not a compile or event generation)')
    args = parser.parse_args()

    procs = [normalize_proc(p) for p in args.procs]
    gridpack_names = {proc: gridpack_name_for_proc(proc) for proc in procs}

    populate_script = os.path.join(GENCFG_PATH, 'populate_gridpack_cache.sh')
    if not os.path.exists(populate_script):
        raise Exception('{} not found'.format(populate_script))

    output_dir = os.path.abspath(args.output_dir)

    if args.local:
        failed = []
        for proc in procs:
            gridpack_name = gridpack_names[proc]
            print('=== Downloading gridpack for {} ({}) locally ==='.format(proc, gridpack_name))
            cmd = 'MG5_PATH={} GRIDPACK_CACHE={} {} {}'.format(
                args.mg5_path, output_dir, populate_script, gridpack_name)
            ret = os.system(cmd)
            if ret != 0:
                failed.append(proc)
        if failed:
            print('FAILED for: {}'.format(', '.join(failed)))
            sys.exit(1)
        print('Done. Gridpack cache directory: {}'.format(output_dir))
        sys.exit(0)

    condor_dir = os.path.abspath(args.condor_dir)
    if not os.path.exists(condor_dir):
        os.makedirs(condor_dir)

    cwd = os.getcwd()
    os.chdir(condor_dir)
    try:
        for proc in procs:
            gridpack_name = gridpack_names[proc]
            jobname = 'download_gridpack_{}'.format(proc)
            # explicit cd, same reasoning as run_condor.py: makes the job
            # work regardless of where download_gridpack.py was invoked from
            commands = [
                'cd {}'.format(THISDIR),
                'echo "###starting###"',
                'MG5_PATH={} GRIDPACK_CACHE={} {} {}'.format(
                    args.mg5_path, output_dir, populate_script, gridpack_name),
                'echo "###done###"',
            ]
            ct.submitCommandsAsCondorJob(
                jobname,
                commands,
                home='auto',
                cpus=args.cpus,
                mem=args.mem,
                disk=args.disk,
                jobflavour=args.jobflavour,
            )
            print('Submitted condor job to download gridpack for {} (gridpack {})'.format(proc, gridpack_name))
    finally:
        os.chdir(cwd)

    print('Submitted {} condor job(s). Gridpack cache directory: {}'.format(len(procs), output_dir))
    print('Job descriptions in: {}'.format(condor_dir))
