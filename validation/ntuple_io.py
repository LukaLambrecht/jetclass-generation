#!/usr/bin/env python3

'''
Shared input layer letting the diagnostic/plotting scripts in this
directory and in compare-hlt-to-offline/ read EITHER of two ntuple
schemas transparently, so the same script/command can be pointed at
either one:

  - "ours": produced by this repo's own delphes_analyzers/makeNtuples.C
    (single Delphes card) or makeNtuplesPaired.C (offline+HLT pair) -
    part_*/jet_* for offline, plus hlt_part_*/hlt_jet_*/hlt_matched for
    HLT when the input is a paired production. Identified by the presence
    of a jet_label branch.

  - "fullsim": the real CMS offline+scouting reference dataset this whole
    Delphes pipeline is trying to mimic - see hlteff/README.md's own
    "Data source" section for the full description. Path:
      /eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/
        QCD_PT-mixed_TuneCP5_13p6TeV_pythia8_new/dnnTuples_nanov15_*.root
        H0HpHm_mixed_new/dnnTuples_nanov15_*.root
    One row per (offline, HLT/scouting) jet PAIR, already geometrically
    matched (median dR ~0.005 - see hlteff/README.md) - unlike our own
    single-card output, every row here always has both sides; there is no
    "hlt_matched" concept to speak of, so load_particles() below just
    reports it as always True. Offline particles are split across TWO
    collections (cpfcandlt_* charged incl. recovered lost tracks, npfcand_*
    neutral) instead of our own single combined one; the HLT/scouting side
    (scoutpfcand_*) already IS one combined collection like ours.
    Identified by the presence of an fj_label branch.

Every function below normalizes to OUR OWN naming (part_*/hlt_part_*/
jet_pt/hlt_jet_pt/hlt_matched) regardless of which schema the input
actually is, so callers never need their own if/else on the source - only
classify_ours_label()/FULLSIM_CATEGORY_FLAGS below are schema-specific,
for callers (print_njets.py) that need a coarse, cross-schema-comparable
category rather than particle content.
'''

import os
import re

import awkward as ak
import numpy as np
import uproot

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(THISDIR)
DEFAULT_LABEL_HEADER = os.path.join(REPO_DIR, 'delphes_analyzers', 'FatJetMatching.h')

OURS_MARKER = 'jet_label'
FULLSIM_MARKER = 'fj_label'

# per-particle fields load_particles() normalizes onto part_<suffix>/
# hlt_part_<suffix> for both schemas
PARTICLE_SUFFIXES = ['px', 'py', 'charge', 'energy',
                      'isElectron', 'isMuon', 'isPhoton', 'isChargedHadron', 'isNeutralHadron']


def _treepaths(files, treename):
    return ['{}:{}'.format(f, treename) for f in files]


def _keys_of(file, treename):
    with uproot.open('{}:{}'.format(file, treename)) as t:
        return set(t.keys())


def detect_schema(files, treename='tree'):
    '''Returns 'ours' or 'fullsim', from the first file's own branch list (see module docstring
    for the marker branch each is identified by).'''
    keys = _keys_of(files[0], treename)
    if OURS_MARKER in keys:
        return 'ours'
    if FULLSIM_MARKER in keys:
        return 'fullsim'
    raise ValueError('{}: neither {!r} (ours) nor {!r} (fullsim) found - not a recognized ntuple schema'.format(
        files[0], OURS_MARKER, FULLSIM_MARKER))


# fullsim raw branch(es) backing each PARTICLE_SUFFIXES entry, per collection - see
# load_particles()'s own comment on why some entries are None (a collection that
# structurally can't hold that property at all, e.g. npfcand_* - all-neutral - has no
# charge/isElectron/isMuon/isChargedHadron branch, cpfcandlt_* - all-charged - has no
# isPhoton/isNeutralHadron). 'px' deliberately has both, so it can always serve as the
# minimal structural (jagged-length) reference for zero-filling a side that lacks a
# requested suffix, without reading a whole extra branch just for that.
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
}
FULLSIM_HLT_FIELD = {
    'px': 'scoutpfcand_px', 'py': 'scoutpfcand_py', 'charge': 'scoutpfcand_charge',
    'energy': 'scoutpfcand_energy', 'isElectron': 'scoutpfcand_isEl', 'isMuon': 'scoutpfcand_isMu',
    'isPhoton': 'scoutpfcand_isGamma', 'isChargedHadron': 'scoutpfcand_isChargedHad',
    'isNeutralHadron': 'scoutpfcand_isNeutralHad',
}


def load_particles(files, suffixes=None, treename='tree'):
    '''
    Returns a dict: always 'jet_pt' (offline jet pT) and 'part_<suffix>' for every
    suffix in `suffixes` (a per-jet-jagged awkward array of per-particle values); ALSO
    'hlt_matched', 'hlt_jet_pt' and 'hlt_part_<suffix>' whenever an HLT/scouting side
    is present at all (always true for fullsim; only true for a paired "ours"
    production - see module docstring) - callers that also handle offline-only "ours"
    input should check for 'hlt_matched' in the returned dict rather than assuming
    it's always there.

    `suffixes` (default: all of PARTICLE_SUFFIXES) restricts which per-particle fields
    are actually read - pass only what you need (e.g. skip 'energy' if you're only
    plotting kinematics, or skip 'px'/'py'/'charge' if you only need the type flags):
    this is the dominant cost of this function (jagged per-particle branches are much
    larger than the flat per-jet ones), so trimming it measurably cuts both bytes read
    from EOS and the fullsim path's ak.concatenate work. 'px' is always read regardless
    (on every side/collection) even if not requested, as the minimal structural
    reference for zero-filling a side that structurally lacks a requested suffix (see
    FULLSIM_OFFLINE_FIELD) - it's cheap (a plain float, present everywhere already),
    and always returned in the output dict alongside whatever was actually requested.
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

    # fullsim: offline = cpfcandlt_* (charged) + npfcand_* (neutral) concatenated per
    # jet into one combined collection matching our own part_* layout; HLT =
    # scoutpfcand_* renamed onto our own hlt_part_* names (already one combined
    # collection there, like ours - see module docstring). Only the raw branches
    # actually backing `read_suffixes` are read at all (see FULLSIM_OFFLINE_FIELD/
    # FULLSIM_HLT_FIELD) - a suffix missing from one side's collection (e.g. npfcand_*
    # has no charge/isElectron/isMuon/isChargedHadron; cpfcandlt_* has no isPhoton/
    # isNeutralHadron) is filled with zeros there instead (via the 'px' structural
    # reference), which is exactly the value a genuine part_charge/part_isElectron/etc.
    # would hold for a particle of that type anyway.
    charged_branches = sorted({FULLSIM_OFFLINE_FIELD[s][0] for s in read_suffixes if FULLSIM_OFFLINE_FIELD[s][0]})
    neutral_branches = sorted({FULLSIM_OFFLINE_FIELD[s][1] for s in read_suffixes if FULLSIM_OFFLINE_FIELD[s][1]})
    hlt_branches = sorted({FULLSIM_HLT_FIELD[s] for s in read_suffixes})
    raw = ['fj_pt', 'scoutfj_pt'] + charged_branches + neutral_branches + hlt_branches
    a = uproot.concatenate(paths, filter_name=raw, library='ak')
    njets = len(a['fj_pt'])
    zeros_c = ak.zeros_like(a['cpfcandlt_px'])
    zeros_n = ak.zeros_like(a['npfcand_px'])

    out = {
        'jet_pt': a['fj_pt'],
        'hlt_jet_pt': a['scoutfj_pt'],
        # every fullsim row is already a matched (offline, scouting) pair
        # by construction - see module docstring
        'hlt_matched': np.ones(njets, dtype=bool),
    }
    for suffix in read_suffixes:
        charged_branch, neutral_branch = FULLSIM_OFFLINE_FIELD[suffix]
        charged_part = a[charged_branch] if charged_branch else zeros_c
        neutral_part = a[neutral_branch] if neutral_branch else zeros_n
        out['part_' + suffix] = ak.concatenate([charged_part, neutral_part], axis=1)
        out['hlt_part_' + suffix] = a[FULLSIM_HLT_FIELD[suffix]]

    return out


def load_nparticles(files, treename='tree'):
    '''
    Lightest possible read of "how many particles per jet" for either schema - no
    per-particle CONTENT is read at all (unlike load_particles(), even with a minimal
    `suffixes`), just enough structure to count. Returns {'jet_nparticles': array} and,
    when an HLT/scouting side is present, also 'hlt_jet_nparticles' and 'hlt_matched' -
    an unmatched row's hlt_jet_nparticles is 0 (its hlt_part_* vectors are empty, not
    missing - see load_particles()'s own comment), which is NOT the same thing as "HLT
    genuinely reconstructed 0 particles"; callers wanting the HLT nparticles
    distribution should mask by 'hlt_matched' first (see ../compare-hlt-to-offline/
    plot_nparticles.py) rather than including unmatched rows as zeros.

    "ours" already stores this as a precomputed flat int branch on both sides (see
    makeNtuples.C/makeNtuplesPaired.C) - read directly, no jagged branch touched at all.

    fullsim has no such precomputed branch - reads exactly ONE small branch per
    underlying particle collection (arbitrary, cheap fields, used only for their
    jagged length via ak.num() - never their actual values) instead of
    load_particles()'s full per-particle content. 'hlt_matched' is trivially all True
    (every fullsim row is already a matched pair - see module docstring), returned
    anyway so callers don't need a schema-specific branch here either.
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


def load_label_names(header_path=DEFAULT_LABEL_HEADER):
    '''
    Parse FatJetMatching.h's own `std::vector<std::string> labels_{...}`
    initializer list straight out of the header (rather than hardcoding a
    second copy of ~200 label strings here that could silently drift out
    of sync with it) and return it as an ordered list - labels_[i] is
    exactly what a jet_label value of i means, for both the v2
    X_*/X_YY_*/QCD_* scheme and the v1 Top_*/W_*/Z_*/H_*/QCD_all labels
    appended after it (see FatJetMatching.h's own useV1Labels_/labels_
    comments). Only meaningful for the "ours" schema - fullsim's own
    fj_label uses a completely different (DNNTuples-defined) list, not
    reproduced here - see classify_ours_label()/FULLSIM_CATEGORY_FLAGS for
    the coarse, cross-schema category comparison used instead.
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
    '''Every QCD-fallback label (v2's 27-way flavor split, and v1's single QCD_all
    catch-all) is named QCD_*; every signal label (X_*, X_YY_*, Top_*, W_*, Z_*, H_*)
    is not - see FatJetMatching.h's labels_ vector. "ours" schema only.'''
    return name.startswith('QCD_')


# Coarse, cross-schema category scheme: fine-grained label names don't
# correspond 1:1 between our own v2 X_bb/X_cc/.../QCD_bb/... scheme and
# DNNTuples' own fj_label list (a different, unpublished list we don't
# reproduce here - see load_label_names()'s own docstring), but these 8
# buckets, built from each schema's own boolean category flags/label-name
# prefixes, DO correspond well enough to compare njets/composition across
# both directly: our own v2 X_* 2-prong signal labels are the same physics
# category as fullsim's fj_isH2p flag (both a single exotic resonance
# decaying to 2 partons/leptons/taus - see FatJetMatching.h's labels_ and
# DNNTuples' own isH2p for what each actually covers).
CATEGORY_NAMES = ['Top', 'W', 'Z', 'H2p', 'HWW', 'HZZ', 'QCD', 'other']

FULLSIM_CATEGORY_FLAGS = ['fj_isTop', 'fj_isW', 'fj_isZ', 'fj_isH2p', 'fj_isHWW', 'fj_isHZZ', 'fj_isQCD']


def classify_ours_label(name):
    '''Coarse category (one of CATEGORY_NAMES) for one of our OWN label names (from
    FatJetMatching.h's labels_ vector, see load_label_names()) - the "ours" counterpart
    to fullsim's own boolean category flags (FULLSIM_CATEGORY_FLAGS) - see CATEGORY_NAMES'
    own comment for why this mapping is deliberately coarse, not a fine-grained one.'''
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
    '''fullsim counterpart to classify_ours_label(): returns (categories, njets), categories
    a numpy array of one of CATEGORY_NAMES per jet, read directly off fullsim's own boolean
    category flags (FULLSIM_CATEGORY_FLAGS) - no per-jet Python loop, just a numpy select.'''
    paths = _treepaths(files, treename)
    a = uproot.concatenate(paths, filter_name=FULLSIM_CATEGORY_FLAGS, library='np')
    njets = len(a[FULLSIM_CATEGORY_FLAGS[0]])
    cats = np.full(njets, 'other', dtype=object)
    for name, flag in zip(CATEGORY_NAMES[:-1], FULLSIM_CATEGORY_FLAGS):
        cats[a[flag].astype(bool)] = name
    return cats, njets


# DNNTuples' own per-category sub-label components (dev/AK15Scout branch,
# Ntupler/interface/FatJetInfoFiller.h's labelTop_/labelW_/labelZ_/labelH2p_/
# labelQCD_ member vectors, transcribed from source) - VERIFIED directly against
# this dataset's own generator-level branches for the two categories the two
# samples this pipeline actually uses populate: H2p (cross-checked against
# fj_genpart1_pid/fj_genpart2_pid - the Higgs decay products' own PDG codes -
# label 17 is exactly the bb pairs, 18 exactly cc, ... 29 exactly the
# both-hadronic ditau case, in this list's order) and QCD (cross-checked
# against fj_nbHadrons/fj_ncHadrons - label 309 is exactly nb>=2, 310 exactly
# nb==0 and nc>=2, etc., in this list's order). Top/W/Z are transcribed from
# the same source but NOT independently re-verified this way (neither sample
# ever sets fj_isTop/isW/isZ, so there's nothing to check them against) - a
# mismatch here would just fall back to a plain numeric suffix rather than
# print a silently-wrong name, see resolve_fullsim_label_names().
#
# HWW/HZZ are deliberately NOT included: DNNTuples pushes THREE differently-
# prefixed copies of each onto labels_ (H_WW_*/H_WxWx_*/H_WxWxStar_* and
# H_ZZ_*/H_ZxZx_*/H_ZxZxStar_*), and with no HWW/HZZ-flagged jets in either
# sample to empirically pin down which of the three a given label value falls
# in, guessing would risk a confidently WRONG name - resolve_fullsim_label_names()
# falls back to a plain numeric suffix for those too.
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
    '''
    Read fullsim's own native fj_label directly, alongside its 7 boolean category
    flags (FULLSIM_CATEGORY_FLAGS) - needed to resolve a fine-grained name per value
    (see resolve_fullsim_label_names()), since fj_label alone doesn't say which
    category's sub-list it indexes into. Returns (values, category_flags, njets):
    values is the raw per-jet fj_label array, category_flags is
    {category_name: per-jet boolean array} for each of CATEGORY_NAMES[:-1] - a label
    VALUE is consistently exactly one category across the whole dataset, by
    construction (see FatJetInfoFiller.cc's own label-building code), so a caller
    aggregating over many files can safely combine per-file "this value co-occurred
    with this category" observations (whichever file happens to contain it) to
    recover the true per-value category, without needing DNNTuples' own full label
    list or its exact concatenation order.
    '''
    paths = _treepaths(files, treename)
    a = uproot.concatenate(paths, filter_name=['fj_label'] + FULLSIM_CATEGORY_FLAGS, library='np')
    category_flags = {name: a[flag].astype(bool) for name, flag in zip(CATEGORY_NAMES[:-1], FULLSIM_CATEGORY_FLAGS)}
    return a['fj_label'], category_flags, len(a['fj_label'])


def resolve_fullsim_label_names(value_to_category):
    '''
    Given value_to_category - {label_value: category_name}, one entry per distinct
    raw fj_label value actually observed (built by the caller from
    load_fullsim_raw_labels()'s category_flags, aggregated across every file read -
    see print_njets.py) - return {label_value: display_name}. Resolves a
    fine-grained name via FULLSIM_SUBLABELS wherever possible, indexed from that
    CATEGORY's own empirically-observed minimum label value (not a hardcoded global
    offset) - so this works regardless of where in DNNTuples' own full label list a
    given production actually starts a category, without needing to know that list's
    exact concatenation order at all. Falls back to "<category>_fj_label=<value>"
    for HWW/HZZ or an index past what FULLSIM_SUBLABELS has (see its own docstring
    for why), and "fj_label=<value>" for a value with no known category at all.
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


# Generous upper bound for a raw fj_label value (see load_fullsim_raw_labels()) - every
# value actually observed so far tops out at 313 (the QCD_PT-mixed sample's own QCD_light);
# this just needs to comfortably exceed whatever DNNTuples' own (unpublished) label list
# actually goes up to, with plenty of headroom - callers still get the same out-of-range
# warning/clipping "ours" already has if a value ever exceeds it, rather than silently
# breaking, so this is a safety margin, not something that has to be exactly right.
FULLSIM_RAW_LABEL_CAP = 1000
