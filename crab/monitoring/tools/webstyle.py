# Shared look and feel for the CRAB monitoring pages
#
# Both monitoring pages are built from this module, so they stay consistent:
#   * ../monitor_crab_jobs.py   -> index.html    (per-task status)
#   * mirror_job_logs.py        -> failures.html, task_<...>.html  (per-job failures)

import html
import json
import os
from datetime import datetime

# Job states in the order they are laid out in the progress bar, left to right. It
# reads as a progression: done -> moving -> running -> will run again -> waiting -> bad.
#
# A state missing from here still appears in the legend (so nothing is ever silently
# dropped) but contributes no coloured segment.
STATUS_ORDER = (
    'finished',
    'transferring',
    'running',
    'toRetry',
    'idle',
    'unsubmitted',
    'failed',
    'killed',
)

STATUS_COLORS = {
    'finished':     '#27AE60',   # green
    'transferring': '#9B59B6',   # purple
    'running':      '#2471A3',   # deep blue
    'toRetry':      '#E8A33D',   # amber
    'idle':         '#9AA7B1',   # grey
    'unsubmitted':  '#D5DBDF',   # light grey
    'failed':       '#C0392B',   # red
    'killed':       '#7B241C',   # dark maroon
}

# States that mean "something went wrong", for emphasis in the legend.
BAD_STATES = ('failed', 'killed')


def esc(value):
    """HTML-escape anything, including None and non-strings."""
    if value is None:
        return ''
    return html.escape(str(value), quote=True)


def parse_pct(value):
    """'99.6%' -> 99.6, tolerating junk.

    crab's own output can put non-numeric text where a percentage is expected (the
    monitor stores {'crab status': 'failed'} when a task cannot be read, and '<none>'
    when a percentage is missing), so this must never raise - a malformed number is
    not a reason to lose the whole page.
    """
    if value is None:
        return None
    try:
        return float(str(value).strip().rstrip('%'))
    except (TypeError, ValueError):
        return None


CSS = """
:root {
  --bg: #ffffff;
  --fg: #20262E;
  --muted: #6B7680;
  --line: #DDE1E6;
  --head-bg: #2C3E50;
  --head-fg: #EAECEE;
  --th-bg: #F4F6F7;
  --pill-bg: #E8EDF1;
  --bar-bg: #EDF0F2;
  --link: #1A5276;
  --card: #FBFCFC;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #15191E;
    --fg: #E6E9EC;
    --muted: #9AA7B1;
    --line: #2B323A;
    --head-bg: #0E1318;
    --head-fg: #E6E9EC;
    --th-bg: #1C2228;
    --pill-bg: #232B33;
    --bar-bg: #232B33;
    --link: #7FB3D5;
    --card: #1A2026;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; padding: 0;
  background: var(--bg); color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  font-size: 15px; line-height: 1.45;
  -webkit-text-size-adjust: 100%;
}
a { color: var(--link); }
.banner { background: var(--head-bg); color: var(--head-fg); padding: 14px 16px; }
.banner h1 { margin: 0; font-size: 20px; font-weight: 600; }
.banner .sub { font-size: 13px; opacity: .85; margin-top: 4px; }
.wrap { padding: 12px 16px 28px 16px; max-width: 1100px; }
h2 { font-size: 16px; margin: 22px 0 8px 0; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 8px 6px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { background: var(--th-bg); font-size: 13px; font-weight: 600; }
tr:last-child td { border-bottom: none; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
       font-size: 12px; word-break: break-word; }
/* overflow-wrap: the muted sub-line carries things like the CRAB task name
   (261112_083348:llambrec_crab_<request>), a long string with no spaces to break at,
   which would otherwise push the table wider than a phone screen. */
.muted { color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.nowrap { white-space: nowrap; }
.name { font-weight: 600; word-break: break-word; }

/* progress bar: flex segments, so widths cannot overflow or drift out of the
   container the way absolutely-positioned bars with cumulative offsets did. */
.bar { display: flex; width: 100%; height: 14px; border-radius: 7px;
       overflow: hidden; background: var(--bar-bg); }
.bar span { display: block; height: 100%; }
.legend { margin-top: 6px; }
.pill { display: inline-block; padding: 1px 8px; border-radius: 10px;
        font-size: 12px; background: var(--pill-bg); margin: 2px 4px 0 0;
        white-space: nowrap; }
.pill .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%;
             margin-right: 5px; vertical-align: baseline; }
.pill.bad { font-weight: 600; }
.warn { background: #FDEBD0; color: #7E5109; border-left: 3px solid #E8A33D;
        padding: 8px 10px; margin: 10px 0; font-size: 13px; border-radius: 3px; }
@media (prefers-color-scheme: dark) {
  .warn { background: #2E2616; color: #F0C987; }
}
.nav { margin-top: 24px; padding-top: 12px; border-top: 1px solid var(--line);
       font-size: 14px; }
.nav a { margin-right: 14px; }
details { margin: 8px 0; }
summary { cursor: pointer; font-size: 14px; color: var(--muted); }
/* per-row details: smaller and tighter than a page-level <details>, so a table of
   them does not look like a list of sections. */
details.rowdetails { margin: 6px 0 0 0; }
details.rowdetails summary { font-size: 12px; }
details.rowdetails .kv { font-size: 12px; margin: 4px 0 0 0; }
details.rowdetails .kv .k { color: var(--muted); margin-right: 4px; }
.btn { font: inherit; font-size: 13px; cursor: pointer; padding: 4px 10px;
       border: 1px solid var(--line); border-radius: 4px;
       background: var(--th-bg); color: var(--fg); }
.btn:hover { border-color: var(--muted); }
.toolbar { margin: 8px 0; }
@media (max-width: 520px) {
  .wrap { padding: 10px 12px 24px 12px; }
  table { font-size: 13px; }
  th, td { padding: 7px 4px; }
}
"""


def page_head(title, subtitle=None):
    """Doctype through the opening banner. Pair with page_foot()."""
    out = (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<title>{}</title>\n'
        '<style>{}</style>\n'
        '</head>\n<body>\n'
    ).format(esc(title), CSS)
    out += '<div class="banner"><h1>{}</h1>'.format(esc(title))
    if subtitle:
        out += '<div class="sub">{}</div>'.format(subtitle)
    out += '</div>\n<div class="wrap">\n'
    return out


def page_foot(links=None):
    """Close the page, optionally with a footer nav.

    links: list of (href, text) tuples. Rendered below the page content - the status
    page's link to the failure pages belongs under the task table, not in the banner,
    so that the first thing on screen is the status itself.
    """
    out = ''
    if links:
        out += '<div class="nav">\n'
        for href, text in links:
            out += '<a href="{}">{}</a>\n'.format(esc(href), esc(text))
        out += '</div>\n'
    out += '</div>\n</body>\n</html>\n'
    return out


def timestamp():
    return datetime.now().strftime('%d/%m/%Y %H:%M:%S')


def progress_bar(values):
    """Stacked bar + legend for a {state: '12.3%'} mapping.

    Never raises: states with unparseable percentages are shown in the legend without
    a bar segment, which is strictly better than losing the row.
    """
    values = values or {}
    out = '<div class="bar">'
    for state in STATUS_ORDER:
        if state not in values:
            continue
        pct = parse_pct(values[state])
        if not pct or pct <= 0:
            continue
        out += '<span style="width:{:.4f}%;background:{}"></span>'.format(
            min(pct, 100.0), STATUS_COLORS.get(state, '#9AA7B1'))
    out += '</div>\n'
    out += status_legend(values)
    return out


def status_legend(values):
    """Legend pills, in STATUS_ORDER, then any unrecognised keys.

    States sitting at exactly zero are dropped: the monitor seeds every task with
    'finished': '0%', and carrying that through to the page added a pill that says
    nothing on every row. A value that is not a number (e.g. 'crab status': 'failed')
    is always kept - it is never noise. If that would empty the legend completely,
    everything is shown instead, so a row is never left with no explanation at all.
    """
    values = values or {}
    known = [s for s in STATUS_ORDER if s in values]
    other = sorted(k for k in values if k not in STATUS_COLORS)
    order = known + other
    nonzero = [s for s in order
               if parse_pct(values[s]) is None or parse_pct(values[s]) != 0]
    if nonzero:
        order = nonzero
    out = '<div class="legend">'
    for state in order:
        color = STATUS_COLORS.get(state)
        cls = 'pill bad' if state in BAD_STATES else 'pill'
        dot = ('<span class="dot" style="background:{}"></span>'.format(color)
               if color else '')
        out += '<span class="{}">{}{}: {}</span>'.format(
            cls, dot, esc(state), esc(values[state]))
    out += '</div>'
    return out


def warn(message):
    return '<div class="warn">{}</div>\n'.format(esc(message))


def row_details(pairs, label='More details'):
    """A collapsed <details> block for one table row.

    pairs: sequence of (label, value) shown one per line, values in <code> since they
    are mostly paths. Returns '' for no pairs, so a row never grows an empty toggle.
    """
    pairs = [(k, v) for k, v in (pairs or []) if v]
    if not pairs:
        return ''
    out = '<details class="rowdetails"><summary>{}</summary>'.format(esc(label))
    for key, value in pairs:
        out += '<div class="kv"><span class="k">{}:</span><code>{}</code></div>'.format(
            esc(key), esc(value))
    out += '</details>'
    return out


def expand_all_button(selector='details.rowdetails',
                      expand='Expand all details',
                      collapse='Collapse all details'):
    """A button that opens or closes every matching <details> at once.

    The label follows the real state of the page rather than a remembered one: it acts
    on "is anything still closed?", so it keeps doing the useful thing after rows have
    been toggled by hand. The selector is scoped, so a page-level <details> such as
    Meta-info is left alone.

    Needs javascript, and nothing else does - so if it is unavailable the button is
    simply inert and every row still expands on its own.
    """
    # json.dumps for the two labels, not repr or a bare quote: it produces a valid
    # JS string literal whatever the label contains, so a quote or a backslash in a
    # caller's wording cannot break the script. esc() is for the HTML text only -
    # putting an HTML-escaped string into JS would show the entity literally.
    return (
        '<div class="toolbar">'
        '<button type="button" class="btn" data-sel="{sel}" '
        'onclick="crabToggleAll(this)">{expand_html}</button>'
        '</div>\n'
        '<script>\n'
        'function crabToggleAll(btn) {{\n'
        '  var items = document.querySelectorAll(btn.dataset.sel);\n'
        '  var anyClosed = Array.prototype.some.call(items, function (d) {{\n'
        '    return !d.open;\n'
        '  }});\n'
        '  Array.prototype.forEach.call(items, function (d) {{ d.open = anyClosed; }});\n'
        '  btn.textContent = anyClosed ? {collapse_js} : {expand_js};\n'
        '}}\n'
        '</script>\n'
    ).format(sel=esc(selector), expand_html=esc(expand),
             expand_js=json.dumps(expand), collapse_js=json.dumps(collapse))


def write_atomic(path, text):
    """Write via a temp file + rename.

    The sweep runs every 15 minutes and the pages are served straight off EOS, so a
    reader can hit the file mid-write. os.replace is atomic within a filesystem, so a
    browser sees either the old page or the new one, never a half-written one - and a
    crash part-way through building the text leaves the previous page intact.
    """
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(text)
    os.replace(tmp, path)
