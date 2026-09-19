#!/usr/bin/env python3

'''
Derive a multiplicative correction to the HLT card's JetEnergyScalePUPPIAK8
so that OUR HLT/offline AK8 jet-pT ratio matches the one measured in CMS
FullSim (median scoutfj_pt/fj_pt per offline jet (|eta|, pT) bin, the
jetEnergyScale.scout_over_offline_ratio of curves_qcd.json).

Why a separate correction: generate_hlt_card.py builds JetEnergyScalePUPPIAK8
as offline(pt,eta) * FullSim ratio, which assumes our raw HLT jets already
have the same response as our offline jets. That holds for the PUPPI-based
HLT card, but not once the HLT jets are built WITHOUT PUPPI
(--no-puppi): our offline jets lose most of their neutral energy to a
Delphes PUPPI bug (see delphes_cards/KNOWN_ISSUES.md) that the no-PUPPI HLT
jets don't have, so the HLT/offline jet-pT ratio comes out 10-30% high.
This script measures that residual from paired ntuples and stores a
per-HLT-jet-pT-bin factor, which generate_hlt_card.py --jes-correction
multiplies onto the JES table.

Input: paired ntuples (delphes_analyzers/makeNtuplesPaired.C) made with an
HLT card generated WITHOUT --jes-correction but otherwise with the intended
settings (the factors are relative to that card's JES table). Use QCD, and
events independent of the ones used to validate the result.

Method: for each matched jet pair, target HLT pT = offline pT * R_FS(offline
|eta|, pT bin); the factor for an HLT-jet-pT bin (the JES formula is a
function of the HLT jet's own pT) is the median of target / current HLT pT
over the jets in that bin (bins starting below --min-hlt-pt are filled from the
nearest measured bin instead, see its help). |eta|-inclusive (the endcap has few jets); bins
with fewer than --min-jets jets are filled from the nearest valid bin. One
iteration suffices in practice (a second one gave factors within 1-5% of 1).

Note: this matches the MEDIAN ratio per HLT-pT bin; in offline-pT bins a
residual offset can remain where our HLT/offline spread is wider/more skewed
than FullSim's (a scale factor cannot change the spread).

Usage:
  python derive_hlt_jes_correction.py NTUPLE [NTUPLE ...] [--output PATH] [--min-jets N]
'''

import os
import sys
import json
import argparse
from datetime import datetime, timezone

import numpy as np
import uproot

HLTEFF_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HLTEFF_DIR)
from generate_hlt_card import fill_missing


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('ntuples', nargs='+')
    parser.add_argument('--curves', default=os.path.join(HLTEFF_DIR, 'curves_qcd.json'))
    parser.add_argument('--min-jets', type=int, default=50)
    parser.add_argument('--min-hlt-pt', type=float, default=250.0,
        help='HLT-jet-pT bins with a lower edge below this are NOT measured but filled from the nearest measured'
             ' bin: near the offline selection threshold (200 GeV) the offline partner of a low-pT HLT jet is'
             ' biased high (it had to pass 200 GeV), which would bias the factor upward (default: 250)')
    parser.add_argument('--output', default=os.path.join(HLTEFF_DIR, 'jes_correction_nopuppi.json'))
    args = parser.parse_args()

    curves = json.load(open(args.curves))
    eta_edges = curves['binning']['eta_edges']
    jpt = curves['binning']['jet_pt_edges']
    r_fs = curves['jetEnergyScale']['scout_over_offline_ratio']

    off, eta, hlt = [], [], []
    for fn in args.ntuples:
        b = uproot.open(fn)['tree'].arrays(['jet_pt', 'jet_eta', 'hlt_matched', 'hlt_jet_pt'], library='np')
        m = b['hlt_matched'] & (b['hlt_jet_pt'] > 0)
        off.append(b['jet_pt'][m]); eta.append(np.abs(b['jet_eta'][m])); hlt.append(b['hlt_jet_pt'][m])
    off, eta, hlt = np.concatenate(off), np.concatenate(eta), np.concatenate(hlt)
    ie = np.clip(np.digitize(eta, eta_edges) - 1, 0, len(eta_edges) - 2)
    ip = np.clip(np.digitize(off, jpt) - 1, 0, len(jpt) - 2)
    r = np.array([r_fs[e][p] if r_fs[e][p] is not None else 1.0 for e, p in zip(ie, ip)])
    target = off * r

    ih = np.clip(np.digitize(hlt, jpt) - 1, 0, len(jpt) - 2)
    factors, valid, counts = [], [], []
    for i in range(len(jpt) - 1):
        s = ih == i
        ok = bool(s.sum() >= args.min_jets and jpt[i] >= args.min_hlt_pt - 1e-9)
        factors.append(float(np.median(target[s] / hlt[s])) if ok else 1.0)
        valid.append(ok)
        counts.append(int(s.sum()))
    filled, _ = fill_missing(factors, valid)
    for i in range(len(jpt) - 1):
        print('HLT jet pT {:6.0f}-{:<6.0f}: n={:6d}  factor {:.3f}{}'.format(
            jpt[i], jpt[i + 1], counts[i], filled[i], '' if valid[i] else ' (filled from neighbour)'))

    result = {
        'note': ('multiplicative correction to JetEnergyScalePUPPIAK8, per bin of the HLT jet pT '
                 '(|eta|-inclusive), relative to the JES table of the HLT card the input ntuples were '
                 'made with - see derive_hlt_jes_correction.py'),
        'generated_at': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
        'inputs': [os.path.abspath(f) for f in args.ntuples],
        'n_matched_jets': int(len(off)),
        'jet_pt_edges': jpt,
        'factors': filled,
        'n_jets': counts,
        'measured': valid,
    }
    with open(args.output, 'w') as f:
        json.dump(result, f, indent=1)
    print('Wrote', args.output)


if __name__ == '__main__':
    main()
