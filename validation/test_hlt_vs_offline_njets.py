#!/usr/bin/env python3

'''
Concretely checks WHERE HLT-card jets get lost relative to offline-card
jets, by generating a small number of GEN events ONCE and running the SAME
events.hepmc through multiple Delphes cards (exactly like run.sh does) -
so any difference between cards is attributable only to their detector
modeling, not to independent proton collisions.

For each card, jets are counted at three stages (see count_delphes_jets.C
for the first two, makeNtuples.C for the third - this script doesn't
reimplement either, it drives the real production code):

  STAGE_A "clustered"     - entries in the raw Delphes Jet branch, i.e. how
                             many jets Delphes' own clustering found at all
                             (FastJetFinderPUPPIAK8's JetPTMin=200 cut,
                             applied at clustering time - IDENTICAL in every
                             card - but stored PT is post the
                             JetEnergyScalePUPPIAK8 correction, which is NOT
                             identical between cards).
  STAGE_B "pt/eta cut"    - of those, how many pass makeNtuples.C's own
                             `jet->PT < 120 || |eta| > 2.5` cut (also
                             IDENTICAL code/threshold in every card).
  STAGE_C "final ntuple"  - the actual number of entries written to the
                             ntuple by makeNtuples.C (STAGE_B jets that also
                             get a valid FatJetMatching truth label).

Reading this off: if STAGE_A itself differs a lot between cards, jets are
being lost before any cut even runs - never clustered in the first place
(a tracking/PF-candidate-multiplicity effect, upstream of any threshold).
If STAGE_A is similar but the STAGE_A -> STAGE_B loss differs, jets ARE
being clustered but their JES-corrected PT falls below the shared 120 GeV
cut more often for one card - a JES-correction effect surfacing through a
threshold both cards apply identically, not a different/stricter cut for
one of them. See the HLT card's own header comment (delphes_cards/
delphes_card_CMS_JetClassII_onlyFatJet_HLT_noPU.tcl) for the underlying
data-driven tracking-efficiency/JES/calorimeter curves this traces back to.

This was written to concretely confirm (with real numbers from a live run,
not just reading the cards) the offline-vs-HLT njets discussion from the
output_jetclass1_10M production run's size cross-check - see
print_njets.py for the actual per-process/card jet-count table from that
run's real output.

Usage:
  # default: 1000 TTBarLep events, offline vs HLT (both NoPU)
  python3 test_hlt_vs_offline_njets.py

  # a different process/stat/card set
  python3 test_hlt_vs_offline_njets.py --proc HToBB --nevent 2000 \\
      --cards onlyFatJetNoPU,onlyFatJetHLTNoPU,onlyFatJet,onlyFatJetHLT

  # keep the intermediate events.hepmc/events_delphes.root/ntuple.root
  # files around afterward for further inspection instead of deleting them
  python3 test_hlt_vs_offline_njets.py --keep --workdir /tmp/hlt_test
'''

import os
import sys
import argparse
import shutil
import subprocess
import tempfile

import uproot

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(THISDIR)
sys.path.append(REPO_DIR)
from download_gridpack import normalize_proc

GENCFG_PATH = os.path.join(REPO_DIR, 'gen_configs')
DELPHES_CARDS_DIR = os.path.join(REPO_DIR, 'delphes_cards')
DELPHES_ANALYZERS_DIR = os.path.join(REPO_DIR, 'delphes_analyzers')
COUNT_MACRO = os.path.join(THISDIR, 'count_delphes_jets.C')

# ============ same "basic configuration" as run.sh - kept in sync by hand ============
CMSSET_DEFAULT = '/cvmfs/cms.cern.ch/cmsset_default.sh'
MG5_PATH = '/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2'
DELPHES_PATH = '/eos/user/l/llambrec/jetclass/delphes'
LHAPDFCONFIG = '/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/lhapdf6_py3/share/LHAPDF/lhapdf.conf'
LHAPDF_DATA_PATH = '/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/lhapdf6_py3/share/LHAPDF'
PYTHIA8DATA = '/eos/user/l/llambrec/jetclass/MG5_aMC_v3_7_2/bin/HEPTools/pythia8/share/Pythia8/xmldoc'
# same LCG view + Delphes include path run.sh sources only for the ROOT-based
# (ntuple-making) step, not for generation/DelphesHepMC2 itself
LCG_SETUP = '/cvmfs/sft.cern.ch/lcg/views/LCG_104/x86_64-el9-gcc13-opt/setup.sh'
DELPHES_ROOT_INCLUDE = '/cvmfs/sft.cern.ch/lcg/releases/delphes/3.5.1pre09-9fe9c/x86_64-el9-gcc13-opt/include'
# same mapping as run.sh's card_file_for_name() bash function
CARD_FILE_FOR_NAME = {
    'onlyFatJet':          'delphes_card_CMS_JetClassII_onlyFatJet.tcl',
    'onlyFatJetHLT':       'delphes_card_CMS_JetClassII_onlyFatJet_HLT.tcl',
    'onlyFatJetNoPU':      'delphes_card_CMS_JetClassII_onlyFatJet_noPU.tcl',
    'onlyFatJetHLTNoPU':   'delphes_card_CMS_JetClassII_onlyFatJet_HLT_noPU.tcl',
    'lite':                'delphes_card_CMS_JetClassII_lite.tcl',
    'full':                'delphes_card_CMS_JetClassII.tcl',
    'JetClassI':           'delphes_card_CMS_JetClassI.tcl',
}
DEFAULT_PROC = 'TTBarLep'
DEFAULT_NEVENT = 1000
DEFAULT_CARDS = 'onlyFatJetNoPU,onlyFatJetHLTNoPU'
# ======================================================================================


def run_bash(script, cwd=None, label=''):
    '''Run a bash -c script, streaming output live (like run.sh's own -x trace) - raises on failure.'''
    print('--- running: {} ---'.format(label))
    result = subprocess.run(['bash', '-c', 'set -e\n' + script], cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError('{} failed with exit code {}'.format(label, result.returncode))


def run_bash_lenient(script, label=''):
    '''
    Captures and returns stdout - but, unlike run_bash(), does NOT treat a
    nonzero exit code as failure. `root -b -q [-l] -e '...'` can exit
    nonzero on interpreter shutdown even after correctly printing/writing
    everything it was asked to (a known ROOT quirk, reproduced directly
    while writing this script: a TFile::Open() one-liner left unclosed
    printed the right answer and still returned exit code 255). Neither
    run_timing_scan.py's own count_njets_command() nor run.sh's own
    makeNtuples.C++ call check root's exit code either, for the same
    reason - only the captured output / the output file's existence.
    Callers here do the equivalent: parse stdout for what they need and
    raise their own error if it's missing/unparseable.
    '''
    print('--- running: {} ---'.format(label))
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
    if result.stderr.strip():
        sys.stderr.write('--- {} stderr ---\n{}\n'.format(label, result.stderr))
    return result.stdout


def generate_events(proc_full, nevent, workdir):
    '''
    Set up a fresh proc_base (same logic as run.sh: copy the gridpack config,
    fall back to run_gen_default.sh if the process has no run_gen.sh of its
    own) and generate `nevent` GEN events into it - returns the resulting
    events.hepmc path.
    '''
    proc_base = os.path.join(workdir, 'proc_base')
    os.makedirs(proc_base, exist_ok=True)
    src = os.path.join(GENCFG_PATH, proc_full)
    if not os.path.isdir(src):
        raise RuntimeError('no gen config found for {!r} (expected {})'.format(proc_full, src))
    subprocess.run('cp -r {}/. {}/'.format(src, proc_base), shell=True, check=True)
    if not os.path.exists(os.path.join(proc_base, 'run_gen.sh')):
        shutil.copy(os.path.join(GENCFG_PATH, 'run_gen_default.sh'), os.path.join(proc_base, 'run_gen.sh'))

    script = '''
source {cmsset}
export MG5_PATH={mg5}
export GENCFG_PATH={gencfg}
export LHAPDFCONFIG={lhapdfconfig}
export LHAPDF_DATA_PATH={lhapdf_data}
export PYTHIA8DATA={pythia8data}
rm -f events.hepmc
./run_gen.sh {nevent}
'''.format(cmsset=CMSSET_DEFAULT, mg5=MG5_PATH, gencfg=GENCFG_PATH, lhapdfconfig=LHAPDFCONFIG,
           lhapdf_data=LHAPDF_DATA_PATH, pythia8data=PYTHIA8DATA, nevent=nevent)
    run_bash(script, cwd=proc_base, label='generate {} events for {}'.format(nevent, proc_full))

    hepmc = os.path.join(proc_base, 'events.hepmc')
    if not os.path.exists(hepmc):
        raise RuntimeError('run_gen.sh did not produce {}'.format(hepmc))
    return hepmc, proc_base


def run_delphes(card_name, hepmc_path, proc_base, workdir):
    '''Run DelphesHepMC2 with `card_name` on hepmc_path - same call as run.sh's own.'''
    if card_name not in CARD_FILE_FOR_NAME:
        raise ValueError('unknown Delphes card {!r} - expected one of: {}'.format(
            card_name, ', '.join(CARD_FILE_FOR_NAME)))
    card_path = os.path.join(DELPHES_CARDS_DIR, CARD_FILE_FOR_NAME[card_name])
    outdir = os.path.join(workdir, card_name)
    os.makedirs(outdir, exist_ok=True)
    out_root = os.path.join(outdir, 'events_delphes.root')

    script = '''
source {cmsset}
ln -sf {delphes}/MinBias_100k.pileup .
rm -f {out}
{delphes}/DelphesHepMC2 {card} {out} {hepmc}
'''.format(cmsset=CMSSET_DEFAULT, delphes=DELPHES_PATH, card=card_path, out=out_root, hepmc=hepmc_path)
    run_bash(script, cwd=proc_base, label='Delphes ({})'.format(card_name))

    if not os.path.exists(out_root):
        raise RuntimeError('DelphesHepMC2 did not produce {}'.format(out_root))
    return out_root


def count_delphes_stages(events_delphes_path, jet_branch, pt_cut, eta_cut):
    '''Run count_delphes_jets.C on events_delphes_path, return its parsed KEY->value dict.'''
    call = 'count_delphes_jets.C++("{}", "{}", {}, {})'.format(events_delphes_path, jet_branch, pt_cut, eta_cut)
    # single-quote (not double-quote) the whole call when embedding it in the
    # bash script below: `call` itself contains double quotes (the TString
    # arguments), and double-quoting around it here would need those escaped
    # (like run.sh's own makeNtuples.C++ call does with \") - single-quoting
    # instead passes it through to root verbatim, no escaping needed, since
    # `call` never contains a single quote itself
    script = '''
cd {macrodir}
source {lcg} > /dev/null 2>&1
export ROOT_INCLUDE_PATH=$ROOT_INCLUDE_PATH:{delphes_inc}
root -b -q '{call}'
'''.format(macrodir=THISDIR, lcg=LCG_SETUP, delphes_inc=DELPHES_ROOT_INCLUDE, call=call)
    out = run_bash_lenient(script, label='count_delphes_jets.C ({})'.format(events_delphes_path))
    values = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[0].isupper():
            try:
                values[parts[0]] = float(parts[1])
            except ValueError:
                pass
    for required in ('NEVENTS', 'STAGE_A', 'STAGE_B', 'PT_MEAN', 'PT_MEDIAN', 'PFCAND_MEAN'):
        if required not in values:
            raise RuntimeError('count_delphes_jets.C output did not contain {!r} - full output:\n{}'.format(
                required, out))
    return values


def run_ntuplizer(events_delphes_path, workdir, use_v1_labels, tag):
    '''
    Run the real, unmodified delphes_analyzers/makeNtuples.C - same call as
    run.sh's own - in an isolated per-card copy (same reasoning as run.sh:
    avoids ACLiC compilation races). Returns the resulting ntuple path.
    '''
    analyzer_dir = os.path.join(workdir, 'analyzer_' + tag)
    os.makedirs(analyzer_dir, exist_ok=True)
    for fname in ('EventData.h', 'FatJetMatching.h', 'ParticleID.h', 'ParticleInfo.h', 'makeNtuples.C'):
        shutil.copy(os.path.join(DELPHES_ANALYZERS_DIR, fname), analyzer_dir)

    ntuple_path = os.path.join(workdir, '{}_ntuple.root'.format(tag))
    call = 'makeNtuples.C++("{}", "{}", "JetPUPPIAK8", "GenJetAK8", true, false, {})'.format(
        events_delphes_path, ntuple_path, 'true' if use_v1_labels else 'false')
    # single-quoted for the same reason as count_delphes_stages() above
    script = '''
cd {analyzer_dir}
source {lcg} > /dev/null 2>&1
export ROOT_INCLUDE_PATH=$ROOT_INCLUDE_PATH:{delphes_inc}
root -b -q '{call}'
'''.format(analyzer_dir=analyzer_dir, lcg=LCG_SETUP, delphes_inc=DELPHES_ROOT_INCLUDE, call=call)
    # lenient (see run_bash_lenient docstring) - same as run.sh's own
    # makeNtuples.C++ call, which doesn't check root's exit code either,
    # only whether the output file actually landed (checked right below)
    run_bash_lenient(script, label='makeNtuples.C++ ({})'.format(tag))

    if not os.path.exists(ntuple_path):
        raise RuntimeError('makeNtuples.C did not produce {}'.format(ntuple_path))
    return ntuple_path


def count_tree_entries(root_path, tree_name='tree'):
    '''
    Just a plain entry count of a plain (no Delphes classes involved) tree -
    read via uproot (see print_njets.py) instead of a `root` subprocess:
    faster, and sidesteps the exit-code quirk documented on
    run_bash_lenient() above entirely rather than working around it.
    '''
    with uproot.open(root_path) as f:
        return f[tree_name].num_entries


def print_report(proc_short, nevent, pt_cut, eta_cut, results, card_order):
    print()
    print('=' * 100)
    print('HLT vs offline jet-loss breakdown - proc={} nevent={} pt_cut={} eta_cut={}'.format(
        proc_short, nevent, pt_cut, eta_cut))
    print('=' * 100)
    header = '{:<20}{:>10}{:>16}{:>16}{:>16}{:>12}{:>12}{:>14}'.format(
        'card', 'nevents', 'A: clustered', 'B: pt/eta cut', 'C: final', 'pt_mean', 'pt_median', 'pfcand/evt')
    print(header)
    print('-' * len(header))
    for card in card_order:
        r = results[card]
        print('{:<20}{:>10.0f}{:>16.0f}{:>16.0f}{:>16.0f}{:>12.1f}{:>12.1f}{:>14.1f}'.format(
            card, r['NEVENTS'], r['STAGE_A'], r['STAGE_B'], r['STAGE_C'], r['PT_MEAN'], r['PT_MEDIAN'],
            r['PFCAND_MEAN']))
    print()

    if len(card_order) == 2:
        c0, c1 = card_order
        r0, r1 = results[c0], results[c1]
        print('{} vs {}:'.format(c1, c0))

        def pct(a, b):
            return 100.0 * a / b if b else float('nan')

        a_ratio = pct(r1['STAGE_A'], r0['STAGE_A'])
        b_of_a_0 = pct(r0['STAGE_B'], r0['STAGE_A'])
        b_of_a_1 = pct(r1['STAGE_B'], r1['STAGE_A'])
        c_of_b_0 = pct(r0['STAGE_C'], r0['STAGE_B'])
        c_of_b_1 = pct(r1['STAGE_C'], r1['STAGE_B'])
        print('  STAGE_A ({}) is {:.1f}% of STAGE_A ({}) - i.e. clustering itself finds {} as many jets'.format(
            c1, a_ratio, c0, 'about' if 90 < a_ratio < 110 else ('far fewer' if a_ratio < 90 else 'more')))
        print('  fraction of STAGE_A jets surviving the pt/eta cut (STAGE_B/STAGE_A): {:.1f}% ({}) vs {:.1f}% ({})'.format(
            b_of_a_0, c0, b_of_a_1, c1))
        print('  fraction of STAGE_B jets surviving label-matching (STAGE_C/STAGE_B): {:.1f}% ({}) vs {:.1f}% ({})'.format(
            c_of_b_0, c0, c_of_b_1, c1))
        print()
        if a_ratio < 90:
            print('  -> a substantial chunk of the loss already happens at clustering (STAGE_A itself is'
                  ' smaller) - jets are genuinely not forming in the first place for {}, not merely being'
                  ' cut afterward.'.format(c1))
        else:
            print('  -> STAGE_A is comparable between cards - jets DO cluster about as often, but a larger'
                  ' fraction of {}\'s clustered jets then fail the (identical) pt/eta cut, consistent with'
                  ' its lower PT_MEAN/PT_MEDIAN above (a JES-correction effect, not a different cut).'.format(c1))
    print('=' * 100)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--proc', default=DEFAULT_PROC,
        help='jetclass1 process, e.g. TTBarLep or jetclass1/TTBarLep (default: {})'.format(DEFAULT_PROC))
    parser.add_argument('--nevent', type=int, default=DEFAULT_NEVENT,
        help='number of GEN events to generate ONCE and reuse for every card (default: {})'.format(DEFAULT_NEVENT))
    parser.add_argument('--cards', default=DEFAULT_CARDS,
        help='comma-separated Delphes card names to compare (default: {}) - the report\'s'
             ' card-vs-card verdict only applies with exactly 2 cards'.format(DEFAULT_CARDS))
    parser.add_argument('--pt-cut', type=float, default=120.0,
        help='STAGE_B pt cut in GeV - must match makeNtuples.C\'s own hardcoded cut to be meaningful (default: 120)')
    parser.add_argument('--eta-cut', type=float, default=2.5,
        help='STAGE_B |eta| cut - must match makeNtuples.C\'s own hardcoded cut to be meaningful (default: 2.5)')
    parser.add_argument('--workdir', default=None,
        help='directory to run in (default: a fresh temp dir, removed afterward unless --keep)')
    parser.add_argument('--keep', action='store_true',
        help='keep --workdir (events.hepmc, events_delphes.root, ntuple.root per card) instead of deleting it')
    args = parser.parse_args()

    proc_short = normalize_proc(args.proc)
    proc_full = 'jetclass1/{}/precompiled'.format(proc_short)
    # this script only supports the jetclass1 hierarchy (matching the
    # output_jetclass1_10M production run it was written to cross-check) -
    # jetclass1/* always uses the v1 label scheme, same as run.sh's own case
    # statement on PROC
    use_v1_labels = True

    cards = [c.strip() for c in args.cards.split(',') if c.strip()]
    if not cards:
        raise Exception('--cards did not contain any card names')

    own_workdir = args.workdir is None
    workdir = args.workdir or tempfile.mkdtemp(prefix='test_hlt_vs_offline_njets_')
    os.makedirs(workdir, exist_ok=True)
    print('workdir: {}'.format(workdir))

    try:
        hepmc_path, proc_base = generate_events(proc_full, args.nevent, workdir)

        results = {}
        for card in cards:
            delphes_root = run_delphes(card, hepmc_path, proc_base, workdir)
            stages_ab = count_delphes_stages(delphes_root, 'JetPUPPIAK8', args.pt_cut, args.eta_cut)
            ntuple_path = run_ntuplizer(delphes_root, workdir, use_v1_labels, tag=card)
            stage_c = count_tree_entries(ntuple_path)
            results[card] = dict(stages_ab)
            results[card]['STAGE_C'] = stage_c

        print_report(proc_short, args.nevent, args.pt_cut, args.eta_cut, results, cards)
    finally:
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)
        elif own_workdir:
            print('kept workdir: {}'.format(workdir))
