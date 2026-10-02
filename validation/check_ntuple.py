#!/usr/bin/env python3

'''
Sanity-check a production ntuple, from either backend (delphes or fullsim).

Checks, in this order (anything that fails is printed as FAIL and makes the
script exit nonzero; "nothing immediately suspicious" means an all-PASS run):

 1. the branch set is exactly the expected schema (the paired offline+HLT one of
    delphes_analyzers/makeNtuplesPaired.C and
    fullsim_analyzers/makeNtuplesFullSim.cc), with the optional
    genpart_*/genjet_*/aux_genpart_* groups allowed but not required;
 2. there is at least one entry, and no NaN/inf anywhere;
 3. per-jet vector lengths agree with jet_nparticles (and hlt_part_* with
    hlt_jet_nparticles) - the most likely symptom of a filling bug;
 4. physical ranges: pT > 0, |eta| within the selection, jet_energy >= jet_pt,
    0 <= tau_{n+1} <= tau_n, sdmass between 0 and the jet mass scale, charges in
    {-1,0,1}, particle type flags mutually exclusive and exhaustive;
 5. hlt_matched consistency: the hlt_* scalars are the -999 sentinel and the
    hlt_part_* vectors empty exactly when hlt_matched is false;
 6. the impact parameters are in the units this repo writes (mm, see
    delphes_cards/KNOWN_ISSUES.md): flagged if the median |d0| of charged
    constituents is outside a generous 1e-3 .. 1 mm window, which is what would
    happen if a backend ever wrote cm by mistake.

It also prints a short summary table (per-jet multiplicities, labels, HLT/offline
ratios) which is what you actually look at to judge whether a new production is
reasonable.

Usage:
  python validation/check_ntuple.py NTUPLE [NTUPLE ...] [--label-names]
'''

import os
import sys
import glob
import argparse
import numpy as np
import uproot

PART_BRANCHES = ['px', 'py', 'pz', 'energy', 'deta', 'dphi', 'd0val', 'd0err', 'dzval', 'dzerr',
                 'charge', 'isElectron', 'isMuon', 'isPhoton', 'isChargedHadron', 'isNeutralHadron']
JET_BRANCHES = ['pt', 'eta', 'phi', 'energy', 'sdmass', 'nparticles', 'tau1', 'tau2', 'tau3', 'tau4']

EXPECTED = (['part_' + b for b in PART_BRANCHES]
            + ['jet_' + b for b in JET_BRANCHES] + ['jet_label']
            + ['hlt_matched']
            + ['hlt_jet_' + b for b in JET_BRANCHES] + ['hlt_jet_dr_offline']
            + ['hlt_part_' + b for b in PART_BRANCHES])
OPTIONAL_PREFIXES = ('genpart_', 'genjet_', 'aux_genpart_')

SENTINEL = -999


class Checker:
    def __init__(self):
        self.failed = 0

    def check(self, ok, what, detail=''):
        print('  {:4s} {}{}'.format('PASS' if ok else 'FAIL', what,
                                    '' if ok else ' -- ' + detail))
        if not ok:
            self.failed += 1
        return ok


def flat(jagged):
    '''Concatenate a jagged (per-jet) array into one flat array.'''
    if len(jagged) == 0:
        return np.array([])
    return np.concatenate([np.asarray(x) for x in jagged]) if len(jagged) else np.array([])


def check_file(path, c, show_label_names=False):
    print('\n=== {} ==='.format(path))
    t = uproot.open(path)['tree']
    keys = list(t.keys())
    n = t.num_entries
    print('  entries (jets): {}, branches: {}'.format(n, len(keys)))

    missing = [b for b in EXPECTED if b not in keys]
    unexpected = [b for b in keys if b not in EXPECTED and not b.startswith(OPTIONAL_PREFIXES)]
    c.check(not missing, 'all expected branches present', 'missing: {}'.format(missing))
    c.check(not unexpected, 'no unexpected branches', 'unexpected: {}'.format(unexpected))
    c.check(n > 0, 'at least one jet')
    if n == 0 or missing:
        return

    a = t.arrays(library='np')

    # --- no NaN/inf ---
    bad = []
    for k in keys:
        v = a[k]
        f = flat(v) if v.dtype == object else np.asarray(v)
        if f.dtype.kind == 'f' and f.size and not np.all(np.isfinite(f)):
            bad.append(k)
    c.check(not bad, 'no NaN/inf values', 'in: {}'.format(bad))

    # --- vector lengths vs nparticles ---
    for prefix, count in (('part_', 'jet_nparticles'), ('hlt_part_', 'hlt_jet_nparticles')):
        lens = {b: np.array([len(x) for x in a[prefix + b]]) for b in PART_BRANCHES}
        nref = np.asarray(a[count])
        mismatched = [b for b, l in lens.items() if not np.array_equal(l, nref)]
        c.check(not mismatched, '{}* lengths all equal {}'.format(prefix, count),
                'mismatched: {}'.format(mismatched))

    # --- physical ranges ---
    c.check(np.all(a['jet_pt'] > 0), 'jet_pt > 0')
    c.check(np.all(np.abs(a['jet_eta']) < 5), '|jet_eta| < 5')
    c.check(np.all(a['jet_energy'] >= a['jet_pt'] - 1e-3), 'jet_energy >= jet_pt')
    sd = np.asarray(a['jet_sdmass'])
    c.check(np.all((sd >= 0) & (sd < a['jet_energy'])), '0 <= jet_sdmass < jet_energy')
    for lo, hi in (('jet_tau1', 'jet_tau2'), ('jet_tau2', 'jet_tau3'), ('jet_tau3', 'jet_tau4')):
        # N-subjettiness is non-increasing in N by construction
        c.check(np.all(np.asarray(a[hi]) <= np.asarray(a[lo]) + 1e-5), '{} <= {}'.format(hi, lo))
    q = flat(a['part_charge'])
    c.check(np.all(np.isin(q, (-1, 0, 1))), 'part_charge in {-1,0,1}',
            'other values: {}'.format(np.unique(q)[:10]))

    types = np.stack([flat(a['part_is' + x]).astype(int) for x in
                      ('Electron', 'Muon', 'Photon', 'ChargedHadron', 'NeutralHadron')])
    tsum = types.sum(axis=0)
    c.check(np.all(tsum == 1), 'each constituent has exactly one type flag',
            'counts of flags set: {}'.format(dict(zip(*np.unique(tsum, return_counts=True)))))

    # --- hlt_matched consistency ---
    m = np.asarray(a['hlt_matched']).astype(bool)
    nmatch = int(m.sum())
    print('  hlt_matched: {}/{} ({:.0f}%)'.format(nmatch, n, 100. * nmatch / n))
    if nmatch < n:
        um = ~m
        c.check(np.all(np.asarray(a['hlt_jet_pt'])[um] == SENTINEL),
                'hlt_jet_pt is the {} sentinel when unmatched'.format(SENTINEL))
        c.check(all(len(x) == 0 for x in a['hlt_part_px'][um]),
                'hlt_part_* empty when unmatched')
    if nmatch:
        c.check(np.all(np.asarray(a['hlt_jet_pt'])[m] > 0), 'hlt_jet_pt > 0 when matched')
        c.check(np.all(np.asarray(a['hlt_jet_dr_offline'])[m] >= 0),
                'hlt_jet_dr_offline >= 0 when matched')

    # --- impact-parameter units ---
    for prefix in ('part_', 'hlt_part_'):
        qq = flat(a[prefix + 'charge'])
        d0 = flat(a[prefix + 'd0val'])
        if qq.size == 0 or not np.any(qq != 0):
            continue
        med = float(np.median(np.abs(d0[qq != 0])))
        c.check(1e-3 < med < 1.0,
                '{}d0val median |d0| = {:.4f} is in the mm range'.format(prefix, med),
                'expected ~0.01 mm; cm instead of mm would give ~0.001')

    # --- summary ---
    print('  --- summary ---')
    npart = np.asarray(a['jet_nparticles'])
    hnpart = np.asarray(a['hlt_jet_nparticles'])
    print('    jet pT        : median {:7.1f}  range {:.0f} - {:.0f}'.format(
        np.median(a['jet_pt']), np.min(a['jet_pt']), np.max(a['jet_pt'])))
    print('    constituents  : offline {:.1f}, HLT {:.1f} (matched jets)'.format(
        npart.mean(), hnpart[m].mean() if nmatch else float('nan')))
    for name, x in (('charged hadrons', 'isChargedHadron'), ('photons', 'isPhoton'),
                    ('neutral hadrons', 'isNeutralHadron')):
        off = np.array([np.sum(x_) for x_ in a['part_' + x]]).mean()
        hlt = np.array([np.sum(x_) for x_ in a['hlt_part_' + x]])[m]
        print('    {:15s}: offline {:5.1f}, HLT {:5.1f}'.format(
            name, off, hlt.mean() if nmatch else float('nan')))
    if nmatch:
        r = np.asarray(a['hlt_jet_pt'])[m] / np.asarray(a['jet_pt'])[m]
        print('    HLT/offline jet pT: median {:.3f}'.format(np.median(r)))
    labels, counts = np.unique(np.asarray(a['jet_label']), return_counts=True)
    if show_label_names:
        names = label_names()
        shown = ['{}={}'.format(names[l] if l < len(names) else l, cnt)
                 for l, cnt in zip(labels, counts)]
    else:
        shown = ['{}={}'.format(l, cnt) for l, cnt in zip(labels, counts)]
    print('    jet_label     : {}'.format(', '.join(shown)))


def label_names():
    '''The labels_ list of delphes_analyzers/FatJetMatching.h, in order.'''
    import re
    here = os.path.dirname(os.path.abspath(__file__))
    src = open(os.path.join(here, '..', 'delphes_analyzers', 'FatJetMatching.h')).read()
    m = re.search(r'std::vector<std::string> labels_\{(.*?)\};', src, re.S)
    return re.findall(r'"([^"]+)"', m.group(1)) if m else []


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('ntuples', nargs='+', help='ntuple files (globs allowed)')
    parser.add_argument('--label-names', action='store_true',
        help='print jet_label as names (read from FatJetMatching.h) instead of indices')
    args = parser.parse_args()

    paths = []
    for p in args.ntuples:
        paths.extend(sorted(glob.glob(p)) or [p])

    c = Checker()
    for p in paths:
        check_file(p, c, args.label_names)
    print('\n{} check(s) failed across {} file(s)'.format(c.failed, len(paths)))
    sys.exit(1 if c.failed else 0)


if __name__ == '__main__':
    main()
