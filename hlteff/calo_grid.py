#!/usr/bin/env python3

'''
Parse, coarsen, and assign candidates to a SimpleCalorimeter tower grid, as
literally defined in a Delphes .tcl card (the repeated
"set PhiBins {}; for {...} {add PhiBins ...}; <eta block>" groups inside
e.g. the HCal/ECal modules).

Two eta-block styles appear in this repo's cards, both handled here:
  - literal: `foreach eta {v1 v2 ...} {add EtaPhiBins $eta $PhiBins}`
    (all of HCal, and ECal's forward/HF region)
  - arithmetic: `for {set i A} {$i <= B} {incr i} {set eta [expr {EXPR}]
    add EtaPhiBins $eta $PhiBins}` (ECal's barrel and endcap regions, where
    EXPR is e.g. "$i * 0.0174" or "-2.958 + $i * 0.0174")
Both are associated with whichever `set PhiBins {}; for {...} {add PhiBins
...}` block most recently preceded them - matching how Tcl variable scoping
actually behaves here (ECal's two endcap sub-regions share a single
PhiBins definition across two consecutive eta-blocks, for example).

Simplification (documented, not silently assumed): Delphes actually merges
ALL `add EtaPhiBins` calls across every block into one globally eta-sorted
boundary list, so the true tower grid has thin transition bins exactly at
each block's edge (e.g. HCal's barrel/endcap boundary reuses whichever
block registered that specific eta value). This module instead treats each
block as an independent region covering its own [min(eta_edges),
max(eta_edges)] span with its own phi granularity, picking the first
matching region for any eta in more than one (this only affects the very
thin transition slivers). Adequate for scan_calo_granularity.py's aggregate
energy-multiplicity comparison; NOT a bit-exact reproduction of Delphes'
own tower construction - see its module docstring for why that's an
acceptable trade here.
'''

import re
import math

import numpy as np

_PHI_RESET_PAT = re.compile(
    r'set\s+PhiBins\s+\{\}\s*'
    r'for\s*\{set\s+i\s+(-?\d+)\}\s*\{\$i\s*<=\s*(-?\d+)\}\s*\{incr\s+i\}\s*\{\s*'
    r'add\s+PhiBins\s*\[expr\s*\{\$i\s*\*\s*\$pi\s*/\s*([\d.]+)\}\]\s*\}',
    re.MULTILINE)

_ETA_LITERAL_PAT = re.compile(
    r'foreach\s+eta\s*\{([^}]*)\}\s*\{\s*add\s+EtaPhiBins\s+\$eta\s+\$PhiBins\s*\}',
    re.MULTILINE)

_ETA_ARITH_PAT = re.compile(
    r'for\s*\{set\s+i\s+(-?\d+)\}\s*\{\$i\s*<=\s*(-?\d+)\}\s*\{incr\s+i\}\s*\{\s*'
    r'set\s+eta\s*\[expr\s*\{([^}]*?)\}\]\s*'
    r'add\s+EtaPhiBins\s+\$eta\s+\$PhiBins\s*\}',
    re.MULTILINE)


def _eval_i_expr(expr_text, i):
    ### evaluate a small "$i", "+", "*", literal-number Tcl expr (e.g.
    # "$i * 0.0174" or "-2.958 + $i * 0.0174") for a given integer i
    expr = expr_text.replace('$i', '({!r})'.format(float(i)))
    return float(eval(expr, {'__builtins__': {}}, {}))


def _module_body_span(text, module_name):
    '''Return (body_start, body_end): absolute offsets of a module's { ... } contents.'''
    module_pat = re.compile(r'^\s*module\s+\S+\s+' + re.escape(module_name) + r'\s*\{', re.MULTILINE)
    m = module_pat.search(text)
    if not m:
        raise ValueError('module {} not found'.format(module_name))
    depth, i = 0, m.end() - 1
    for i in range(m.end() - 1, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                break
    return m.end(), i


def _parse_blocks(body):
    '''
    Return (regions, span_start, span_end): regions in document order, each
    {'eta_edges': [...], 'phi_edges': [...]}, and the (start, end) offsets
    (relative to `body`) spanning everything parsed - the first PhiBins
    reset through the last eta-block, for find_grid_span().
    '''
    phi_blocks = []  # (start, end, phi_edges)
    for m in _PHI_RESET_PAT.finditer(body):
        lo, hi, denom = int(m.group(1)), int(m.group(2)), float(m.group(3))
        phi_edges = [i * math.pi / denom for i in range(lo, hi + 1)]
        phi_blocks.append((m.start(), m.end(), phi_edges))

    eta_blocks = []  # (start, end, eta_edges)
    for m in _ETA_LITERAL_PAT.finditer(body):
        eta_edges = [float(x) for x in m.group(1).split()]
        eta_blocks.append((m.start(), m.end(), eta_edges))
    for m in _ETA_ARITH_PAT.finditer(body):
        lo, hi, expr_text = int(m.group(1)), int(m.group(2)), m.group(3)
        eta_edges = [_eval_i_expr(expr_text, i) for i in range(lo, hi + 1)]
        eta_blocks.append((m.start(), m.end(), eta_edges))
    eta_blocks.sort(key=lambda b: b[0])

    if not phi_blocks or not eta_blocks:
        return [], None, None

    regions = []
    for eta_start, eta_end, eta_edges in eta_blocks:
        # associate with the closest preceding phi-reset block
        candidates = [pb for pb in phi_blocks if pb[1] <= eta_start]
        if not candidates:
            raise ValueError('eta block at offset {} has no preceding PhiBins reset'.format(eta_start))
        phi_edges = max(candidates, key=lambda pb: pb[1])[2]
        regions.append({'eta_edges': eta_edges, 'phi_edges': phi_edges})

    span_start = min(phi_blocks[0][0], eta_blocks[0][0])
    span_end = max(eta_blocks[-1][1], phi_blocks[-1][1])
    return regions, span_start, span_end


def parse_regions(text, module_name):
    '''
    Return a list of {'eta_edges': [...], 'phi_edges': [...]} dicts, one per
    eta-block found (in document order) inside `module ... module_name { ... }`,
    each paired with whichever PhiBins definition most recently preceded it.
    '''
    body_start, body_end = _module_body_span(text, module_name)
    regions, span_start, span_end = _parse_blocks(text[body_start:body_end])
    if not regions:
        raise ValueError('no PhiBins/EtaPhiBins blocks found in module {}'.format(module_name))
    return regions


def find_grid_span(text, module_name):
    '''
    Return (start, end): absolute offsets in `text` spanning the whole
    tower-grid definition (every PhiBins reset and eta-block) inside
    `module ... module_name { ... }`, for replacement via replace_grid().
    '''
    body_start, body_end = _module_body_span(text, module_name)
    body = text[body_start:body_end]
    _, span_start, span_end = _parse_blocks(body)
    if span_start is None:
        raise ValueError('no PhiBins/EtaPhiBins blocks found in module {}'.format(module_name))
    return body_start + span_start, body_start + span_end


def format_regions_as_tcl(regions, indent='  '):
    '''
    Regenerate the "set PhiBins {}; add PhiBins ...; foreach eta {...}
    {add EtaPhiBins $eta $PhiBins}" Tcl text for `regions` (one
    self-contained block per region, in order) - always the literal-list
    eta style regardless of the original's style, since that's valid for
    any region (including ones parsed from an arithmetic eta-loop) and
    robust to any coarsening factor, including ones that don't evenly
    divide the original bin count or aren't integers.
    '''
    blocks = []
    for r in regions:
        lines = [indent + 'set PhiBins {}']
        for v in r['phi_edges']:
            lines.append('{}add PhiBins {:.10g}'.format(indent, v))
        eta_list = ' '.join('{:.10g}'.format(v) for v in r['eta_edges'])
        lines.append('{}foreach eta {{{}}} {{'.format(indent, eta_list))
        lines.append('{}  add EtaPhiBins $eta $PhiBins'.format(indent))
        lines.append('{}}}'.format(indent))
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


def replace_grid(text, module_name, new_regions):
    '''Return `text` with module_name's whole tower-grid definition replaced by new_regions.'''
    start, end = find_grid_span(text, module_name)
    return text[:start] + format_regions_as_tcl(new_regions) + text[end:]


def _coarsen_contiguous_run(run_edges, factor):
    n_orig_bins = len(run_edges) - 1
    if n_orig_bins < 1:
        return list(run_edges)
    n_new_bins = max(1, int(round(n_orig_bins / factor)))
    orig_idx = np.arange(len(run_edges), dtype=np.float64)
    new_idx = np.linspace(0, len(run_edges) - 1, n_new_bins + 1)
    return np.interp(new_idx, orig_idx, run_edges)


def coarsen_edges(edges, factor):
    '''
    Resample a list of bin edges so each new bin is (on average) `factor`
    times wider - works for any factor >= 1, not just integers. Implemented
    as linear interpolation in INDEX space (for uniformly-spaced edges,
    true of every grid in these cards, this is exactly "factor" wider
    bins; for an integer factor that evenly divides the original bin count
    it's identical to plain index-striding) - but several of these cards'
    eta lists have a deliberate GAP (e.g. an endcap list jumping straight
    from the negative side to the positive side, skipping the barrel
    entirely, which a different region/block already covers). Interpolating
    across such a gap would invent a bogus intermediate edge spanning it,
    so gaps (a step more than 3x the list's median step) are detected and
    each contiguous run between them is coarsened independently, never
    interpolated across.
    '''
    if factor == 1:
        return list(edges)
    edges = np.asarray(edges, dtype=np.float64)
    steps = np.diff(edges)
    median_step = np.median(np.abs(steps))
    gap_after = np.abs(steps) > 3 * median_step
    run_starts = [0] + list(np.nonzero(gap_after)[0] + 1)
    run_bounds = list(zip(run_starts, run_starts[1:] + [len(edges)]))

    new_edges = []
    for start, end in run_bounds:
        coarsened_run = _coarsen_contiguous_run(edges[start:end], factor)
        if new_edges and abs(new_edges[-1] - coarsened_run[0]) < 1e-9:
            new_edges.extend(coarsened_run[1:].tolist())
        else:
            new_edges.extend(coarsened_run.tolist())
    return new_edges


def coarsen_regions(regions, factor):
    if factor == 1:
        return regions
    return [{'eta_edges': coarsen_edges(r['eta_edges'], factor),
             'phi_edges': coarsen_edges(r['phi_edges'], factor)} for r in regions]


def assign_towers(regions, eta, phi):
    '''
    Vectorized tower assignment for arrays `eta`, `phi` (same length).
    Returns an integer array of the same length: a unique tower ID
    (encodes region + eta-bin + phi-bin), or -1 if outside every region's
    eta span. IDs are only unique within a single call (a fixed `regions`
    grid) - fine for per-jet merging, not meant to be compared across calls.
    '''
    n = len(eta)
    tower_id = np.full(n, -1, dtype=np.int64)
    assigned = np.zeros(n, dtype=bool)
    offset = 0
    for r in regions:
        eta_edges = np.asarray(r['eta_edges'])
        phi_edges = np.asarray(r['phi_edges'])
        n_phi = len(phi_edges) - 1
        in_region = (~assigned) & (eta >= eta_edges[0]) & (eta <= eta_edges[-1])
        if np.any(in_region):
            eta_bin = np.clip(np.searchsorted(eta_edges, eta[in_region], side='right') - 1, 0, len(eta_edges) - 2)
            # wrap phi into the grid's own range before binning (grids span a full -pi..pi)
            phi_wrapped = (phi[in_region] - phi_edges[0]) % (2 * np.pi) + phi_edges[0]
            phi_bin = np.clip(np.searchsorted(phi_edges, phi_wrapped, side='right') - 1, 0, n_phi - 1)
            tower_id[in_region] = offset + eta_bin * n_phi + phi_bin
            assigned |= in_region
        offset += (len(eta_edges) - 1) * n_phi
    return tower_id
