# Running crab subcommands
#
# Wrapper around crab commands with environment setup,
# shared by the monitoring, the log mirroring and the kill step.
#
# The environment is set up per invocation, that is a few seconds of
# cvmfs work, which is small next to the crab server round-trip each call makes
# anyway, and it keeps this module free of any assumption about the caller's shell.

import os
import subprocess

# The shell driver that sets up the environment, found relative to this file so there
# is nothing to configure.
DRIVER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crab_env.sh')

DEFAULT_TIMEOUT = 900


def argv(args, proxy=None):
    """The command line for a crab subcommand, e.g. argv(['status', '/path/to/task'])."""
    cmd = ['bash', DRIVER] + [str(a) for a in args]
    if proxy:
        cmd.append('--proxy={}'.format(proxy))
    return cmd


def run(args, proxy=None, timeout=DEFAULT_TIMEOUT, cwd=None):
    """Run a crab subcommand and capture its output.

    Returns (returncode, combined stdout+stderr). Never raises: a timeout or a failure
    to start comes back as a non-zero code with the reason in the output, because
    every caller is looping over tasks and must be able to carry on to the next one.
    """
    cmd = argv(args, proxy=proxy)
    try:
        p = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=timeout)
        return p.returncode, p.stdout.decode('utf-8', 'replace')
    except subprocess.TimeoutExpired:
        return 124, 'TIMEOUT after {}s: {}'.format(timeout, ' '.join(cmd))
    except Exception as e:                                   # noqa: BLE001
        return 1, 'EXCEPTION running {}: {}'.format(' '.join(cmd), e)


def call(args, proxy=None, cwd=None):
    """Run a crab subcommand, letting its output go straight to the terminal.

    For interactive use (e.g. crab task killing).
    Returns the exit code.
    """
    try:
        return subprocess.call(argv(args, proxy=proxy), cwd=cwd)
    except Exception as e:                                   # noqa: BLE001
        print('could not run crab: {}'.format(e))
        return 1
