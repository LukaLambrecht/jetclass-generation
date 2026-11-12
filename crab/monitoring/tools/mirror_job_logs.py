#!/usr/bin/env python3
#######################################################################################
# Mirror per-job CRAB failure logs into the monitoring web area                        #
#######################################################################################
#
# WHY THIS EXISTS
#
# cmsweb.cern.ch authenticates with an X.509 client certificate, not CERN SSO, so the
# per-job log URLs that `crab status` prints (https://cmsweb.cern.ch/scheddmon/...)
# cannot be opened from a browser without the grid certificate installed - a phone, for
# instance. This script runs where a proxy IS available (the acron monitoring sweep),
# pulls the logs itself, and drops them in the web area next to monitor_crab_jobs'
# index.html, which is reachable with an ordinary CERN login.
#
# THE TASK-VS-JOB PROBLEM, AND WHY WE GROUP
#
# `crab status` is per task; logs are per job. The naive bridge - mirror every failed
# job's log - is useless: when a task fails systematically, all 4000 logs are the same
# file, i.e. one bit of information spread over 250 MB and 4000 links.
#
# So this groups failed jobs by failure mode and mirrors only a few REPRESENTATIVES per
# group. Two cheap sources make that possible without fetching anything:
#   * `crab status --json` returns a per-job dict, each entry carrying
#     'State', 'Retries' and 'Error' = [exit code, reason, {}].
#   * that exit code + reason already names most failure modes for free.
#
# Exit code alone is NOT a sufficient signature, though. 50115 ("BadFWJRXML") is a
# generic bucket: run_job.sh writes the framework job report as its last act, so ANY
# earlier death reports as 50115 and genuinely different problems collapse into one
# row. For each group we therefore also extract a signature line from a fetched
# representative, which is the difference between a row reading
#     50115 x 3850
# and one reading
#     50115 x 3850 - PYTHIA Abort: PDF initialization failed
#
# PRIVACY
#
# Job logs embed the submitter's certificate DN and e-mail address (CRAB_UserDN,
# CRAB_UserEmail, x509UserProxyEmail, x509userproxysubject, and the proxy-info block).
# The web area's access control lives in the WebEOS site settings, not in a file we can
# read here, so we must not assume it is restricted: every mirrored log is scrubbed
# before it is written. Scrubbing is on by default and `--no-scrub` has to be asked for.
#
# COST AND CADENCE
#
# `crab status --json` is an extra crab call per task (tens of seconds), which matters
# at a 15-minute cadence over many tasks. Two things keep it cheap:
#   * --status-json: monitor_crab_jobs.py dumps its own per-task summary, and we then
#     only pay the per-job call for tasks that actually have failures.
#   * a cache keyed on (task, job, retry): a log already mirrored is never refetched,
#     so a steady-state task with an unchanged failure set costs one status call.
#
# This is deliberately a SEPARATE module rather than extra logic inside
# monitor_crab_jobs.py: if anything in here breaks, the status page that the sweep
# exists to produce is unaffected. monitor_crab_jobs.py calls mirror() only after the
# page has been written and published, inside a try/except, so a failure here cannot
# turn a successful monitoring run into a failed one.
#
# USAGE
#   Normal use is through ../monitor_crab_jobs.py, which calls mirror().
#   Standalone, for debugging one step:
#     python3 -m tools.mirror_job_logs -i <searchdir> -o <webdir> [-p <proxy>]
#######################################################################################

import argparse
import glob
import json
import os
import re
import shutil
import sys
import time

from . import crabcmd
from . import inputs
from . import webstyle

# Job states worth mirroring. 'killed' is excluded on purpose: a task we killed
# ourselves produces thousands of uninformative termination logs.
FAILED_STATES = ('failed',)

# Lines that name the real cause, best first. Matched against the log body.
SIGNATURE_PATTERNS = (
    r'Fatal Exception',
    r'PYTHIA Abort[^\n]*',
    r'An exception of category [^\n]*',
    r'ERROR: [^\n]*',
    r'Removed due to [^\n]*',
    r'error while loading shared libraries[^\n]*',
    r'Segmentation fault[^\n]*',
    r'No such file or directory[^\n]*',
    r'Traceback \(most recent call last\)',
)

# Noise that must never be taken as a signature. The condor job ad is echoed verbatim
# into every log, and PeriodicRemoveReason contains the literal strings "Removed due to
# memory use", "Removed due to wall clock limit" etc. as ClassAd source - present in
# every log whether or not anything was removed. Matching it would label all failures
# with the same wrong cause.
SIGNATURE_EXCLUDE = (
    '== JOB AD:',
    '== ENV:',
    'PeriodicRemove',
    'use crab status --verboseErrors',
)

# Redactions applied to every mirrored log. Value-level rather than line-level, so the
# surrounding line stays readable and we do not depend on knowing every key that can
# carry a DN.
REDACTIONS = (
    # X.509 subject/issuer DNs, with however many components follow.
    #
    # NOTE the component pattern [^/"\n]+ : DN components CONTAIN SPACES
    # ("/OU=Organic Units", "/CN=Firstname Lastname"). An earlier version excluded
    # whitespace, so it stopped at the first space and left the holder's real name in
    # the file - redaction that looks like it worked and does not. Bound components on
    # '/', '"' and newline only, which are the characters that actually end one.
    (re.compile(r'/DC=[A-Za-z]+/DC=[A-Za-z]+(?:/[A-Za-z]+=[^/"\n]+)+'), '<DN redacted>'),
    # bare e-mail addresses
    (re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'), '<email redacted>'),
)

# BUMP THIS whenever REDACTIONS changes. It is part of the cache key, so an already
# mirrored log is otherwise never rewritten and a scrubbing fix would silently fail to
# apply to the files that motivated it - the logs already on the web would keep
# whatever the old, broken pattern let through.
SCRUB_VERSION = 2

# Job ids listed per failure mode before the list is truncated.
JOBIDS_SHOWN = 40

# Defaults shared by Options and the command line.
DEFAULT_MAX_PER_GROUP = 3
DEFAULT_MAX_PER_TASK = 15
DEFAULT_KEEP_DAYS = 30
DEFAULT_TIMEOUT = 900



def log(msg):
    print('[mirror_job_logs] {}'.format(msg), flush=True)


def safe_name(task):
    """Filesystem/URL-safe form of a CRAB task name ('261112_083348:llambrec_crab_x')."""
    return re.sub(r'[^A-Za-z0-9_.-]', '_', task)


def extract_json_blobs(text):
    """Pull every JSON value out of mixed human-readable + JSON crab output.

    `crab status --json` prints its human report first and the JSON after it, and may
    emit more than one value, so json.loads on the whole thing raises "Extra data".
    """
    dec = json.JSONDecoder()
    out = []
    i = 0
    while i < len(text):
        while i < len(text) and text[i] not in '{[':
            i += 1
        if i >= len(text):
            break
        try:
            obj, end = dec.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        out.append(obj)
        i = end
    return out


def find_job_dict(blobs):
    """Pick the per-job mapping: {'1': {'State':..., 'Error':[...]}, ...}."""
    best = None
    for obj in blobs:
        if not isinstance(obj, dict) or not obj:
            continue
        vals = [v for v in obj.values() if isinstance(v, dict)]
        if len(vals) != len(obj):
            continue
        if not any('State' in v for v in vals):
            continue
        if best is None or len(obj) > len(best):
            best = obj
    return best


def parse_task_header(text):
    """Task name and scheduler status from the human-readable part of crab status."""
    info = {'task': '', 'scheduler': '', 'server': '', 'grafana': ''}
    for line in text.splitlines():
        if line.startswith('Task name:'):
            info['task'] = line.split(':', 1)[1].strip()
        elif line.startswith('Status on the scheduler:'):
            info['scheduler'] = line.split(':', 1)[1].strip()
        elif line.startswith('Status on the CRAB server:'):
            info['server'] = line.split(':', 1)[1].strip()
        elif line.startswith('Dashboard monitoring URL:'):
            info['grafana'] = line.split(':', 1)[1].strip()
    return info


def group_failures(jobs):
    """Group failed jobs by (exit code, reason).

    Returns a list of dicts, biggest group first, each with 'code', 'reason', 'jobids'
    (sorted numerically) and 'retries' (job id -> final retry number).
    """
    groups = {}
    for jobid, info in jobs.items():
        if not isinstance(info, dict):
            continue
        if info.get('State') not in FAILED_STATES:
            continue
        err = info.get('Error') or []
        code, reason = 'unknown', ''
        if isinstance(err, (list, tuple)) and len(err) >= 1:
            code = err[0]
            if len(err) >= 2 and isinstance(err[1], str):
                reason = err[1]
        key = (str(code), reason)
        g = groups.setdefault(key, {'code': str(code), 'reason': reason,
                                    'jobids': [], 'retries': {}})
        g['jobids'].append(jobid)
        g['retries'][jobid] = info.get('Retries', 0)
    for g in groups.values():
        g['jobids'].sort(key=lambda s: (len(s), s))
    return sorted(groups.values(), key=lambda g: -len(g['jobids']))


def scrub(text):
    for pattern, repl in REDACTIONS:
        text = pattern.sub(repl, text)
    return text


def signature_of(text):
    """First line naming a plausible cause, skipping the echoed job ad / environment."""
    excl = SIGNATURE_EXCLUDE
    for pattern in SIGNATURE_PATTERNS:
        rx = re.compile(pattern)
        for line in text.splitlines():
            if any(e in line for e in excl):
                continue
            m = rx.search(line)
            if m:
                sig = m.group(0).strip()
                # drop the run_job.sh "== CMSSW:" prefix noise if it survived
                sig = re.sub(r'^==\s*CMSSW:\s*', '', sig)
                return sig[:200]
    return ''


def fetch_logs(task, jobids, proxy, timeout):
    """crab getlog --short for the given job ids.

    Returns {jobid: path} for the HIGHEST retry of each job: getlog pulls every retry,
    and the last one is the failure that actually stuck. Returns what it managed to
    get; a partial result is still useful.
    """
    if not jobids:
        return {}
    rc, out = crabcmd.run(['getlog', '--short',
                           '--jobids={}'.format(','.join(jobids)),
                           '-d', task.path], proxy=proxy, timeout=timeout)
    results_dir = os.path.join(task.path, 'results')
    found = {}
    for jobid in jobids:
        cands = glob.glob(os.path.join(results_dir,
                                       'job_out.{}.*.txt'.format(jobid)))
        best, best_retry = None, -1
        for c in cands:
            m = re.search(r'job_out\.{}\.(\d+)\.txt$'.format(re.escape(jobid)), c)
            if not m:
                continue
            if int(m.group(1)) > best_retry:
                best, best_retry = c, int(m.group(1))
        if best is not None:
            found[jobid] = (best, best_retry)
    if rc != 0 and not found:
        log('  getlog failed (rc={}) and produced nothing; tail: {}'
            .format(rc, out.strip().splitlines()[-1:] or ''))
    return found


def mirror_task(task, outdir, proxy, opts, cache):
    """Mirror one task. Returns a summary dict for the index page, or None to skip."""
    rc, out = crabcmd.run(['status', '--json', task.path],
                          proxy=proxy, timeout=opts.status_timeout)
    header = parse_task_header(out)
    jobs = find_job_dict(extract_json_blobs(out))
    if jobs is None:
        log('  no per-job JSON in crab status output (rc={}) - skipping'.format(rc))
        return None

    groups = group_failures(jobs)
    nfailed = sum(len(g['jobids']) for g in groups)
    task_name = header['task'] or task.request
    tsafe = safe_name(task_name)
    log('  task {}: {} failed job(s) in {} group(s)'
        .format(task_name, nfailed, len(groups)))

    logdir = os.path.join(outdir, 'logs', tsafe)
    nfetched = 0
    budget = opts.max_per_task
    for g in groups:
        g['logs'] = []
        g['signature'] = ''
        reps = g['jobids'][:opts.max_per_group]
        want = []
        for jobid in reps:
            retry = g['retries'].get(jobid, 0)
            key = '{}|{}|{}|s{}'.format(tsafe, jobid, retry, SCRUB_VERSION)
            dest = os.path.join(logdir, 'job_{}_retry{}.txt'.format(jobid, retry))
            if key in cache and os.path.exists(dest):
                g['logs'].append(os.path.basename(dest))
                if not g['signature']:
                    try:
                        with open(dest, encoding='utf-8', errors='replace') as fh:
                            g['signature'] = signature_of(fh.read())
                    except OSError:
                        pass
                continue
            want.append(jobid)
        want = want[:max(0, budget - nfetched)]
        if want:
            if not os.path.isdir(logdir):
                os.makedirs(logdir)
            got = fetch_logs(task, want, proxy, opts.getlog_timeout)
            for jobid, (src, retry) in sorted(got.items()):
                try:
                    with open(src, encoding='utf-8', errors='replace') as fh:
                        body = fh.read()
                except OSError as e:
                    log('  could not read {}: {}'.format(src, e))
                    continue
                if not opts.no_scrub:
                    body = scrub(body)
                dest = os.path.join(logdir, 'job_{}_retry{}.txt'.format(jobid, retry))
                with open(dest, 'w', encoding='utf-8') as fh:
                    fh.write(body)
                g['logs'].append(os.path.basename(dest))
                cache['{}|{}|{}|s{}'.format(tsafe, jobid, retry,
                                            SCRUB_VERSION)] = int(time.time())
                nfetched += 1
                if not g['signature']:
                    g['signature'] = signature_of(body)
        g['logs'].sort()

    write_task_page(outdir, tsafe, task_name, header, jobs, groups, nfailed)
    # Remember which task page belongs to this project dir, so a later run that skips
    # this task (because it has no failures any more) can delete the now-stale page
    # instead of leaving it behind, unlinked, reporting failures that are gone.
    cache['taskmap|{}'.format(task.key)] = tsafe
    return {'task': task_name, 'safe': tsafe, 'nfailed': nfailed,
            'ngroups': len(groups), 'scheduler': header['scheduler'],
            'top': groups[0] if groups else None, 'nfetched': nfetched}


def write_task_page(outdir, tsafe, task, header, jobs, groups, nfailed):
    """One page per task: job-state legend, then one row per failure mode."""
    states = {}
    for info in jobs.values():
        if isinstance(info, dict):
            st = info.get('State', 'unknown')
            states[st] = states.get(st, 0) + 1

    sub = '{} &middot; scheduler: {} &middot; Last update: {}'.format(
        webstyle.esc(task), webstyle.esc(header.get('scheduler') or '?'),
        webstyle.timestamp())
    p = webstyle.page_head('Job failures', sub)

    if header.get('grafana'):
        p += ('<p class="muted"><a href="{}" target="_blank" rel="noopener">'
              'Grafana &#8599;</a></p>\n').format(webstyle.esc(header['grafana']))

    # Counts, not percentages - this page is about which jobs, not what fraction.
    p += webstyle.status_legend({k: str(v) for k, v in states.items()})

    if not groups:
        p += '<p class="muted">No failed jobs.</p>\n'
    else:
        p += ('<p class="muted">{} failed job(s) in {} distinct failure mode(s). '
              'The linked logs are representatives: jobs grouped on one row failed '
              'the same way.</p>\n').format(nfailed, len(groups))
        p += '<table>\n<tr><th>Exit</th><th>Jobs</th><th>Cause</th><th>Logs</th></tr>\n'
        for g in groups:
            cause = webstyle.esc(g['reason'] or '')
            if g.get('signature'):
                cause += '<br><code>{}</code>'.format(webstyle.esc(g['signature']))
            links = ' '.join(
                '<a href="logs/{}/{}">#{}</a>'.format(
                    webstyle.esc(tsafe), webstyle.esc(fn),
                    webstyle.esc(fn.split('_')[1]))
                for fn in g['logs'])
            p += ('<tr><td class="nowrap"><code>{}</code></td><td>{}</td>'
                  '<td>{}</td><td class="nowrap">{}</td></tr>\n').format(
                webstyle.esc(g['code']), len(g['jobids']), cause,
                links or '<span class="muted">none</span>')
        p += '</table>\n'

        p += '<details>\n<summary>Job ids per failure mode</summary>\n<table>\n'
        for g in groups:
            shown = ', '.join(g['jobids'][:JOBIDS_SHOWN])
            if len(g['jobids']) > JOBIDS_SHOWN:
                shown += ', ... (+{} more)'.format(len(g['jobids']) - JOBIDS_SHOWN)
            p += '<tr><td class="nowrap"><code>{}</code></td><td><code>{}</code></td></tr>\n'.format(
                webstyle.esc(g['code']), webstyle.esc(shown))
        p += '</table>\n</details>\n'

    p += webstyle.page_foot([('failures.html', '\u2190 All tasks'),
                             ('index.html', 'Task status')])
    webstyle.write_atomic(os.path.join(outdir, 'task_{}.html'.format(tsafe)), p)


def write_index(outdir, summaries):
    """Overview across tasks: who is failing, how badly, and why."""
    p = webstyle.page_head('CRAB job failures',
                           'Last update: {}'.format(webstyle.timestamp()))
    live = [s for s in summaries if s]
    withfail = [s for s in live if s['nfailed']]

    if not live:
        p += ('<p class="muted">No task needed inspecting: no reported failures.'
              '</p>\n')
    elif not withfail:
        p += '<p><span class="pill">No failed jobs in any task</span></p>\n'
    else:
        p += '<table>\n<tr><th>Task</th><th>Failed</th><th>Modes</th><th>Top cause</th></tr>\n'
        for s in sorted(withfail, key=lambda s: -s['nfailed']):
            top = ''
            if s['top']:
                top = webstyle.esc(s['top']['reason'] or s['top']['code'])
                if s['top'].get('signature'):
                    top += '<br><code>{}</code>'.format(
                        webstyle.esc(s['top']['signature']))
            p += ('<tr><td><div class="name"><a href="task_{}.html">{}</a></div>'
                  '<div class="muted">{}</div></td>'
                  '<td>{}</td><td>{}</td><td>{}</td></tr>\n').format(
                webstyle.esc(s['safe']), webstyle.esc(s['task']),
                webstyle.esc(s['scheduler'] or ''), s['nfailed'], s['ngroups'],
                top or '<span class="muted">-</span>')
        p += '</table>\n'

    p += webstyle.page_foot([('index.html', '\u2190 Task status')])
    webstyle.write_atomic(os.path.join(outdir, 'failures.html'), p)


def prune(outdir, keep_tasks, keep_days):
    """Drop mirrored logs for tasks no longer monitored, or older than keep_days."""
    logroot = os.path.join(outdir, 'logs')
    if not os.path.isdir(logroot):
        return
    cutoff = time.time() - keep_days * 86400
    for name in sorted(os.listdir(logroot)):
        path = os.path.join(logroot, name)
        if not os.path.isdir(path):
            continue
        try:
            mtime = max([os.path.getmtime(os.path.join(path, f))
                         for f in os.listdir(path)] or [0])
        except OSError:
            continue
        if name not in keep_tasks and mtime < cutoff:
            log('pruning stale logs for {}'.format(name))
            shutil.rmtree(path, ignore_errors=True)
            page = os.path.join(outdir, 'task_{}.html'.format(name))
            if os.path.exists(page):
                os.remove(page)


def tasks_with_failures(status_data):
    """Task keys that the monitoring pass saw failures for.

    Returns None for "no filter, process everything" - an absent or unusable summary
    must not silently disable mirroring, which is the whole point of the step.
    """
    if not status_data:
        return None
    try:
        out = set()
        for name, info in (status_data.get('samples') or {}).items():
            st = (info or {}).get('status') or {}
            frac = st.get('failed') or st.get('toRetry')
            if st.get('crab status') == 'failed':
                out.add(name)          # could not be read; look at it properly
                continue
            if frac and frac not in ('0%', '0.0%', '<none>'):
                out.add(name)
        return out
    except Exception as e:                                   # noqa: BLE001
        log('could not use the status summary ({}); processing all tasks'.format(e))
        return None


class Options:
    """Tunables for a mirroring run; the defaults are also the CLI defaults.

    Attribute names match the argparse destinations, so a parsed namespace can be
    used wherever an Options is expected and vice versa.
    """

    def __init__(self, max_per_group=DEFAULT_MAX_PER_GROUP,
                 max_per_task=DEFAULT_MAX_PER_TASK,
                 keep_days=DEFAULT_KEEP_DAYS, no_scrub=False,
                 status_timeout=DEFAULT_TIMEOUT, getlog_timeout=DEFAULT_TIMEOUT):
        self.max_per_group = max_per_group
        self.max_per_task = max_per_task
        self.keep_days = keep_days
        self.no_scrub = no_scrub
        self.status_timeout = status_timeout
        self.getlog_timeout = getlog_timeout


def mirror(tasks, outdir, proxy=None, status_data=None, cache_file=None,
           options=None):
    """Mirror per-job failure logs for the given CRAB tasks.

    - tasks:       inputs.Task objects (see tools/inputs.py). Discovery lives there,
                   shared with the monitoring and the kill step, so all three select
                   tasks the same way.
    - outdir:      web directory for failures.html, the task pages and logs/.
    - proxy:       grid proxy path, passed to crab as --proxy.
    - status_data: the monitoring summary dict; when given, only tasks it reports
                   failures for pay the expensive per-job 'crab status --json' call.
    - cache_file:  record of already-mirrored logs (default <outdir>/.mirror_cache.json).

    Returns {'tasks': n, 'failed': n, 'fetched': n}. Raises only on bad arguments: a
    task that cannot be processed is logged and skipped, so one failure cannot cost
    the rest or the pages.
    """
    opts = options or Options()
    tasks = list(tasks)
    outdir = os.path.abspath(outdir)
    if proxy is not None and not os.path.exists(proxy):
        raise ValueError('proxy {} does not exist'.format(proxy))
    if not os.path.isdir(outdir):
        os.makedirs(outdir)

    cachefile = cache_file or os.path.join(outdir, '.mirror_cache.json')
    cache = {}
    if os.path.exists(cachefile):
        try:
            with open(cachefile, encoding='utf-8') as fh:
                cache = json.load(fh)
        except Exception as e:                               # noqa: BLE001
            log('ignoring unreadable cache {} ({})'.format(cachefile, e))

    if not tasks:
        log('no tasks to mirror')
        write_index(outdir, [])
        return {'tasks': 0, 'failed': 0, 'fetched': 0}

    only = tasks_with_failures(status_data)
    if only is not None:
        skipped = [t for t in tasks if t.key not in only]
        tasks = [t for t in tasks if t.key in only]
        log('{} task(s) with failures per status summary, {} skipped'
            .format(len(tasks), len(skipped)))
        for t in skipped:
            stale = cache.get('taskmap|{}'.format(t.key))
            if not stale:
                continue
            page = os.path.join(outdir, 'task_{}.html'.format(stale))
            if os.path.exists(page):
                log('removing stale failure page for {} (no failures now)'.format(stale))
                os.remove(page)

    summaries, keep = [], set()
    for t in tasks:
        log('processing {}'.format(t.path))
        try:
            s = mirror_task(t, outdir, proxy, opts, cache)
        except Exception as e:                               # noqa: BLE001
            # One bad task must not cost us the others, nor the pages.
            log('ERROR mirroring {}: {}'.format(t.path, e))
            continue
        if s:
            summaries.append(s)
            keep.add(s['safe'])

    write_index(outdir, summaries)
    prune(outdir, keep, opts.keep_days)

    try:
        with open(cachefile, 'w', encoding='utf-8') as fh:
            json.dump(cache, fh, indent=1, sort_keys=True)
    except OSError as e:
        log('could not write cache {}: {}'.format(cachefile, e))

    total = sum(s['nfailed'] for s in summaries)
    fetched = sum(s['nfetched'] for s in summaries)
    log('done: {} task(s), {} failed job(s), {} new log(s) mirrored into {}'
        .format(len(summaries), total, fetched, outdir))
    return {'tasks': len(summaries), 'failed': total, 'fetched': fetched}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='python3 -m tools.mirror_job_logs',
        description='Mirror per-job CRAB failure logs into a web area.')
    ap.add_argument('-i', '--searchdir', default=[], nargs='+', metavar='DIR',
                    help='Directory/ies scanned recursively for CRAB project dirs')
    ap.add_argument('-t', '--requestdir', default=[], nargs='+', metavar='DIR',
                    help='CRAB project directory/ies (crab_<requestName>)')
    ap.add_argument('-o', '--outdir', required=True, type=os.path.abspath,
                    help='Web directory to write failures.html, task pages and logs into')
    ap.add_argument('-p', '--proxy', default=None,
                    help='Path to a valid grid proxy (passed to crab as --proxy)')
    ap.add_argument('--status-json', default=None,
                    help='Status summary written by monitor_crab_jobs.py; limits the '
                         'expensive per-job call to tasks that have failures')
    ap.add_argument('--max-per-group', default=DEFAULT_MAX_PER_GROUP, type=int,
                    help='Representative logs per failure mode (default %(default)s)')
    ap.add_argument('--max-per-task', default=DEFAULT_MAX_PER_TASK, type=int,
                    help='Cap on logs fetched per task per run (default %(default)s)')
    ap.add_argument('--keep-days', default=DEFAULT_KEEP_DAYS, type=int,
                    help='Prune logs of unmonitored tasks after this many days '
                         '(default %(default)s)')
    ap.add_argument('--cache', default=None,
                    help='Cache file of already-mirrored (task, job, retry) '
                         '(default: <outdir>/.mirror_cache.json)')
    ap.add_argument('--no-scrub', action='store_true',
                    help='Do NOT redact certificate DNs and e-mail addresses. '
                         'Only safe if the web area is access-controlled.')
    ap.add_argument('--status-timeout', default=DEFAULT_TIMEOUT, type=int)
    ap.add_argument('--getlog-timeout', default=DEFAULT_TIMEOUT, type=int)
    args = ap.parse_args(argv)

    status_data = None
    if args.status_json and os.path.exists(args.status_json):
        try:
            with open(args.status_json, encoding='utf-8') as fh:
                status_data = json.load(fh)
        except Exception as e:                               # noqa: BLE001
            log('could not read {} ({}); processing all tasks'.format(
                args.status_json, e))

    try:
        tasks = inputs.collect(args.searchdir, args.requestdir)
    except ValueError as e:
        ap.error(str(e))
        return 1

    try:
        mirror(tasks, args.outdir, proxy=args.proxy,
               status_data=status_data, cache_file=args.cache,
               options=Options(max_per_group=args.max_per_group,
                               max_per_task=args.max_per_task,
                               keep_days=args.keep_days,
                               no_scrub=args.no_scrub,
                               status_timeout=args.status_timeout,
                               getlog_timeout=args.getlog_timeout))
    except ValueError as e:
        log('ERROR: {}'.format(e))
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
