#!/usr/bin/env python3

'''
Minimal, generic helpers for reading and evaluating the piecewise pT/eta
formulas used throughout this repo's Delphes cards (EfficiencyFormula,
ResolutionFormula, ...), and for writing new ones in the same style.

These formulas are Delphes' own small expression language: arithmetic on
the free variables `pt` and `eta`, comparisons, `&&`, and abs()/exp()/sqrt(),
combined as a sum of "indicator * ... * value" terms (see any existing
EfficiencyFormula block for examples). extract_formula_block() pulls the
literal text of one such block out of a .tcl file (via brace matching, not
regex-of-the-contents, so it's robust to whatever arithmetic is inside),
and evaluate_formula() evaluates that literal text at a given (pt, eta)
point using a tiny, restricted Python expression evaluator - not a real
Tcl interpreter, since Delphes' `^` means "power" (like Python's `**`),
which is different from Tcl's own `expr` semantics (bitwise XOR).

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


def evaluate_formula(formula_text, pt, eta):
    '''
    Numerically evaluate a Delphes-style pT/eta formula string at a given
    (pt, eta) point. Translates Delphes/Tcl syntax to Python syntax
    (`^` -> `**`, `&&` -> `and`, bare `pt`/`eta` -> literal numbers) and
    evaluates with no builtins except abs/exp/sqrt.
    '''
    expr = formula_text.replace('\\\n', ' ').replace('\n', ' ')
    expr = expr.replace('^', '**').replace('&&', ' and ').replace('||', ' or ')

    def repl(m):
        name = m.group(0)
        if name == 'pt':
            return '({!r})'.format(float(pt))
        if name == 'eta':
            return '({!r})'.format(float(eta))
        if name in _ALLOWED_NAMES or name in ('and', 'or'):
            return name
        raise ValueError('unexpected identifier {!r} in formula'.format(name))

    expr = _IDENTIFIER_RE.sub(repl, expr)
    return float(eval(expr, {'__builtins__': {}}, dict(_ALLOWED_NAMES)))


def format_piecewise_table(eta_edges, pt_edges, values, var_prefix=''):
    '''
    Build a Delphes-style piecewise-constant EfficiencyFormula/ResolutionFormula
    string (a sum of "(eta range) * (pt range) * (value)" terms, one per
    bin) from an explicit [n_eta][n_pt] grid of values - the same style
    already used by this repo's hand-written formulas, just generated
    instead of typed by hand.

    `var_prefix` is prepended to each generated line for indentation.
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
            else:
                pt_cond = '(pt > {:g} && pt <= {:g})'.format(pt_lo, pt_hi)
            value = values[ie][ip]
            lines.append('{}{} * {} * ({:.6g})'.format(var_prefix, eta_cond, pt_cond, value))
    return ' +\n'.join(lines)
