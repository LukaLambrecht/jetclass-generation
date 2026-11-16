#!/usr/bin/env python3

'''Parse, coarsen and assign candidates to a SimpleCalorimeter tower grid, as defined in a
Delphes .tcl card.

Two eta-block styles appear in these cards, both handled here:
  - literal:    foreach eta {v1 v2 ...} {add EtaPhiBins $eta $PhiBins}
  - arithmetic: for {set i A} {$i <= B} {incr i} {set eta [expr {EXPR}] ...}
Each block is associated with whichever PhiBins definition most recently preceded it,
which is how Tcl scoping behaves here: two consecutive eta-blocks may share one PhiBins
definition.

One deliberate simplification: Delphes merges every `add EtaPhiBins` call across all
blocks into one globally sorted boundary list, so the real grid has thin transition bins
at each block edge. This module instead treats each block as an independent region
covering its own eta span with its own phi granularity, taking the first matching region
where they overlap. That only affects the thin transition slivers, which is adequate for
an aggregate energy-multiplicity comparison but is not a bit-exact reproduction of
Delphes' own tower construction.
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
    '''Evaluate a small Tcl expression over $i, built from literals, + and *, for one integer
    i.
    '''
    expr = expr_text.replace('$i', '({!r})'.format(float(i)))
    return float(eval(expr, {'__builtins__': {}}, {}))


def _module_body_span(text, module_name):
    '''Absolute offsets (start, end) of a module's { ... } contents.'''
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
    '''Parse one module body into regions.

    Returns (regions, span_start, span_end): the regions in document order, each
    {'eta_edges', 'phi_edges'}, and the offsets spanning everything parsed, from the first
    PhiBins reset through the last eta-block.
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
    '''The {'eta_edges', 'phi_edges'} regions defined inside the named module, in document
    order, each paired with the PhiBins definition that precedes it.
    '''
    body_start, body_end = _module_body_span(text, module_name)
    regions, span_start, span_end = _parse_blocks(text[body_start:body_end])
    if not regions:
        raise ValueError('no PhiBins/EtaPhiBins blocks found in module {}'.format(module_name))
    return regions


def find_grid_span(text, module_name):
    '''Absolute offsets spanning the whole tower-grid definition inside the named module, for
    replacement via replace_grid().
    '''
    body_start, body_end = _module_body_span(text, module_name)
    body = text[body_start:body_end]
    _, span_start, span_end = _parse_blocks(body)
    if span_start is None:
        raise ValueError('no PhiBins/EtaPhiBins blocks found in module {}'.format(module_name))
    return body_start + span_start, body_start + span_end


def format_regions_as_tcl(regions, indent='  '):
    '''Regenerate the Tcl text defining `regions`, one self-contained block each.

    Always uses the literal-list eta style, whatever the original used: it is valid for any
    region and robust to any coarsening factor, including one that does not evenly divide
    the original bin count.
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
    '''`text` with the named module's whole tower-grid definition replaced by new_regions.
    '''
    start, end = find_grid_span(text, module_name)
    return text[:start] + format_regions_as_tcl(new_regions) + text[end:]


def _coarsen_contiguous_run(run_edges, factor):
    '''Coarsen one gap-free run of edges by `factor`, interpolating in index space.'''
    n_orig_bins = len(run_edges) - 1
    if n_orig_bins < 1:
        return list(run_edges)
    n_new_bins = max(1, int(round(n_orig_bins / factor)))
    orig_idx = np.arange(len(run_edges), dtype=np.float64)
    new_idx = np.linspace(0, len(run_edges) - 1, n_new_bins + 1)
    return np.interp(new_idx, orig_idx, run_edges)


def coarsen_edges(edges, factor):
    '''Resample bin edges so each new bin is, on average, `factor` times wider.

    Works for any factor >= 1, not only integers, by interpolating in index space. For the
    uniformly-spaced edges these cards use that gives exactly `factor` times wider bins.

    Some eta lists have a deliberate gap, e.g. an endcap list that jumps across the barrel
    another region already covers. Interpolating across such a gap would invent a bogus
    edge spanning it, so gaps are detected and each contiguous run between them is
    coarsened on its own.
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
    '''coarsen_edges() applied to every region's eta and phi edges.'''
    if factor == 1:
        return regions
    return [{'eta_edges': coarsen_edges(r['eta_edges'], factor),
             'phi_edges': coarsen_edges(r['phi_edges'], factor)} for r in regions]


def assign_towers(regions, eta, phi):
    '''Vectorized tower assignment for equal-length `eta` and `phi` arrays.

    Returns a tower ID per entry, encoding region and bin, or -1 outside every region's eta
    span. IDs are unique only within one call, for a fixed grid, so they are meant for
    per-jet merging rather than comparison across calls.
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
