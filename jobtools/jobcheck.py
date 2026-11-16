#!/usr/bin/env python3

################################################
# Check the error and output log files of jobs #
################################################
# Scans the _err_ files written by the job scheduler and reports how many look
# like failures. Two independent checks are made:
#   - the file contains one of a list of known error strings;
#   - the 'starting' and 'done' tags are both present and balanced, which
#     requires the job's executable to write those tags to stderr.
# Usage:
#   Run 'python jobcheck.py -h' for the options. Either pass the job directory
#   with --dir, or run it from inside that directory.
# Note:
#   Works for both condor and qsub log files.


import sys
import os
import argparse
import glob


def check_start_done( filename,
                      starting_tag='###starting###',
                      done_tag='###done###',
                      ntarget=None,
                      verbose=True ):

    # read the file content
    """Check the starting and done tags in one log file.

    Returns 0 if the file looks healthy, meaning at least one starting tag is present and
    the number of done tags equals both the number of starting tags and ntarget, if given.
    Returns 1 otherwise.
    """
    f = open(filename)
    filetext = f.read()
    f.close()

    # count number of starting tags
    nstarted = filetext.count(starting_tag)
    if(nstarted==0):
        if verbose:
            msg = 'WARNING in jobCheck.py: file {}'.format(filename)
            msg += ' does not contain a valid starting tag "{}"'.format(starting_tag)
            print(msg)
        return 1

    # count number of done tags
    ndone = filetext.count(done_tag)
    if ntarget is None: ntarget = ndone

    # return 0 if all is ok
    if(nstarted==ndone and ndone==ntarget): return 0

    # return 1 otherwise
    if verbose:
        msg = 'WARNING in jobCheck.py: found issue in file {}:\n'.format(filename)
        msg += '   {} commands were initiated.\n'.format(nstarted)
        msg += '   {} seem to have finished normally.\n'.format(ndone)
        msg += '   {} were expected.\n'.format(ntarget)
        print(msg)
    return 1


def check_error_content(filename, contentlist='default', verbose=True):

    # read the file content
    """Check one log file for known error messages.

    Returns 0 if none of the strings in contentlist occurs in the file, 1 otherwise.
    """
    f = open(filename)
    filetext = f.read()
    f.close()

    # hard-coded default error content
    if( isinstance(contentlist,str) and contentlist=='default' ):
        contentlist = ([    'SysError',
                           '/var/torque/mom_priv/jobs',
                           'R__unzip: error',
                           'hadd exiting due to error in',
                           'Bus error',
                           'Exception:',
                           'Traceback (most recent call last):' ])
        contentlist.append('###error###') # custom error tag for targeted flagging

    # check if the file content contains provided error tags
    contains = []
    for idx,content in enumerate(contentlist):
        if filetext.count(content)>0:
            contains.append(idx)
    if len(contains)==0: return 0
    if verbose:
        msg = 'WARNING in jobCheck.py: found issue in file {}:\n'.format(filename)
        for idx in contains:
            msg += '   found sequence {}\n'.format(contentlist[idx])
        print(msg)
    return 1


if __name__=='__main__':

    # parse command line arguments
    parser = argparse.ArgumentParser(description='Check job logs for errors.')
    parser.add_argument('--dir', default=os.getcwd(),
                        help='Directory to scan for files (default: cwd)')
    parser.add_argument('--starting_tag', default='###starting###',
                        help='Starting tag, default is "###starting###".')
    parser.add_argument('--done_tag', default='###done###',
                        help='Done tag, default is "###done###".')
    parser.add_argument('--ntags', default=None,
                         help='Number of expected starting and done tags per job.')
    parser.add_argument('--notags', action='store_true',
                        help='Ignore starting and done tags, only check for errors.')
    parser.add_argument('--noerrors', action='store_true',
                        help='Ignore errors, only check starting and done tags.')
    args = parser.parse_args()

    # print arguments
    print('running with following configuration:')
    for arg in vars(args):
        print('  - {}: {}'.format(arg,getattr(args,arg)))

    # some more parsing
    if args.ntags is not None: args.ntags = int(args.ntags)

    # find files, for either scheduler's naming convention
    print('finding files...')
    condorpattern = os.path.join(args.dir,'*_err_*')
    qsubpattern = os.path.join(args.dir,'*.sh.e*')
    files = glob.glob(condorpattern) + glob.glob(qsubpattern)
    nfiles = len(files)
    print('found {} error log files.'.format(nfiles))
    print('start scanning...')

    # loop over files
    nerror = 0
    for fname in files:
        # initialize
        error_start_done = 0
        error_content = 0
        # error checking
        if not args.notags:
            error_start_done = check_start_done(fname,
                starting_tag = args.starting_tag,
                done_tag = args.done_tag,
                ntarget = args.ntags)
        if not args.noerrors:
            error_content = check_error_content(fname)
        if(error_start_done + error_content > 0): nerror += 1

    # print results
    print('number of files scanned: {}'.format(nfiles))
    print('number of files with error: {}'.format(nerror))
    print('number of files without apparent error: {}'.format(nfiles-nerror))
