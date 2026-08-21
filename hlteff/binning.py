#!/usr/bin/env python3

'''
Shared (pT, |eta|) binning used across the hlteff pipeline: derive_curves.py
fills these bins from data, generate_hlt_card.py evaluates the offline
formula and writes the new HLT formula on exactly the same grid. Defining
the grid once here (rather than duplicating edges in each script) is what
keeps the two stages consistent with each other.

PT_EDGES is log-ish spaced and deliberately fine between 0.1-3 GeV, since
that's the region where the offline/HLT tracking-efficiency turn-on curve
actually lives (see README) - coarser bins there would wash out the cliff.
ETA_EDGES matches the barrel/endcap split already used throughout the
existing offline Delphes card (delphes_cards/delphes_card_CMS_JetClassII_onlyFatJet.tcl),
so multiplying a data-driven ratio onto the offline formula bin-by-bin is
well-defined (no interpolation across a differently-binned eta axis needed).
'''

PT_EDGES = [
    0.1, 0.2, 0.35, 0.5, 0.7, 0.9, 1.2, 1.6, 2.2, 3.0, 4.5,
    7.0, 10.0, 16.0, 25.0, 40.0, 65.0, 100.0, 160.0, 250.0,
    400.0, 650.0, 1000.0, 2000.0,
]

# matches the offline card's own |eta| <= 1.5 (barrel) / 1.5 < |eta| <= 2.5
# (endcap) split; particles beyond 2.5 are cut to zero efficiency there too
# and are not binned here.
ETA_EDGES = [0.0, 1.5, 2.5]


def n_pt_bins():
    return len(PT_EDGES) - 1


def n_eta_bins():
    return len(ETA_EDGES) - 1


def pt_bin_index(pt):
    '''Return the PT_EDGES bin index for pt, or None if out of range.'''
    if pt < PT_EDGES[0] or pt >= PT_EDGES[-1]:
        return None
    lo, hi = 0, len(PT_EDGES) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if pt < PT_EDGES[mid]:
            hi = mid
        else:
            lo = mid
    return lo


def eta_bin_index(abs_eta):
    '''Return the ETA_EDGES bin index for |eta|, or None if out of range.'''
    for i in range(len(ETA_EDGES) - 1):
        if ETA_EDGES[i] <= abs_eta < ETA_EDGES[i + 1]:
            return i
    return None


def pt_bin_center(i):
    ### geometric mean of the bin edges, appropriate for a log-spaced axis
    return (PT_EDGES[i] * PT_EDGES[i + 1]) ** 0.5


def eta_bin_center(i):
    return 0.5 * (ETA_EDGES[i] + ETA_EDGES[i + 1])
