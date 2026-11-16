#!/usr/bin/env python3

'''
run_condor_loop.py with the 10 jetclass1 processes hardcoded as --procs;
everything else is forwarded to it unchanged, --output-path included.

Uses the precompiled variant of each process, which reads the gridpack cache
populated by download_gridpack.py and is far faster than building from scratch
(see gen_configs/run_gen_precompiled.sh), rather than the "raw" configs.

The only argument of its own is --njobs-per-class, which is run_condor_loop.py's
--njobs renamed to make clear that it applies per jetclass1 process, and is
translated back to --njobs on the way out.

Usage:
  # 10 jobs of 5000 events each, for all 10 jetclass1 processes (100 condor jobs total)
  python run_condor_jetclass1.py --backend delphes --njobs-per-class 10 --nevents-per-job 5000 \\
      --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250

  # same, but targeting a jet count per job instead
  python run_condor_jetclass1.py --backend delphes --njobs-per-class 10 --target-njets-per-job 150000 \\
      --output-path /eos/user/l/llambrec/jetclass/output_test --batch-size 250

--backend is required by run_condor_loop.py and simply forwarded, like every
other argument this script does not handle itself.

See run_condor_loop.py --help for every other argument. --procs is the only one
not accepted here, since it is the one thing this script fixes.
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

    # Forward -h straight to run_condor_loop.py's full help: the parser below
    # has a required argument, so it would error out on -h instead.
    if any(a in ('-h', '--help') for a in sys.argv[1:]):
        sys.exit(subprocess.run([sys.executable, RUN_CONDOR_LOOP_PY, '--help']).returncode)

    # Only --njobs-per-class is handled here, since it needs renaming; this
    # minimal parser does not recognise the rest, which is forwarded as-is.
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--njobs-per-class', type=int, required=True,
        help='number of jobs to submit per jetclass1 process/"class" (forwarded to'
             ' run_condor_loop.py as --njobs)')
    args, passthrough = parser.parse_known_args()

    cmd = ([sys.executable, RUN_CONDOR_LOOP_PY, '--procs', ','.join(JETCLASS1_PROCS),
            '--njobs', str(args.njobs_per_class)] + passthrough)
    sys.exit(subprocess.run(cmd).returncode)
