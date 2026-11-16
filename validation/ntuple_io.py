#!/usr/bin/env python3

'''Shared input layer that lets the scripts in this directory and in
compare-hlt-to-offline/ read either ntuple schema transparently, so one command can
be pointed at either:

  - "ours": produced by delphes_analyzers/makeNtuples.C (one Delphes card) or
    makeNtuplesPaired.C (an offline+HLT pair). part_*/jet_* for offline, plus
    hlt_part_*/hlt_jet_*/hlt_matched for HLT in a paired production. Identified by
    the presence of a jet_label branch.

  - "fullsim": the CMS offline+scouting reference dataset this pipeline is compared
    against, at
      /eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/
    One row per already-matched (offline, HLT) jet pair, so both sides are always
    present and hlt_matched is reported as always True. Offline particles come in two
    collections (cpfcandlt_* charged, npfcand_* neutral) rather than one combined one,
    while the HLT side (scoutpfcand_*) is already combined. Identified by the presence
    of an fj_label branch.

Every function normalizes onto our own naming (part_*/hlt_part_*/jet_pt/hlt_jet_pt/
hlt_matched) whatever the input was, so callers never branch on the schema. Only
classify_ours_label() and FULLSIM_CATEGORY_FLAGS are schema-specific, for callers that
need a coarse cross-schema category instead of particle content.
'''

import os
import re
import glob

import awkward as ak
import numpy as np
import uproot
import concurrent.futures

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(THISDIR)
DEFAULT_LABEL_HEADER = os.path.join(REPO_DIR, 'delphes_analyzers', 'FatJetMatching.h')

OURS_MARKER = 'jet_label'
FULLSIM_MARKER = 'fj_label'

# ---------------------------------------------------------------------------
# Input discovery, shared by every script that takes ntuples on the command line.
# ---------------------------------------------------------------------------

# Filename patterns of the two schemas: our own productions, and the CMS
# offline+scouting reference dataset.
NTUPLE_GLOBS = ('ntuple_*.root', 'dnnTuples_nanov15_*.root')

# The process families our productions write under <output-path>/<family>/<proc>/...,
# i.e. the top-level subdirectory names of gen_configs/. Matched case-insensitively, so
# a differently-cased family name still parses. The canonical list; print_njets.py
# imports it from here.
OURS_FAMILIES = ('jetclass1', 'jetclass2', 'jetclass2sb')


def discover_ntuples(pattern):
    '''Expand one command-line input into a list of files.

    A directory is searched recursively for both schemas' ntuples, so a whole production
    tree can be passed as is, without hand-writing a glob whose depth matches the layout.
    Anything else is glob-expanded, and a pattern matching nothing is kept as a literal, so
    a plain path still works and a typo fails on the read rather than vanishing here.
    '''
    if os.path.isdir(pattern):
        files = []
        for g in NTUPLE_GLOBS:
            files.extend(glob.glob(os.path.join(pattern, '**', g), recursive=True))
        return sorted(files)
    matched = sorted(glob.glob(pattern))
    return matched if matched else [pattern]


def expand_inputs(patterns):
    '''discover_ntuples() over several inputs, de-duplicated, order preserved.'''
    files, seen = [], set()
    for pattern in patterns:
        for f in discover_ntuples(pattern):
            if f not in seen:
                seen.add(f)
                files.append(f)
    if not files:
        raise ValueError('no files matched: {}'.format(patterns))
    return files


def family_of(path, root):
    '''The gen_configs family a discovered file belongs to, or None.

    `root` is the directory the user passed; the family is the first path component below
    it, validated against OURS_FAMILIES. Pointing at a whole production therefore gives
    e.g. 'jetclass2sb', while pointing at a single family's own directory, or at the
    reference dataset, gives None, meaning "already one sample, do not split further".
    '''
    try:
        rel = os.path.relpath(os.path.dirname(os.path.abspath(path)), os.path.abspath(root))
    except ValueError:
        return None
    parts = [p for p in rel.split(os.sep) if p not in ('.', '')]
    if len(parts) < 2:
        return None
    return parts[0] if parts[0].lower() in OURS_FAMILIES else None

# Per-particle fields load_particles() normalizes onto part_<suffix> and
# hlt_part_<suffix> for both schemas.
PARTICLE_SUFFIXES = ['px', 'py', 'charge', 'energy',
                      'isElectron', 'isMuon', 'isPhoton', 'isChargedHadron', 'isNeutralHadron',
                      # Track impact parameters, transverse and longitudinal, in cm. Only
                      # charged particles carry a track, so these are zero for neutrals in
                      # our schema and absent from the fullsim neutral collection; mask
                      # on 'charge' before using them.
                      'd0val', 'dzval', 'd0err', 'dzerr']


def _treepaths(files, treename):
    '''The 'file:tree' paths uproot wants, for a list of files.'''
    return ['{}:{}'.format(f, treename) for f in files]


def _keys_of(file, treename):
    '''The set of branch names in one file.'''
    with uproot.open('{}:{}'.format(file, treename)) as t:
        return set(t.keys())


# How many files _read_branches() reads in parallel. Pulling a few flat branches out of
# these inputs is almost pure I/O latency rather than bandwidth or CPU, and uproot
# releases the GIL while reading, so overlapping whole files across threads turns that
# latency into throughput.
READ_WORKERS = int(os.environ.get('NTUPLE_IO_WORKERS', '8'))


def _read_branches(files, branches, treename, workers=None):
    '''uproot.concatenate(files, filter_name=branches), reading the files in parallel.

    Returns {branch: numpy array} with the files' entries in the same order as `files`,
    which callers rely on to keep separate reads of one file list aligned element-wise.
    '''
    branches = list(branches)
    workers = READ_WORKERS if workers is None else workers

    def read_one(f):
        '''Read the requested branches out of one file.'''
        with uproot.open('{}:{}'.format(f, treename)) as t:
            return t.arrays(branches, library='np')

    if len(files) == 1 or workers <= 1:
        parts = [read_one(f) for f in files]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(workers, len(files))) as ex:
            parts = list(ex.map(read_one, files))
    return {b: np.concatenate([part[b] for part in parts]) for b in branches}


def detect_schema(files, treename='tree'):
    '''Return 'ours' or 'fullsim', from the first file's branch list.

    See the module docstring for the marker branch that identifies each.
    '''
    keys = _keys_of(files[0], treename)
    if OURS_MARKER in keys:
        return 'ours'
    if FULLSIM_MARKER in keys:
        return 'fullsim'
    raise ValueError('{}: neither {!r} (ours) nor {!r} (fullsim) found - not a recognized ntuple schema'.format(
        files[0], OURS_MARKER, FULLSIM_MARKER))


# The fullsim branch backing each PARTICLE_SUFFIXES entry, per collection. An entry is
# None where a collection structurally cannot hold that property: the all-neutral
# npfcand_* has no charge or lepton flags, the all-charged cpfcandlt_* has no photon or
# neutral-hadron flags. 'px' deliberately has both, so it can always serve as the
# jagged-length reference for zero-filling a side that lacks a requested suffix.
FULLSIM_OFFLINE_FIELD = {
    'px':               ('cpfcandlt_px', 'npfcand_px'),
    'py':               ('cpfcandlt_py', 'npfcand_py'),
    'energy':           ('cpfcandlt_energy', 'npfcand_energy'),
    'charge':           ('cpfcandlt_charge', None),
    'isElectron':       ('cpfcandlt_isEl', None),
    'isMuon':           ('cpfcandlt_isMu', None),
    'isChargedHadron':  ('cpfcandlt_isChargedHad', None),
    'isPhoton':         (None, 'npfcand_isGamma'),
    'isNeutralHadron':  (None, 'npfcand_isNeutralHad'),
    # The reference calls these dxy/dz, and d0 is dxy. A neutral candidate has no
    # track, so the neutral half is zero-filled, which is what our schema stores
    # there anyway.
    'd0val':            ('cpfcandlt_dxy', None),
    'dzval':            ('cpfcandlt_dz', None),
    # The reference stores a precomputed significance, not the error itself, so
    # there is nothing to map these onto. Zero-filled, which callers must read as
    # "no error available" rather than "the error is zero".
    'd0err':            (None, None),
    'dzerr':            (None, None),
}
FULLSIM_HLT_FIELD = {
    'px': 'scoutpfcand_px', 'py': 'scoutpfcand_py', 'charge': 'scoutpfcand_charge',
    'energy': 'scoutpfcand_energy', 'isElectron': 'scoutpfcand_isEl', 'isMuon': 'scoutpfcand_isMu',
    'isPhoton': 'scoutpfcand_isGamma', 'isChargedHadron': 'scoutpfcand_isChargedHad',
    'isNeutralHadron': 'scoutpfcand_isNeutralHad',
    'd0val': 'scoutpfcand_dxy', 'dzval': 'scoutpfcand_dz',
    'd0err': None, 'dzerr': None,   # see FULLSIM_OFFLINE_FIELD
}


def load_particles(files, suffixes=None, treename='tree'):
    '''Read per-particle content for either schema.

    Returns 'jet_pt' and 'part_<suffix>' for every suffix in `suffixes`, each a per-jet
    jagged array. Whenever an HLT side is present at all - always for fullsim, only for a
    paired "ours" production - also returns 'hlt_matched', 'hlt_jet_pt' and
    'hlt_part_<suffix>'. Callers that also handle offline-only input should test for
    'hlt_matched' rather than assume it.

    `suffixes` restricts which per-particle fields are read, and is the dominant cost of
    this function, so pass only what is needed. 'px' is always read on every side, as the
    minimal structural reference for zero-filling a side that lacks a requested suffix, and
    is always returned alongside what was asked for.
    '''
    all_suffixes = PARTICLE_SUFFIXES
    suffixes = all_suffixes if suffixes is None else list(suffixes)
    unknown = [s for s in suffixes if s not in all_suffixes]
    if unknown:
        raise ValueError('unknown suffix(es) {} - expected a subset of {}'.format(unknown, all_suffixes))
    read_suffixes = sorted(set(suffixes) | {'px'})

    schema = detect_schema(files, treename)
    paths = _treepaths(files, treename)

    if schema == 'ours':
        has_hlt = 'hlt_matched' in _keys_of(files[0], treename)
        branches = ['jet_pt'] + ['part_' + s for s in read_suffixes]
        if has_hlt:
            branches += ['hlt_matched', 'hlt_jet_pt'] + ['hlt_part_' + s for s in read_suffixes]
        arrays = uproot.concatenate(paths, filter_name=branches, library='ak')
        return {b: arrays[b] for b in branches}

    # fullsim: the offline side is cpfcandlt_* and npfcand_* concatenated per jet into
    # one collection matching our part_* layout, and the HLT side is scoutpfcand_*
    # renamed onto our hlt_part_* names, already combined. Only the branches backing
    # `read_suffixes` are read. A suffix missing from one collection is zero-filled
    # through the 'px' structural reference, which is the value it would genuinely
    # hold for a particle of that type.
    charged_branches = sorted({FULLSIM_OFFLINE_FIELD[s][0] for s in read_suffixes if FULLSIM_OFFLINE_FIELD[s][0]})
    neutral_branches = sorted({FULLSIM_OFFLINE_FIELD[s][1] for s in read_suffixes if FULLSIM_OFFLINE_FIELD[s][1]})
    hlt_branches = sorted({FULLSIM_HLT_FIELD[s] for s in read_suffixes if FULLSIM_HLT_FIELD[s]})
    raw = ['fj_pt', 'scoutfj_pt'] + charged_branches + neutral_branches + hlt_branches
    a = uproot.concatenate(paths, filter_name=raw, library='ak')
    njets = len(a['fj_pt'])
    zeros_c = ak.zeros_like(a['cpfcandlt_px'])
    zeros_n = ak.zeros_like(a['npfcand_px'])

    out = {
        'jet_pt': a['fj_pt'],
        'hlt_jet_pt': a['scoutfj_pt'],
        # every fullsim row is already a matched pair, by construction
        'hlt_matched': np.ones(njets, dtype=bool),
    }
    for suffix in read_suffixes:
        charged_branch, neutral_branch = FULLSIM_OFFLINE_FIELD[suffix]
        charged_part = a[charged_branch] if charged_branch else zeros_c
        neutral_part = a[neutral_branch] if neutral_branch else zeros_n
        out['part_' + suffix] = ak.concatenate([charged_part, neutral_part], axis=1)
        hlt_branch = FULLSIM_HLT_FIELD[suffix]
        out['hlt_part_' + suffix] = a[hlt_branch] if hlt_branch \
            else ak.zeros_like(a['scoutpfcand_px'])

    return out


def load_nparticles(files, treename='tree'):
    '''Read only how many particles each jet has, for either schema.

    No per-particle content is read, just enough structure to count. Returns
    {'jet_nparticles': array} plus 'hlt_jet_nparticles' and 'hlt_matched' when an HLT side
    is present. An unmatched row's hlt_jet_nparticles is 0 because its hlt_part_* vectors
    are empty, which is not the same as HLT having reconstructed nothing, so callers
    wanting the HLT distribution should mask by 'hlt_matched' first.

    "ours" stores this as a precomputed flat branch on both sides and is read directly.
    fullsim has none, so one small branch per particle collection is read and used only for
    its jagged length. For fullsim 'hlt_matched' is trivially all True, returned anyway so
    callers need no schema-specific branch.
    '''
    schema = detect_schema(files, treename)
    paths = _treepaths(files, treename)

    if schema == 'ours':
        has_hlt = 'hlt_matched' in _keys_of(files[0], treename)
        branches = ['jet_nparticles'] + (['hlt_jet_nparticles', 'hlt_matched'] if has_hlt else [])
        arrays = uproot.concatenate(paths, filter_name=branches, library='np')
        return {b: arrays[b] for b in branches}

    raw = ['cpfcandlt_charge', 'npfcand_isGamma', 'scoutpfcand_charge']
    a = uproot.concatenate(paths, filter_name=raw, library='ak')
    offline_n = ak.num(a['cpfcandlt_charge'], axis=1) + ak.num(a['npfcand_isGamma'], axis=1)
    hlt_n = ak.num(a['scoutpfcand_charge'], axis=1)
    return {'jet_nparticles': ak.to_numpy(offline_n), 'hlt_jet_nparticles': ak.to_numpy(hlt_n),
            'hlt_matched': np.ones(len(offline_n), dtype=bool)}


# Per-jet quantities load_jet_kinematics() normalizes onto jet_<q>/hlt_jet_<q> for
# both schemas. Only quantities both schemas carry on both sides are listed, so
# anything loaded through here is directly comparable; 'mass' and 'tau4' are absent
# because each exists in only one of the two.
# The branch names are regular on both sides, so no per-field map is needed here,
# unlike the per-particle tables above.
JET_QUANTITIES = ['pt', 'eta', 'phi', 'energy', 'sdmass', 'tau1', 'tau2', 'tau3']


def load_jet_kinematics(files, quantities=('pt', 'eta'), treename='tree'):
    '''Read per-jet quantities for either schema.

    Only the flat scalar branches asked for are touched, so this is cheaper even than
    load_nparticles(). Returns 'jet_<q>' for every q in `quantities`, plus 'hlt_jet_<q>'
    and 'hlt_matched' when an HLT side is present; for fullsim 'hlt_matched' is trivially
    all True.

    An unmatched "ours" row carries hlt_jet_<q> = -999 sentinels, not a physical value, so
    callers must mask by 'hlt_matched' before histogramming the HLT side.
    '''
    unknown = [q for q in quantities if q not in JET_QUANTITIES]
    if unknown:
        raise ValueError('unsupported jet quantity/-ies {} - available on both schemas: {}'.format(
            unknown, ', '.join(JET_QUANTITIES)))
    schema = detect_schema(files, treename)
    paths = _treepaths(files, treename)

    if schema == 'ours':
        has_hlt = 'hlt_matched' in _keys_of(files[0], treename)
        branches = ['jet_' + q for q in quantities]
        if has_hlt:
            branches += ['hlt_matched'] + ['hlt_jet_' + q for q in quantities]
        return _read_branches(files, branches, treename)

    raw = ['fj_' + q for q in quantities] + ['scoutfj_' + q for q in quantities]
    a = _read_branches(files, raw, treename)
    out = {}
    for q in quantities:
        out['jet_' + q] = a['fj_' + q]
        out['hlt_jet_' + q] = a['scoutfj_' + q]
    out['hlt_matched'] = np.ones(len(a['fj_' + quantities[0]]), dtype=bool)
    return out


def jet_selection_mask(files, min_jet_pt=None, max_jet_eta=None, treename='tree'):
    '''Boolean per-row mask for an extra cut on the offline jet, or None if no bound is given.

    The samples compared here do not share one selection: the reference dataset cuts at
    pT > 200 GeV and |eta| < 2.4, our delphes productions are effectively cut at 200 GeV by
    the cards themselves, and some older fullsim productions reach down to 120 GeV. That
    extra band is almost entirely QCD-labelled, so comparing across the mismatch skews
    anything split by jet class; this makes the samples like for like.

    Only the branches the bounds need are read, and the rows line up with every other
    loader's for the same file list, so the result can mask their output directly. Always
    the offline jet, since that is how each sample defines its own selection.
    '''
    if min_jet_pt is None and max_jet_eta is None:
        return None
    quantities = ((['pt'] if min_jet_pt is not None else [])
                  + (['eta'] if max_jet_eta is not None else []))
    d = load_jet_kinematics(files, quantities=quantities, treename=treename)
    keep = np.ones(len(np.asarray(d['jet_' + quantities[0]])), dtype=bool)
    if min_jet_pt is not None:
        keep &= np.asarray(d['jet_pt']) > min_jet_pt
    if max_jet_eta is not None:
        keep &= np.abs(np.asarray(d['jet_eta'])) < max_jet_eta
    return keep


def describe_jet_selection(min_jet_pt=None, max_jet_eta=None):
    '''Short human-readable form of a jet_selection_mask() selection, for the log line
    scripts print when they apply one.
    '''
    parts = []
    if min_jet_pt is not None:
        parts.append('pT > {:g} GeV'.format(min_jet_pt))
    if max_jet_eta is not None:
        parts.append('|eta| < {:g}'.format(max_jet_eta))
    return ' and '.join(parts) if parts else 'none'


def load_label_names(header_path=DEFAULT_LABEL_HEADER):
    '''Return FatJetMatching.h's labels_ list, in order, so labels_[i] is what a jet_label
    value of i means.

    Parsed straight out of the header rather than duplicated here, which would silently
    drift out of sync. Covers both the v2 X_*/X_YY_*/QCD_* scheme and the v1 labels
    appended after it. Only meaningful for the "ours" schema: fullsim's fj_label indexes a
    different list, which is not reproduced here.
    '''
    with open(header_path) as f:
        text = f.read()
    anchor = text.index('labels_{')
    start = text.index('{', anchor)
    depth = 0
    end = None
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        raise ValueError('{}: could not find the closing brace of labels_{{...}}'.format(header_path))
    block = re.sub(r'//.*', '', text[start + 1:end])  # strip line comments before pulling out strings
    labels = re.findall(r'"([^"]*)"', block)
    if not labels:
        raise ValueError('{}: parsed labels_{{...}} but found no quoted label strings inside it'.format(header_path))
    return labels


def is_qcd_label(name):
    '''True for a QCD-fallback label. Every one is named QCD_*, and no signal label is.
    "ours" schema only.
    '''
    return name.startswith('QCD_')


# Coarse cross-schema categories. The fine-grained label names do not correspond one
# to one between our scheme and the upstream fj_label list, but these buckets, built
# from each schema's own category flags and label prefixes, match well enough to
# compare jet counts and composition directly. Our X_* two-prong labels are the same
# physics category as fullsim's fj_isH2p: one exotic resonance decaying to two
# partons, leptons or taus.
CATEGORY_NAMES = ['Top', 'W', 'Z', 'H2p', 'HWW', 'HZZ', 'QCD', 'other']

FULLSIM_CATEGORY_FLAGS = ['fj_isTop', 'fj_isW', 'fj_isZ', 'fj_isH2p', 'fj_isHWW', 'fj_isHZZ', 'fj_isQCD']


def classify_ours_label(name):
    '''The coarse category (one of CATEGORY_NAMES) for one of our own label names.

    The counterpart to fullsim's own boolean category flags; see CATEGORY_NAMES for why the
    mapping is deliberately coarse.
    '''
    if name.startswith('QCD_'):
        return 'QCD'
    if name.startswith('Top_'):
        return 'Top'
    if name.startswith('W_'):
        return 'W'
    if name.startswith('Z_'):
        return 'Z'
    if name in ('H_ww4q', 'H_ww2q1l'):
        return 'HWW'
    if name.startswith('H_') or (name.startswith('X_') and not name.startswith('X_YY_')):
        return 'H2p'
    return 'other'


def load_fullsim_categories(files, treename='tree'):
    '''fullsim counterpart to classify_ours_label().

    Returns (categories, njets), with one of CATEGORY_NAMES per jet, read off fullsim's own
    boolean category flags with a numpy select rather than a per-jet loop.
    '''
    paths = _treepaths(files, treename)
    a = uproot.concatenate(paths, filter_name=FULLSIM_CATEGORY_FLAGS, library='np')
    njets = len(a[FULLSIM_CATEGORY_FLAGS[0]])
    cats = np.full(njets, 'other', dtype=object)
    for name, flag in zip(CATEGORY_NAMES[:-1], FULLSIM_CATEGORY_FLAGS):
        cats[a[flag].astype(bool)] = name
    return cats, njets


# The upstream per-category sub-label components, transcribed from DNNTuples'
# FatJetInfoFiller.h. The H2p and QCD lists are checked against this dataset's own
# generator-level branches, so their order is known to be right. Top/W/Z come from the
# same source but are not independently verified, since neither sample ever sets those
# flags; a mismatch there falls back to a numeric suffix rather than printing a wrong
# name.
#
# HWW/HZZ are deliberately left out: upstream pushes three differently-prefixed copies
# of each onto the list, and with no such jets in either sample to pin down which copy
# a value falls in, a guess risks a confidently wrong name. Those fall back to a
# numeric suffix too.
FULLSIM_SUBLABELS = {
    'Top': ['bWcs', 'bWqq', 'bWc', 'bWs', 'bWq', 'bWev', 'bWmv', 'bWtauev', 'bWtaumv', 'bWtauhv',
            'Wcs', 'Wqq', 'Wev', 'Wmv', 'Wtauev', 'Wtaumv', 'Wtauhv'],
    'W':   ['cs', 'qq', 'ev', 'mv', 'tauev', 'taumv', 'tauhv'],
    'Z':   ['bb', 'cc', 'ss', 'qq'],
    'H2p': ['bb', 'cc', 'ss', 'qq', 'bc', 'bs', 'cs', 'gg', 'ee', 'mm',
            'tauhtaue', 'tauhtaum', 'tauhtauh'],
    'QCD': ['bb', 'cc', 'b', 'c', 'others'],
}
FULLSIM_SUBLABEL_PREFIX = {'Top': 'Top_', 'W': 'W_', 'Z': 'Z_', 'H2p': 'H_', 'QCD': 'QCD_'}


def load_fullsim_raw_labels(files, treename='tree'):
    '''Read fullsim's native fj_label together with its boolean category flags.

    Returns (values, category_flags, njets). Both are needed to name a value, since
    fj_label alone does not say which category's sub-list it indexes into. A given value is
    consistently one category across the whole dataset, so a caller may combine per-file
    observations to recover the true per-value category.
    '''
    a = _read_branches(files, ['fj_label'] + FULLSIM_CATEGORY_FLAGS, treename)
    category_flags = {name: a[flag].astype(bool) for name, flag in zip(CATEGORY_NAMES[:-1], FULLSIM_CATEGORY_FLAGS)}
    return a['fj_label'], category_flags, len(a['fj_label'])


def resolve_fullsim_label_names(value_to_category):
    '''Turn {label_value: category_name} into {label_value: display_name}.

    The caller builds the input from load_fullsim_raw_labels()'s category flags, aggregated
    over every file read. A fine-grained name is resolved through FULLSIM_SUBLABELS where
    possible, indexed from that category's own observed minimum value rather than a
    hardcoded offset, so it does not depend on where a category starts in the upstream
    list. Falls back to "<category>_fj_label=<value>" where no sub-name can be resolved,
    and to "fj_label=<value>" for a value with no known category.
    '''
    by_category = {}
    for value, category in value_to_category.items():
        by_category.setdefault(category, []).append(value)

    names = {}
    for category, values in by_category.items():
        sublabels = FULLSIM_SUBLABELS.get(category)
        prefix = FULLSIM_SUBLABEL_PREFIX.get(category, category + '_')
        base = min(values)
        for value in values:
            idx = value - base
            if sublabels is not None and 0 <= idx < len(sublabels):
                names[value] = prefix + sublabels[idx]
            else:
                names[value] = '{}_fj_label={}'.format(category, value)
    return names


# Generous upper bound for a raw fj_label value. It only has to exceed whatever the
# upstream label list goes up to; a value above it still gets the same out-of-range
# warning as in the "ours" path rather than breaking silently, so this is a safety
# margin, not something that must be exact.
FULLSIM_RAW_LABEL_CAP = 1000
