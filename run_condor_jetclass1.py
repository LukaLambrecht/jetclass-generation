#!/usr/bin/env python3

'''
run_condor_loop.py, with the 10 jetclass1 processes hardcoded as --procs -
everything else is forwarded to it unchanged (including --output-path,
which is REQUIRED - see run_condor_loop.py's own docstring for what it is
and how it differs from -o/--outputdir). Uses the precompiled variant of
each process (jetclass1/<name>/precompiled), matching the gridpack cache
populated by download_gridpack.py earlier and the ~30s-vs-~30min speedup
documented in gen_configs/run_gen_precompiled.sh - not the from-scratch
"raw" configs.

The only argument this script has of its own is --njobs-per-class (renamed
from run_condor_loop.py's --njobs, to make explicit that it's per each of
the 10 hardcoded jetclass1 processes/"classes") - translated to --njobs
when calling run_condor_loop.py.

Usage:
  # 10 jobs of 5000 events each, for all 10 jetclass1 processes (100 condor jobs total)
  python run_condor_jetclass1.py --njobs-per-class 10 --nevents-per-job 5000 \\
      --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250

  # same, but targeting a jet count per job instead
  python run_condor_jetclass1.py --njobs-per-class 10 --target-njets-per-job 150000 \\
      --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250

See run_condor_loop.py --help for every other available argument (all
forwarded unchanged) - --procs itself is the only one this script doesn't
accept, since it's the one thing hardcoded here.
'''

import os
import sys
import argparse
import subprocess

THISDIR = os.path.dirname(os.path.abspath(__file__))
RUN_CONDOR_LOOP_PY = os.path.join(THISDIR, 'run_condor_loop.py')

JETCLASS1_PROCS = [
    'jetclass1/HToBB/precompiled',
    'jetclass1/HToCC/precompiled',
    'jetclass1/HToGG/precompiled',
    'jetclass1/HToWW2Q1L/precompiled',
    'jetclass1/HToWW4Q/precompiled',
    'jetclass1/TTBar/precompiled',
    'jetclass1/TTBarLep/precompiled',
    'jetclass1/WToQQ/precompiled',
    'jetclass1/ZJetsToNuNu/precompiled',
    'jetclass1/ZToQQ/precompiled',
]

if __name__ == '__main__':

    if any(a == '--procs' or a.startswith('--procs=') for a in sys.argv[1:]):
        raise Exception('--procs is hardcoded by this script (the 10 jetclass1 processes) - '
                         'use run_condor_loop.py directly if you want to choose your own list')

    # -h/--help: forward straight to run_condor_loop.py's own full help
    # listing (this script's own parser is required=True below, so it
    # would otherwise error out on -h instead of showing help)
    if any(a in ('-h', '--help') for a in sys.argv[1:]):
        sys.exit(subprocess.run([sys.executable, RUN_CONDOR_LOOP_PY, '--help']).returncode)

    # only --njobs-per-class is handled here (it needs renaming); everything
    # else is unrecognized by this minimal parser and forwarded as-is
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--njobs-per-class', type=int, required=True,
        help='number of jobs to submit per jetclass1 process/"class" (forwarded to'
             ' run_condor_loop.py as --njobs)')
    args, passthrough = parser.parse_known_args()

    cmd = ([sys.executable, RUN_CONDOR_LOOP_PY, '--procs', ','.join(JETCLASS1_PROCS),
            '--njobs', str(args.njobs_per_class)] + passthrough)
    sys.exit(subprocess.run(cmd).returncode)
