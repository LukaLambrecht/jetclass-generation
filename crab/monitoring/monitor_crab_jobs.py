#!/bin/env python3

##############################################################
# Monitor crab jobs and put the results in a summary webpage #
##############################################################

# external imports
import os
import sys
import json
import argparse

# local imports
from tools import crab_kill
from tools import crabcmd
from tools import inputs
from tools import mirror_job_logs
from tools import webstyle

# Where the pages go when -d/--webdir is not given: a directory next to
# this script, so a bare run still produces something viewable.
DEFAULT_WEBDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crab_jobs_monitor')


def collect_tasks(args, parser):
    """The CRAB tasks the command line selects.

    Selection itself lives in tools/inputs.py, shared with the kill and log-mirroring.
    May return an empty list; callers decide whether that is an error (it is for monitoring, which would
    otherwise publish an empty page) or merely nothing to do (killing).
    """
    try:
        return inputs.collect(args.searchdir, args.requestdir)
    except ValueError as e:
        parser.error(str(e))
        return []


def looks_irretrievable(status):
    """True if this task's status is the untouched initial value.

    The main loop seeds every task with {'finished': '0%'} and overwrites it with real
    numbers. A task still carrying exactly that after a successful 'crab status' is one
    whose status could not be retrieved - typically a submission old enough that the
    schedd no longer knows it - and reporting it as "0% finished" would be wrong.
    """
    if not isinstance(status, dict) or len(status) != 1:
        return False
    if 'finished' not in status:
        return False
    return webstyle.parse_pct(status['finished']) == 0


def sample_row(sample, info):
    """One table row: task identity in the first cell, progress in the second."""
    
    # get specific information
    info = info or {}
    request = info.get('request') or sample
    crabtask = info.get('task') or ''
    status = info.get('status') or {}
    grafana = info.get('grafana') or ''

    # format the row
    row = '<tr>\n<td>'
    row += '<div class="name">{}</div>'.format(webstyle.esc(request))
    if crabtask:
        row += '<div class="muted">task: {}</div>'.format(webstyle.esc(crabtask))
    if grafana:
        row += ('<div class="muted"><a href="{}" target="_blank" rel="noopener">'
                'Grafana &#8599;</a></div>').format(webstyle.esc(grafana))
    row += webstyle.row_details([
        ('CRAB working directory', info.get('path')),
        ('Output directory', info.get('outputdir')),
    ])
    row += '</td>\n<td>'
    if looks_irretrievable(status):
        row += '<span class="pill">status unavailable</span>'
    else:
        row += webstyle.progress_bar(status)
    row += '</td>\n</tr>\n'
    return row


def web(data, webpath, force=False):
    """Render the task status page.

    - data:    {'samples': {name: {'status': {state: pct}, 'grafana': url}}, 'meta': {}}
    - webpath: directory to write index.html into; created if absent.
    - force:   write the page even if every task's status looks irretrievable.

    Robustness:
      * one malformed task cannot take down the page - its row carries the error;
      * the page is only replaced if it could be built in full, and replaced
        atomically, so a reader never sees a half-written page;
      * if NO task has a usable status, the existing page is kept rather than
        overwritten with a wall of zeroes.
    Returns True if the page was written.
    """
    samples = (data or {}).get('samples')
    if samples is None:
        samples = {}
        body = webstyle.warn("No 'samples' key in the monitoring data - "
                             "nothing to report.")
    else:
        body = ''

    names = sorted(samples.keys(), key=lambda x: x.lower())
    usable = [n for n in names
              if not looks_irretrievable((samples[n] or {}).get('status'))]
    if names and not usable and not force:
        print('ERROR: no task has a retrievable status (too long since submission?);'
              ' keeping the existing page rather than overwriting it with zeroes.'
              ' Pass force=True to write it anyway.')
        return False

    nfailed = 0
    for n in names:
        status = (samples[n] or {}).get('status') or {}
        for state in webstyle.BAD_STATES:
            if webstyle.parse_pct(status.get(state)):
                nfailed += 1
                break

    subtitle = 'Last update: {}'.format(webstyle.timestamp())
    page = webstyle.page_head('Status of CRAB jobs', subtitle)
    page += body

    page += '<p class="muted">{} task(s) monitored{}.</p>\n'.format(
        len(names), ', {} with failures'.format(nfailed) if nfailed else '')

    if names:
        page += webstyle.expand_all_button()
        page += '<table>\n<tr><th>Task</th><th>Progress</th></tr>\n'
        for n in names:
            try:
                page += sample_row(n, samples[n])
            except Exception as e:                           # noqa: BLE001
                # A single unexpected shape must not cost the whole page.
                print('WARNING: could not render row for {}: {}'.format(n, e))
                page += ('<tr><td><div class="name">{}</div></td>'
                         '<td><span class="pill bad">render error</span></td></tr>\n'
                         ).format(webstyle.esc(n))
        page += '</table>\n'
    else:
        page += '<p class="muted">No tasks found.</p>\n'

    meta = (data or {}).get('meta') or {}
    if meta:
        page += '<details>\n<summary>Meta-info</summary>\n<table>\n'
        for key, val in meta.items():
            page += '<tr><td class="nowrap">{}</td><td><code>{}</code></td></tr>\n'.format(
                webstyle.esc(key), webstyle.esc(val))
        page += '</table>\n</details>\n'

    # Link to the per-job failure pages written by mirror_job_logs.py.
    page += webstyle.page_foot([('failures.html', 'Job failures and logs \u2192')])

    webstyle.write_atomic(os.path.join(webpath, 'index.html'), page)
    return True


if __name__ == '__main__':

    # read command line arguments
    parser = argparse.ArgumentParser(
      prog='monitor_crab_jobs.py',
      description='Monitor, resubmit or kill CRAB tasks and publish a status page.',
      formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # --- main arguments ---------------------------------------------------------
    parser.add_argument('-i', '--searchdir', default=[], nargs='+', metavar='DIR',
      help='Directory/ies scanned recursively, at any depth, for CRAB project'
          +' directories (identified by the .requestcache file crab writes)')
    parser.add_argument('-t', '--requestdir', default=[], nargs='+', metavar='DIR',
      help='CRAB project directory/ies (crab_<requestName>) named individually.'
          +' Use this to act on a subset, or on tasks spread over several trees.')
    parser.add_argument('-p', '--proxy', default=None, type=os.path.abspath,
      help='Path to your proxy; without it, the ambient X509_USER_PROXY is used')
    parser.add_argument('-d', '--webdir', default=DEFAULT_WEBDIR,
      help='Directory to write the pages into (e.g. a web area or CERNBox path).'
          +' The status page is index.html in there, with the failure pages and'
          +' mirrored logs beside it.')

    # --- resubmitting ----------------------------------------------------------
    resubmitgroup = parser.add_argument_group('resubmitting failed jobs')
    resubmitgroup.add_argument('-r', '--resubmit', default=False, action='store_true',
      help='Resubmit failed jobs as the monitoring goes over them')
    resubmitgroup.add_argument('--resubmit_args', default=None,
      help='Command line args passed on to the crab resubmit command.'
          +' Enclose in single quotes AND use "=", not a space, e.g.'
          +' --resubmit_args=\'--siteblacklist=T2_BE_IIHE --maxmemory 3000\'.'
          +' argparse refuses a value starting with "-" given after a space.'
          +' See https://twiki.cern.ch/twiki/bin/view/CMSPublic/CRAB3Commands#crab_resubmit.')

    # --- killing ---------------------------------------------------------------
    killgroup = parser.add_argument_group('killing tasks')
    killgroup.add_argument('-k', '--kill', default=False, action='store_true',
      help='Kill the selected CRAB tasks instead of monitoring them.'
          +' Lists them and asks for confirmation first.')
    killgroup.add_argument('--kill-yes', default=False, action='store_true',
      help='Skip the --kill confirmation prompt (required when not on a terminal)')
    killgroup.add_argument('--kill-dry-run', default=False, action='store_true',
      help='With --kill: list the tasks that would be killed and stop')

    # --- mirroring job failure logs --------------------------------------------
    mirrorgroup = parser.add_argument_group('mirroring job failure logs')
    mirrorgroup.add_argument('--no-mirror-logs', default=False, action='store_true',
      help='Do not mirror per-job failure logs into the web area')
    mirrorgroup.add_argument('--mirror-max-per-group', type=int,
      default=mirror_job_logs.DEFAULT_MAX_PER_GROUP,
      help='Representative logs to mirror per failure mode')
    mirrorgroup.add_argument('--mirror-max-per-task', type=int,
      default=mirror_job_logs.DEFAULT_MAX_PER_TASK,
      help='Cap on logs fetched per task per run')
    mirrorgroup.add_argument('--mirror-keep-days', type=int,
      default=mirror_job_logs.DEFAULT_KEEP_DAYS,
      help='Prune mirrored logs of unmonitored tasks after this many days')
    mirrorgroup.add_argument('--mirror-no-scrub', default=False, action='store_true',
      help='Do NOT redact certificate DNs and e-mail addresses from mirrored logs.'
          +' Only safe if the web area is access-controlled.')

    args = parser.parse_args()
    print('Running monitor_crab_jobs.py with following configuration:')
    for arg in vars(args): print('  - {}: {}'.format(arg, getattr(args,arg)))

    # check command line arguments
    if not args.searchdir and not args.requestdir:
        parser.error('give -i/--searchdir and/or -t/--requestdir')
    if args.proxy is not None:
        if not os.path.exists(args.proxy):
            raise Exception('ERROR: provided proxy {} does not exist'.format(args.proxy))

    # print check of proxy to screen
    # (can help in debugging)
    print('Found following proxy info:')
    os.system('voms-proxy-info')

    # check proxy
    tmpfile = 'monitor_tmp_proxy.txt'
    os.system('voms-proxy-info >> {} 2>&1'.format(tmpfile))
    with open(tmpfile, 'r') as f:
        lines = f.readlines()
    os.system('rm {}'.format(tmpfile))
    msg = ''
    for line in lines:
        if 'Proxy not found' in line:
            msg = 'No proxy found, please create a new one.'
        if line.startswith('timeleft'):
            line = line.strip(' \t\n')
            if line.endswith('00:00:00'):
                msg = 'Proxy expired, please create a new one.'
    if len(msg) > 0: raise Exception(msg)

    # in case task killing is requested:
    # do it first and exit (no monitoring needed).
    if args.kill:
        crab_kill.kill_tasks(collect_tasks(args, parser), proxy=args.proxy,
                             confirm=not args.kill_yes,
                             dry_run=args.kill_dry_run)
        sys.exit(0)

    # initializations
    data = {'meta': {'generating script': os.path.abspath(__file__),
            'command-line arguments': str(args)},
            'samples': {}}
    wdir = os.getcwd()

    # work out which tasks to act on (tools/inputs.py handles both ways of
    # naming them, the union, and colliding identities)
    tasks = collect_tasks(args, parser)
    if not tasks:
        # Loud rather than publishing an empty page: an empty selection from acron
        # almost always means a moved/renamed directory, not "nothing to do".
        raise Exception('ERROR: no CRAB tasks found for the given directories;'
                        ' check -i/--searchdir and -t/--requestdir.')
    print('Found {} CRAB task(s) to monitor:'.format(len(tasks)))
    for task in tasks: print('  - {} ({})'.format(task.key, task.path))

    # initialize every task to 0% finished and no grafana link, so a task whose
    # status cannot be read still appears on the page
    for task in tasks:
        data['samples'][task.key] = {'status': {'finished': '0%'}, 'grafana': '',
                                     'request': task.request,
                                     # the real CRAB task name, filled in from
                                     # crab status below; '' until then
                                     'task': '',
                                     'path': task.path,
                                     'outputdir': task.output_dir}

    # loop over tasks
    for idx, task in enumerate(tasks):
        print('Now processing task {} of {}'.format(idx + 1, len(tasks)))
        print('({})'.format(task.path))
        entry = data['samples'][task.key]

        # Ask crab for this task's status, retrying a few times.
        outlines = []
        success = False
        for attempt in range(5):
            rc, out = crabcmd.run(['status', task.path], proxy=args.proxy)
            outlines = out.splitlines()
            if len([l for l in outlines if l.startswith('Jobs status:')]) == 1:
                success = True
                break
            print('Crab status seems to have failed (rc={}), retrying...'.format(rc))
        if not success:
            print('Crab status seems to have failed, skipping this task.')
            if outlines:
                print('  last output: {}'.format(outlines[-1][:200]))
            entry['status'] = {'crab status': 'failed'}
            continue

        jobsfailed = False
        statuscompleted = False

        # parse the text from the output
        for line in outlines:
            line = line.replace('Jobs status:','')
            words = line.split()
            if len(words)==0: continue
            # check for known job statuses
            for status in webstyle.STATUS_ORDER:
                if status in words[0]:
                    try: frac = words[1]
                    except: frac = '<none>'
                    # save to dict
                    entry['status'][status] = frac
                    # check if jobs failed for this task
                    if( status=='failed' ): jobsfailed = True
                    print('Percentage '+status+': '+frac)
            # find the grafana link
            if line.startswith('Dashboard monitoring URL'):
                entry['grafana'] = words[3]
            # the CRAB task name: the timestamped identifier crab itself uses, which
            # cannot be derived from the directory layout. Free to pick up here, since
            # this output is already being read.
            if line.startswith('Task name:'):
                entry['task'] = line.split(':', 1)[1].strip()

            # check if the task is complete
            if 'Status on the scheduler' in line:
                if 'COMPLETED' in line:
                    if not os.path.isfile(os.path.join(task.path,
                                                       'results/processedLumis.json')):
                        statuscompleted = True

        # handle case where failed jobs were found
        if jobsfailed:
            if args.resubmit:
                print('Found failed jobs, now resubmitting...')
                # --resubmit_args is a single string of extra crab options, so it
                # is split into argv elements here.
                extra = args.resubmit_args.split() if args.resubmit_args else []
                rc, out = crabcmd.run(['resubmit', task.path] + extra,
                                      proxy=args.proxy)
                print(out.strip())
                print('Done' if rc == 0 else 'Resubmit returned {}'.format(rc))

        # handle case where the task is complete
        if statuscompleted:
            print('This task is completed...')

    # make web interface for gathered completion data              
    os.chdir(wdir)
    print('Loop over all tasks completed.')
    print('Retrieved following data:')
    print(data)
    webpath = os.path.abspath(args.webdir)
    if not os.path.exists(webpath): os.makedirs(webpath)

    # Dump the gathered data as JSON, next to the page, for debugging and for any
    # other tool that wants the numbers.
    statusjson = os.path.join(webpath, 'status.json')
    try:
        with open(statusjson, 'w') as fout:
            json.dump(data, fout, indent=2, sort_keys=True)
        print('Status data written to {}.'.format(statusjson))
    except Exception as e:
        print('WARNING: could not write {}: {}'.format(statusjson, e))

    written = web(data, webpath)
    fullpath = os.path.join(webpath, 'index.html')
    if written:
        print('Status page written to {}.'.format(fullpath))
    else:
        print('Page NOT rewritten (see the error above); the previous one is kept.')

    # Mirror the per-job failure logs into the same web area.
    if not args.no_mirror_logs:
        print('\nMirroring per-job failure logs into {}'.format(webpath))
        try:
            mirror_job_logs.mirror(
                tasks, webpath, proxy=args.proxy,
                status_data=data,
                options=mirror_job_logs.Options(
                    max_per_group=args.mirror_max_per_group,
                    max_per_task=args.mirror_max_per_task,
                    keep_days=args.mirror_keep_days,
                    no_scrub=args.mirror_no_scrub))
        except Exception as e:
            print('WARNING: log mirroring failed ({}); status page is unaffected'
                  .format(e))

    print('\nPages are in {}'.format(webpath))
    print('Done.')
