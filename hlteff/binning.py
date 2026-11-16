#!/usr/bin/env python3

'''Shared (pT, |eta|) binning for the hlteff pipeline.

derive_curves.py fills these bins from data and generate_hlt_card.py evaluates the
offline formula and writes the new HLT formula on the same grid, so defining the grid
once here is what keeps the two stages consistent.

PT_EDGES is roughly log-spaced and deliberately fine below a few GeV, where the
tracking-efficiency turn-on lives; coarser bins there would wash the edge out.
ETA_EDGES matches the barrel/endcap split the offline Delphes card already uses, so a
data-driven ratio can be multiplied onto the offline formula bin by bin without
interpolating across a different eta axis.
'''

PT_EDGES = [
    0.1, 0.2, 0.35, 0.5, 0.7, 0.9, 1.2, 1.6, 2.2, 3.0, 4.5,
    7.0, 10.0, 16.0, 25.0, 40.0, 65.0, 100.0, 160.0, 250.0,
    400.0, 650.0, 1000.0, 2000.0,
]

# Matches the offline card's own barrel/endcap split. Particles beyond the last edge
# are cut to zero efficiency there too, and are not binned here.
ETA_EDGES = [0.0, 1.5, 2.5]

# Separate, coarser binning for whole-jet quantities such as the jet energy scale.
# Real jets here start at 200 GeV, the ntuple's own baseline selection, so PT_EDGES'
# sub-GeV bins would be empty. Matches how jet pT is sliced elsewhere in the repo.
JET_PT_EDGES = [200.0, 250.0, 300.0, 400.0, 500.0, 650.0, 800.0, 1000.0, 1500.0, 2000.0, 3000.0, 5000.0]


def n_pt_bins():
    '''Number of pT bins.'''
    return len(PT_EDGES) - 1


def n_eta_bins():
    '''Number of |eta| bins.'''
    return len(ETA_EDGES) - 1


def n_jet_pt_bins():
    '''Number of whole-jet pT bins.'''
    return len(JET_PT_EDGES) - 1


def jet_pt_bin_index(pt):
    '''The JET_PT_EDGES bin index for pt, or None if out of range.'''
    if pt < JET_PT_EDGES[0] or pt >= JET_PT_EDGES[-1]:
        return None
    lo, hi = 0, len(JET_PT_EDGES) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if pt < JET_PT_EDGES[mid]:
            hi = mid
        else:
            lo = mid
    return lo


def pt_bin_index(pt):
    '''The PT_EDGES bin index for pt, or None if out of range.'''
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
    '''The ETA_EDGES bin index for |eta|, or None if out of range.'''
    for i in range(len(ETA_EDGES) - 1):
        if ETA_EDGES[i] <= abs_eta < ETA_EDGES[i + 1]:
            return i
    return None


def pt_bin_center(i):

    '''Centre of pT bin i, as the geometric mean of its edges, which suits a log-spaced axis.
    '''
    return (PT_EDGES[i] * PT_EDGES[i + 1]) ** 0.5


def eta_bin_center(i):
    '''Centre of |eta| bin i.'''
    return 0.5 * (ETA_EDGES[i] + ETA_EDGES[i + 1])
