#!/usr/bin/env python3

'''Read, evaluate and write the piecewise pT/eta formulas used in this repo's Delphes
cards (EfficiencyFormula, ResolutionFormula and the like).

Those formulas are Delphes' own small expression language: arithmetic on free variables
- pt/eta for the tracking modules, energy/eta for the calorimeters - plus comparisons,
&&, and abs()/exp()/sqrt(), combined as a sum of "indicator * value" terms.

extract_formula_block() pulls one block's literal text out of a .tcl file by brace
matching rather than by a regex over its contents, so it does not care what arithmetic
is inside. evaluate_formula() then evaluates that text at a given point with a small
restricted Python evaluator; it is not a Tcl interpreter, since Delphes reads `^` as a
power while Tcl's expr reads it as bitwise xor. extract_scalar() reads a plain,
unbraced `set Name value` line.

Together these let generate_hlt_card.py treat the offline card as the single source of
truth for what offline reconstruction does, reading and evaluating the real file rather
than duplicating its numbers.
'''

import re
import math


def find_formula_span(text, module_name, formula_name):
    '''Character offsets (start, end) spanning the contents assigned to `formula_name` inside
    `module ... module_name { ... }`, excluding the enclosing braces.

    Absolute within `text`, so callers can both read and splice the block in place.
    '''
    module_pat = re.compile(
        r'^\s*module\s+\S+\s+' + re.escape(module_name) + r'\s*\{', re.MULTILINE)
    m = module_pat.search(text)
    if not m:
        raise ValueError('module {} not found'.format(module_name))
    module_open = m.end() - 1
    _, module_close_after = _match_braces(text, module_open)

    # Blank out full-line comments first, keeping the length so the offsets stay valid, so
    # that a commented-out example line is not mistaken for the real assignment below it.
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
    '''The literal formula text; see find_formula_span.'''
    start, end = find_formula_span(text, module_name, formula_name)
    return text[start:end]


def replace_formula_block(text, module_name, formula_name, new_content):
    '''`text` with the named formula's contents replaced by `new_content`.'''
    start, end = find_formula_span(text, module_name, formula_name)
    return text[:start] + '\n' + new_content + '\n  ' + text[end:]


def _match_braces(text, open_brace_pos):
    '''Given the index of an opening brace, return (contents, index after the closing one).
    '''
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
    '''Evaluate a Delphes-style formula string at one point.

    `variables` supplies whichever free variables the formula uses, e.g.
    evaluate_formula(f, pt=1.5, eta=0.3). Translates the Delphes syntax to Python (`^` to
    `**`, `&&` to `and`) and evaluates with no builtins beyond abs, exp and sqrt.
    '''
    expr = formula_text.replace('\\\n', ' ').replace('\n', ' ')
    expr = expr.replace('^', '**').replace('&&', ' and ').replace('||', ' or ')

    def repl(m):
        '''Substitute one identifier: a supplied variable becomes its value, an allowed function
        name is kept, anything else is rejected.
        '''
        name = m.group(0)
        if name in variables:
            return '({!r})'.format(float(variables[name]))
        if name in _ALLOWED_NAMES or name in ('and', 'or'):
            return name
        raise ValueError('unexpected identifier {!r} in formula (no value given for it)'.format(name))

    expr = _IDENTIFIER_RE.sub(repl, expr)
    return float(eval(expr, {'__builtins__': {}}, dict(_ALLOWED_NAMES)))


def extract_scalar(text, module_name, var_name):
    '''Read a plain scalar assignment, e.g. `set EnergyMin 0.5`, inside the named module.

    Unlike the formulas, these are not brace-enclosed.
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
    '''`text` with a plain scalar assignment inside the named module set to `new_value`.
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
    '''Build a Delphes-style piecewise-constant formula from an [n_eta][n_pt] grid of values:
    a sum of "(eta range) * (pt range) * (value)" terms, one per bin.

    `var_prefix` is prepended to each line, for indentation.

    The lowest and highest pT bins are open-ended, so the table has no gap and a pt outside
    the grid still lands in the nearest bin rather than matching nothing and evaluating to
    zero. That matters wherever the lowest edge is a selection on the input data rather
    than a physical floor, since a jet genuinely below it would otherwise be scaled by a
    phantom factor of exactly zero.
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
    '''format_piecewise_table() with a third, transverse-impact-parameter axis: one
    "(eta range) * (pt range) * (|d0| range) * (value)" term per bin, from an
    [n_eta][n_pt][n_d0] grid.

    `d0` is the Delphes formula variable, in mm. Only its magnitude matters, so abs() is
    used. pT is open-ended at both ends as before; the lowest |d0| bin is closed at 0 and
    the highest is open-ended, so every track lands in exactly one bin. With skip_zero,
    terms whose value is exactly zero are omitted, which keeps the formula shorter and
    changes nothing, since a sum evaluates to zero where no term applies.
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
