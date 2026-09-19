#!/usr/bin/env python3

'''
Minimal, generic helpers for reading and evaluating the piecewise pT/eta
formulas used throughout this repo's Delphes cards (EfficiencyFormula,
ResolutionFormula, ...), and for writing new ones in the same style.

These formulas are Delphes' own small expression language: arithmetic on
free variables (`pt`/`eta` for tracking Efficiency/MomentumSmearing/
TrackSmearing formulas; `energy`/`eta` for SimpleCalorimeter's
ResolutionFormula), comparisons, `&&`, and abs()/exp()/sqrt(), combined as
a sum of "indicator * ... * value" terms (see any existing EfficiencyFormula
block for examples). extract_formula_block() pulls the literal text of one
such block out of a .tcl file (via brace matching, not regex-of-the-contents,
so it's robust to whatever arithmetic is inside), and evaluate_formula()
evaluates that literal text at a given point (given as keyword arguments
matching whichever free variables the formula actually uses) using a tiny,
restricted Python expression evaluator - not a real Tcl interpreter, since
Delphes' `^` means "power" (like Python's `**`), which is different from
Tcl's own `expr` semantics (bitwise XOR). extract_scalar() reads a plain
(non-piecewise, unbraced) `set Name value` line, e.g. SimpleCalorimeter's
`EnergyMin`/`EnergySignificanceMin`.

Together these let generate_hlt_card.py treat the offline Delphes card as
the single source of truth for "what does offline reconstruction do",
instead of duplicating its numbers - it reads the real file and evaluates
the real formula, every time.
'''

import re
import math


def find_formula_span(text, module_name, formula_name):
    '''
    Return (start, end): character offsets into `text` spanning the literal
    contents (excluding the enclosing braces) assigned to `formula_name`
    (e.g. "EfficiencyFormula") inside `module ... module_name { ... }`
    (e.g. "ChargedHadronTrackingEfficiency"). Offsets are absolute within
    `text`, so callers can both read (text[start:end]) and splice
    (text[:start] + new + text[end:]) the block in place.
    '''
    module_pat = re.compile(
        r'^\s*module\s+\S+\s+' + re.escape(module_name) + r'\s*\{', re.MULTILINE)
    m = module_pat.search(text)
    if not m:
        raise ValueError('module {} not found'.format(module_name))
    module_open = m.end() - 1
    _, module_close_after = _match_braces(text, module_open)

    # blank out full-line comments first (same length, so offsets stay
    # valid), so a commented-out example line like
    # "# set ResolutionFormula {...}" (present in every module as a hint)
    # isn't mistaken for the real assignment below it
    module_region = text[module_open:module_close_after]
    region_no_comments = re.sub(
        r'#[^\n]*', lambda m: ' ' * len(m.group(0)), module_region)

    set_pat = re.compile(r'set\s+' + re.escape(formula_name) + r'\s*\{')
    m2 = set_pat.search(region_no_comments)
    if not m2:
        raise ValueError('{} not found in module {}'.format(formula_name, module_name))
    formula_open = module_open + m2.end() - 1
    _, formula_close_after = _match_braces(text, formula_open)
    return formula_open + 1, formula_close_after - 1


def extract_formula_block(text, module_name, formula_name):
    '''Return the literal formula text (see find_formula_span).'''
    start, end = find_formula_span(text, module_name, formula_name)
    return text[start:end]


def replace_formula_block(text, module_name, formula_name, new_content):
    '''Return `text` with the named formula's contents replaced by `new_content`.'''
    start, end = find_formula_span(text, module_name, formula_name)
    return text[:start] + '\n' + new_content + '\n  ' + text[end:]


def _match_braces(text, open_brace_pos):
    '''Given the index of an opening "{", return (contents, index_after_closing_"}").'''
    assert text[open_brace_pos] == '{'
    depth = 0
    for i in range(open_brace_pos, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return text[open_brace_pos + 1:i], i + 1
    raise ValueError('unbalanced braces')


_ALLOWED_NAMES = {'abs': abs, 'exp': math.exp, 'sqrt': math.sqrt}
_IDENTIFIER_RE = re.compile(r'\b[a-zA-Z_][a-zA-Z_0-9]*\b')


def evaluate_formula(formula_text, **variables):
    '''
    Numerically evaluate a Delphes-style formula string at a given point.
    `variables` supplies the free variables the formula itself uses as
    keyword arguments, e.g. evaluate_formula(f, pt=1.5, eta=0.3) for a
    tracking formula, or evaluate_formula(f, energy=5.0, eta=0.3) for a
    SimpleCalorimeter ResolutionFormula. Translates Delphes/Tcl syntax to
    Python syntax (`^` -> `**`, `&&` -> `and`) and evaluates with no
    builtins except abs/exp/sqrt.
    '''
    expr = formula_text.replace('\\\n', ' ').replace('\n', ' ')
    expr = expr.replace('^', '**').replace('&&', ' and ').replace('||', ' or ')

    def repl(m):
        name = m.group(0)
        if name in variables:
            return '({!r})'.format(float(variables[name]))
        if name in _ALLOWED_NAMES or name in ('and', 'or'):
            return name
        raise ValueError('unexpected identifier {!r} in formula (no value given for it)'.format(name))

    expr = _IDENTIFIER_RE.sub(repl, expr)
    return float(eval(expr, {'__builtins__': {}}, dict(_ALLOWED_NAMES)))


def extract_scalar(text, module_name, var_name):
    '''
    Read a plain scalar assignment, e.g. `set EnergyMin 0.5` inside
    `module ... module_name { ... }` - unlike EfficiencyFormula/
    ResolutionFormula, these aren't brace-enclosed.
    '''
    module_pat = re.compile(
        r'^\s*module\s+\S+\s+' + re.escape(module_name) + r'\s*\{', re.MULTILINE)
    m = module_pat.search(text)
    if not m:
        raise ValueError('module {} not found'.format(module_name))
    module_open = m.end() - 1
    module_body, _ = _match_braces(text, module_open)
    body_no_comments = re.sub(r'#[^\n]*', lambda m: ' ' * len(m.group(0)), module_body)

    m2 = re.search(r'set\s+' + re.escape(var_name) + r'\s+([0-9.eE+-]+)', body_no_comments)
    if not m2:
        raise ValueError('scalar {} not found in module {}'.format(var_name, module_name))
    return float(m2.group(1))


def replace_scalar(text, module_name, var_name, new_value):
    '''
    Return `text` with a plain scalar assignment (e.g. `set JetPTMin 200.0`,
    see extract_scalar's own docstring for the "plain" vs brace-enclosed
    distinction) inside module `module_name` replaced by `new_value`.
    '''
    module_pat = re.compile(
        r'^\s*module\s+\S+\s+' + re.escape(module_name) + r'\s*\{', re.MULTILINE)
    m = module_pat.search(text)
    if not m:
        raise ValueError('module {} not found'.format(module_name))
    module_open = m.end() - 1
    module_body, _ = _match_braces(text, module_open)
    body_no_comments = re.sub(r'#[^\n]*', lambda mm: ' ' * len(mm.group(0)), module_body)

    m2 = re.search(r'set\s+' + re.escape(var_name) + r'\s+([0-9.eE+-]+)', body_no_comments)
    if not m2:
        raise ValueError('scalar {} not found in module {}'.format(var_name, module_name))
    val_start = module_open + 1 + m2.start(1)
    val_end = module_open + 1 + m2.end(1)
    return text[:val_start] + '{:.6g}'.format(new_value) + text[val_end:]


def format_piecewise_table(eta_edges, pt_edges, values, var_prefix=''):
    '''
    Build a Delphes-style piecewise-constant EfficiencyFormula/ResolutionFormula
    string (a sum of "(eta range) * (pt range) * (value)" terms, one per
    bin) from an explicit [n_eta][n_pt] grid of values - the same style
    already used by this repo's hand-written formulas, just generated
    instead of typed by hand.

    `var_prefix` is prepended to each generated line for indentation.

    The lowest and highest pT bins are both open-ended (`pt <= hi` / `pt >
    lo`, no lower/upper bound at all), so the table has no gap: a pt outside
    [pt_edges[0], pt_edges[-1]) still lands in the nearest bin's condition
    and gets that bin's value, rather than matching nothing and silently
    evaluating to 0 (the previous behavior below the lowest edge specifically -
    harmless everywhere this was only ever evaluated within the measured
    range, e.g. PT_EDGES already starts near 0, but a real gap for
    JET_PT_EDGES, whose lowest edge (200 GeV) is a baseline *selection* of
    the input data, not a physical floor - a jet genuinely evaluated below
    it, e.g. after relaxing an HLT card's own FastJetFinder JetPTMin so
    degraded jets aren't dropped before ever reaching this formula, would
    otherwise get scaled by a phantom factor of exactly 0).
    '''
    n_eta = len(eta_edges) - 1
    n_pt = len(pt_edges) - 1
    lines = []
    for ie in range(n_eta):
        eta_lo, eta_hi = eta_edges[ie], eta_edges[ie + 1]
        eta_cond = '(abs(eta) > {:g} && abs(eta) <= {:g})'.format(eta_lo, eta_hi)
        for ip in range(n_pt):
            pt_lo, pt_hi = pt_edges[ip], pt_edges[ip + 1]
            if ip == n_pt - 1:
                pt_cond = '(pt > {:g})'.format(pt_lo)
            elif ip == 0:
                pt_cond = '(pt <= {:g})'.format(pt_hi)
            else:
                pt_cond = '(pt > {:g} && pt <= {:g})'.format(pt_lo, pt_hi)
            value = values[ie][ip]
            lines.append('{}{} * {} * ({:.6g})'.format(var_prefix, eta_cond, pt_cond, value))
    return ' +\n'.join(lines)


def format_piecewise_table_3d(eta_edges, pt_edges, d0_edges, values, var_prefix='', skip_zero=True):
    '''
    Like format_piecewise_table(), with a third, transverse-impact-parameter
    axis: one "(eta range) * (pt range) * (|d0| range) * (value)" term per
    (eta, pt, d0) bin, `values` being an [n_eta][n_pt][n_d0] grid. `d0` is the
    Delphes formula variable (candidate->D0, in mm, set by ParticlePropagator);
    abs() is used since only its magnitude matters (and Delphes' sign
    convention differs from CMS', see delphes_cards/KNOWN_ISSUES.md). pT is
    open-ended at both ends as in format_piecewise_table(); the lowest |d0|
    bin starts at 0 (closed) and the highest is open-ended, so every track
    lands in exactly one bin. With skip_zero, terms whose value is exactly 0
    are omitted (a sum of terms evaluates to 0 where no term applies anyway),
    keeping the formula shorter.
    '''
    n_eta, n_pt, n_d0 = len(eta_edges) - 1, len(pt_edges) - 1, len(d0_edges) - 1
    lines = []
    for ie in range(n_eta):
        eta_cond = '(abs(eta) > {:g} && abs(eta) <= {:g})'.format(eta_edges[ie], eta_edges[ie + 1])
        for ip in range(n_pt):
            pt_lo, pt_hi = pt_edges[ip], pt_edges[ip + 1]
            if ip == n_pt - 1:
                pt_cond = '(pt > {:g})'.format(pt_lo)
            elif ip == 0:
                pt_cond = '(pt <= {:g})'.format(pt_hi)
            else:
                pt_cond = '(pt > {:g} && pt <= {:g})'.format(pt_lo, pt_hi)
            for i0 in range(n_d0):
                value = values[ie][ip][i0]
                if skip_zero and value == 0:
                    continue
                d0_lo, d0_hi = d0_edges[i0], d0_edges[i0 + 1]
                if i0 == n_d0 - 1:
                    d0_cond = '(abs(d0) > {:g})'.format(d0_lo)
                elif i0 == 0:
                    d0_cond = '(abs(d0) <= {:g})'.format(d0_hi)
                else:
                    d0_cond = '(abs(d0) > {:g} && abs(d0) <= {:g})'.format(d0_lo, d0_hi)
                lines.append('{}{} * {} * {} * ({:.6g})'.format(var_prefix, eta_cond, pt_cond, d0_cond, value))
    if not lines:
        return '{}0'.format(var_prefix)
    return ' +\n'.join(lines)
