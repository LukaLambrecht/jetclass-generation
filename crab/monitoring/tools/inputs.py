# Working out which CRAB tasks to act on
#
# In general, this module expects the CRAB working directories to be organized
# as follows (which should be the case for regular CRAB submissions):
#
#     <any user-defined directory structure>/<workArea>/crab_<requestName>/
#
# from two CRAB config settings:
#   config.General.workArea     - where crab puts the project directory.
#   config.General.requestName  - the task's name. crab creates the directory as
#                                 crab_<requestName>, adding the prefix itself.
#
# CRAB calls that innermost directory the **project directory**: `crab status` prints
# "CRAB project directory: ..." and its flag is `-d/--dir PROJDIR`.
#
# PROJECT DIRECTORIES
#
# A project directory is recognized by two criteria:
# - The `.requestcache` file crab writes inside it (this is also what CRAB uses internally).
# - The `crab_` name prefix automatically added by crab before each project directory.
# Directories not starting with `crab_` are ignored (though that option can be disabled).
# Directories called `crab_*` without the .requestcache are reported, because they could be
# a task that was never submitted (or whose cache was deleted).
#
# TWO WAYS TO SAY WHAT TO ACT ON
#
#   search directories  - scanned recursively for project directories, wherever they
#                         sit and whatever the workArea is called. Several may be
#                         given and the union is taken.
#   request directories  - project directories named individually. For tasks scattered
#                         across unrelated places, or to act on a subset.
#
# Both may be combined; the result is deduplicated by real path.
#
# NAME COLLISIONS
#
# Tasks are identified for display and for the status dictionary by their request
# name. Two productions can legitimately use the same one.
# To avoid silent overwriting, collect() therefore detects clashes, says
# exactly which paths collided, and disambiguates them by location rather than
# dropping either: see _resolve_collisions for details.

import os
import pickle

# The file crab writes into every project directory.
# Used to identify project directories in the search.
REQUEST_MARKER = '.requestcache'

# Prefix crab prepends to requestName when it creates the directory.
REQUEST_PREFIX = 'crab_'

class Task(object):
    """One CRAB task, i.e. one CRAB project directory.

    - path:    absolute path of the project directory; this is what is passed to crab
    - request: the CRAB requestName (see the module header)
    - key:     unique identifier, normally the request name. collect() extends it
               with the task's location to break a collision.
    """

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.request = parse_request(self.path)
        self.key = self.request
        self._cache = None             # lazily filled by .cache

    @property
    def workarea(self):
        """The directory the project directory sits in (config.General.workArea)."""
        return os.path.dirname(self.path)

    @property
    def cache(self):
        """The parsed .requestcache, read once per task and then remembered."""
        if self._cache is None:
            self._cache = read_requestcache(self.path)
        return self._cache

    @property
    def output_dir(self):
        """Where crab stages this task's output, as a logical file name (LFN).

        Composed exactly as crab composes CRAB_OutLFNDir:
            <Data.outLFNDirBase>/<outputPrimaryDataset>/<outputDatasetTag>/<timestamp>
        with the timestamp taken from the task name.
        Returns '' if the pieces are not all available.
        """
        c = self.cache
        base = c.get('outLFNDirBase')
        dataset = c.get('outputPrimaryDataset')
        tag = c.get('outputDatasetTag') or self.request
        stamp = (c.get('RequestName') or '').split(':')[0]
        if not (base and dataset and tag and stamp):
            return ''
        return '/'.join([base.rstrip('/'), dataset, tag, stamp])

    def __repr__(self):
        return 'Task({!r})'.format(self.path)


def parse_request(path):
    """config.General.requestName for a project directory path.

    Parsing: strip the 'crab_' prefix (added by CRAB).
    Anything not carrying the prefix is passed through unchanged.
    """
    base = os.path.basename(path.rstrip(os.sep))
    return base[len(REQUEST_PREFIX):] if base.startswith(REQUEST_PREFIX) else base


class _Stub(object):
    """Stands in for any class named by a pickle, so nothing is imported or run.

    .requestcache is a pickle of crab's own config objects, whose classes live in
    WMCore - not importable outside a crab environment, and not something we want to
    import in order to read four strings. Unpickling with every class replaced by this
    stub keeps the attribute dictionaries (which is all we are after) and makes the
    read inert: a pickle cannot name a callable we will execute.
    """

    def __init__(self, *args, **kwargs):
        pass

    def __setstate__(self, state):
        if isinstance(state, dict):
            self.__dict__.update(state)


class _SafeUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        return _Stub


def read_requestcache(taskpath):
    """Fields of interest from a task's .requestcache.

    Returns a flat dict: RequestName plus the config's Data section entries. An
    unreadable or unexpected cache returns an empty dict.
    """
    path = os.path.join(taskpath, REQUEST_MARKER)
    out = {}
    try:
        with open(path, 'rb') as fh:
            obj = _SafeUnpickler(fh).load()
        if not isinstance(obj, dict):
            return {}
        if isinstance(obj.get('RequestName'), str):
            out['RequestName'] = obj['RequestName']
        config = obj.get('OriginalConfig')
        data = getattr(config, 'Data', None)
        for key, value in vars(data).items() if data is not None else ():
            if isinstance(value, str):
                out[key] = value
    except Exception:                                        # noqa: BLE001
        return {}
    return out


def is_request_dir(path):
    """True if path is a CRAB project directory, by crab's own marker file."""
    return os.path.isdir(path) and os.path.exists(os.path.join(path, REQUEST_MARKER))


def discover(searchdirs, require_prefix=True):
    """Find project directories under the given roots, at any depth.

    require_prefix: only look for the marker inside directories whose own name starts
        with 'crab_'. The crab client hard-codes that prefix when it creates a project
        directory, so this costs nothing in coverage and saves a stat() on every other
        directory in the tree.
        The exception is a renamed project directory, which crab itself would still
        accept; pass require_prefix=False to find those too.

    Returns (found, suspicious): the project directories, and any crab_*-looking
    directories that lack the marker (they could be tasks that failed to submit).
    """
    found, suspicious = [], []
    for root in _as_list(searchdirs):
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            raise ValueError('search directory {} does not exist'.format(root))
        if is_request_dir(root):       # a root that is itself a task
            found.append(root)
            continue
        for dirpath, dirnames, _ in os.walk(root):
            # Prune in place: never descend into a project directory and skip hidden trees.
            keep = []
            for name in sorted(dirnames):
                if name.startswith('.'):
                    continue
                candidate = name.startswith(REQUEST_PREFIX) or not require_prefix
                if not candidate:
                    keep.append(name)  # descend, but do not stat it
                    continue
                full = os.path.join(dirpath, name)
                if is_request_dir(full):
                    found.append(full)
                    continue           # pruned: not added to keep
                if name.startswith(REQUEST_PREFIX):
                    suspicious.append(full)
                keep.append(name)
            dirnames[:] = keep
    return found, suspicious


def from_requestdirs(requestdirs):
    """Project directories named individually, validated to exist.

    A directory without the marker is accepted but reported: an explicit instruction
    outranks our inference, and the caller may be pointing at something crab will
    nonetheless handle. Returns (found, suspicious).
    """
    found, suspicious = [], []
    for d in _as_list(requestdirs):
        d = os.path.abspath(d)
        if not os.path.isdir(d):
            raise ValueError('request directory {} does not exist'.format(d))
        if not is_request_dir(d):
            suspicious.append(d)
        found.append(d)
    return found, suspicious


def collect(searchdirs=None, requestdirs=None, quiet=False):
    """The tasks to act on, from search roots and/or named project directories.

    Deduplicates by real path (the same task reachable two ways is one task) and
    reports and disambiguates colliding request names.

    Returns a list of Task, sorted by key. Raises ValueError if a given path does not
    exist, or if nothing at all was requested.
    """
    if not _as_list(searchdirs) and not _as_list(requestdirs):
        raise ValueError('no search directories and no request directories given')

    found_s, susp_s = discover(searchdirs)
    found_r, susp_r = from_requestdirs(requestdirs)
    paths = found_s + found_r
    suspicious = susp_s + susp_r

    # A crab_*-named directory that CONTAINS tasks cannot be a failed task,
    # so should not be flagged as suspicious.
    suspicious = [d for d in suspicious
                  if not any(f.startswith(d + os.sep) for f in paths)]

    if suspicious and not quiet:
        print('WARNING: {} directory/ies look like CRAB projects but have no {}'
              ' (never submitted, or the cache was removed):'
              .format(len(suspicious), REQUEST_MARKER))
        for d in sorted(set(suspicious)):
            print('  - {}'.format(d))

    # Deduplicate on the resolved path: the same task can be reached through a
    # symlink, through two overlapping search roots, or named explicitly as well as
    # found by a scan.
    seen, unique = set(), []
    for p in sorted(paths):
        real = os.path.realpath(p)
        if real in seen:
            continue
        seen.add(real)
        unique.append(p)

    tasks = [Task(p) for p in unique]
    tasks = _resolve_collisions(tasks, quiet=quiet)
    return sorted(tasks, key=lambda t: t.key.lower())


def _resolve_collisions(tasks, quiet=False):
    """Make task keys unique, reporting any that were not.

    A collision is disambiguated rather than treated as fatal: monitoring several
    productions should not stop because two of them happen to use the same request
    name. The extra qualifier is the task's own parent chain, which is what actually
    differs, so the resulting key is stable across runs - it does not depend on the
    order tasks were discovered in.
    """
    bykey = {}
    for t in tasks:
        bykey.setdefault(t.key, []).append(t)

    for key, group in sorted(bykey.items()):
        if len(group) < 2:
            continue
        if not quiet:
            print('WARNING: {} tasks share the identity {!r}; '
                  'qualifying them by location:'.format(len(group), key))
        for t in group:
            # The directory above the workArea: the nearest thing to a production
            # name, and what actually differs between two same-named requests.
            qualifier = os.path.basename(os.path.dirname(t.workarea)) or 'root'
            t.key = '{} [{}]'.format(key, qualifier)
            if not quiet:
                print('  - {} -> {!r}'.format(t.path, t.key))

    # A qualifier can itself repeat (same parent name under different roots); fall
    # back to the full path, which is unique by construction.
    bykey = {}
    for t in tasks:
        bykey.setdefault(t.key, []).append(t)
    for key, group in bykey.items():
        if len(group) < 2:
            continue
        for t in group:
            t.key = '{} [{}]'.format(key.split(' [')[0], t.path)
    return tasks


def _as_list(value):
    """Accept None, a single string, or a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)
