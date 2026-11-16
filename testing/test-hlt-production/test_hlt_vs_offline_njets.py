#!/usr/bin/env python3

'''Check where HLT-card jets get lost relative to offline-card jets.

Generates a small number of GEN events once and runs the same events.hepmc through both
an offline and an HLT Delphes card, exactly as run.sh does, so any difference between
the cards comes only from their detector modelling and not from different collisions.

Two things are measured:

  - Delphes-level clustering, per card independently (see count_delphes_jets.C):
      STAGE_A "clustered"  - entries in the raw Delphes jet branch, i.e. how many jets
                             the clustering found at all. Its pT cut is identical in
                             every card, but the stored PT is after the jet energy
                             scale correction, which is not.
      STAGE_B "pt/eta cut" - of those, how many pass the ntuplizer's own cut, also
                             identical in every card.
    This part is a property of each card's own clustering, upstream of any
    offline-to-HLT correspondence.

  - The actual correspondence, from one paired ntuple rather than by diffing two
    independently produced ones with no shared jet indexing: one row per selected
    offline jet, carrying its own branches plus its matched HLT jet's, or hlt_matched
    false where none was found.
'''

import os
import sys
import argparse
import shutil
import subprocess
import tempfile

import numpy as np
import uproot

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(os.path.dirname(THISDIR))  # testing/test-hlt-production/ is two levels below the repo root

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
DEFAULT_CARD_PAIR = 'onlyFatJetNoPU+onlyFatJetHLTNoPU'
# ======================================================================================


def normalize_proc(proc):
    '''Accept a process in either family, with or without its family prefix, and return
    (short, full, use_v1_labels).
    '''
    parts = [p for p in proc.split('/') if p and p != 'precompiled']
    if parts and parts[0] in ('jetclass1', 'jetclass2'):
        family, rest = parts[0], parts[1:]
    else:
        rest = parts
        family = 'jetclass2' if rest and rest[0].startswith('train_') else 'jetclass1'
    if len(rest) != 1:
        raise ValueError('could not parse a single process name out of {!r}'.format(proc))
    short = rest[0]
    full = 'jetclass1/{}/precompiled'.format(short) if family == 'jetclass1' else 'jetclass2/{}'.format(short)
    return short, full, family == 'jetclass1'


def run_bash(script, cwd=None, label=''):
    '''Run a bash script, streaming its output live. Raises on failure.'''
    print('--- running: {} ---'.format(label))
    result = subprocess.run(['bash', '-c', 'set -e\n' + script], cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError('{} failed with exit code {}'.format(label, result.returncode))


def run_bash_lenient(script, label=''):
    '''Run a bash script and return its stdout, without treating a nonzero exit as failure.

    Needed because root can exit nonzero on interpreter shutdown even after printing its
    results correctly.
    '''
    print('--- running: {} ---'.format(label))
    result = subprocess.run(['bash', '-c', script], capture_output=True, text=True)
    if result.stderr.strip():
        sys.stderr.write('--- {} stderr ---\n{}\n'.format(label, result.stderr))
    return result.stdout


def generate_events(proc_full, nevent, workdir):
    '''Set up a fresh proc_base, as run.sh does, and generate `nevent` GEN events into it.
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
    '''Run DelphesHepMC2 with `card_name` on hepmc_path, the same call run.sh makes.'''
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
    '''Run count_delphes_jets.C and return its parsed KEY -> value dict.'''
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


def run_ntuplizer_paired(offline_delphes_path, hlt_delphes_path, workdir, use_v1_labels):
    '''Run the real makeNtuplesPaired.C, as run.sh's offline+HLT branch does, in an isolated
    workdir copy so ACLiC compilation cannot race with other jobs.
    '''
    analyzer_dir = os.path.join(workdir, 'analyzer_paired')
    os.makedirs(analyzer_dir, exist_ok=True)
    for fname in ('EventData.h', 'FatJetMatching.h', 'ParticleID.h', 'ParticleInfo.h', 'makeNtuplesPaired.C'):
        shutil.copy(os.path.join(DELPHES_ANALYZERS_DIR, fname), analyzer_dir)

    ntuple_path = os.path.join(workdir, 'paired_ntuple.root')
    call = 'makeNtuplesPaired.C++("{}", "{}", "{}", "JetPUPPIAK8", "GenJetAK8", true, false, {})'.format(
        offline_delphes_path, hlt_delphes_path, ntuple_path, 'true' if use_v1_labels else 'false')
    # single-quoted for the same reason as count_delphes_stages() above
    script = '''
cd {analyzer_dir}
source {lcg} > /dev/null 2>&1
export ROOT_INCLUDE_PATH=$ROOT_INCLUDE_PATH:{delphes_inc}
root -b -q '{call}'
'''.format(analyzer_dir=analyzer_dir, lcg=LCG_SETUP, delphes_inc=DELPHES_ROOT_INCLUDE, call=call)
    # lenient (see run_bash_lenient docstring) - same as run.sh's own
    # makeNtuplesPaired.C++ call, which doesn't check root's exit code
    # either, only whether the output file actually landed (checked below)
    run_bash_lenient(script, label='makeNtuplesPaired.C++')

    if not os.path.exists(ntuple_path):
        raise RuntimeError('makeNtuplesPaired.C did not produce {}'.format(ntuple_path))
    return ntuple_path


def read_paired_ntuple(root_path, tree_name='tree'):
    '''Read the branches needed for the offline-against-HLT summary out of the paired ntuple.
    '''
    with uproot.open(root_path) as f:
        arrays = f[tree_name].arrays(
            ['jet_pt', 'hlt_matched', 'hlt_jet_pt', 'hlt_jet_dr_offline'], library='np')
    return arrays


def print_report(proc_short, nevent, offline_card, hlt_card, pt_cut, eta_cut, stages, paired):
    '''Print the per-card stage counts and the offline-to-HLT matching summary.'''
    print()
    print('=' * 100)
    print('HLT vs offline jet-loss breakdown (paired) - proc={} nevent={} offline_card={} hlt_card={}'
          ' pt_cut={} eta_cut={}'.format(proc_short, nevent, offline_card, hlt_card, pt_cut, eta_cut))
    print('=' * 100)

    print('Delphes-level clustering (per card, independent - see count_delphes_jets.C):')
    header = '{:<20}{:>10}{:>16}{:>16}{:>12}{:>12}{:>14}'.format(
        'card', 'nevents', 'A: clustered', 'B: pt/eta cut', 'pt_mean', 'pt_median', 'pfcand/evt')
    print(header)
    print('-' * len(header))
    for card in (offline_card, hlt_card):
        r = stages[card]
        print('{:<20}{:>10.0f}{:>16.0f}{:>16.0f}{:>12.1f}{:>12.1f}{:>14.1f}'.format(
            card, r['NEVENTS'], r['STAGE_A'], r['STAGE_B'], r['PT_MEAN'], r['PT_MEDIAN'], r['PFCAND_MEAN']))
    a_ratio = 100.0 * stages[hlt_card]['STAGE_A'] / stages[offline_card]['STAGE_A'] \
        if stages[offline_card]['STAGE_A'] else float('nan')
    print('  {} STAGE_A is {:.1f}% of {} STAGE_A - i.e. clustering itself finds {} as many jets'.format(
        hlt_card, a_ratio, offline_card, 'about' if 90 < a_ratio < 110 else ('far fewer' if a_ratio < 90 else 'more')))

    print()
    print('Paired final-ntuple matching (one row per selected OFFLINE jet - see makeNtuplesPaired.C):')
    n_offline = len(paired['jet_pt'])
    matched = paired['hlt_matched'].astype(bool)
    n_matched = int(matched.sum())
    n_unmatched = n_offline - n_matched
    print('  offline final jets (STAGE_C):        {}'.format(n_offline))
    print('  matched to an HLT jet:                {}  ({:.1f}%)'.format(
        n_matched, 100.0 * n_matched / n_offline if n_offline else 0))
    print('  unmatched (HLT jet lost entirely):    {}  ({:.1f}%)'.format(
        n_unmatched, 100.0 * n_unmatched / n_offline if n_offline else 0))
    if n_matched:
        offline_pt_matched = paired['jet_pt'][matched]
        hlt_pt_matched = paired['hlt_jet_pt'][matched]
        dr_matched = paired['hlt_jet_dr_offline'][matched]
        print('  offline jet pt   [matched only]: mean={:.1f}  median={:.1f}'.format(
            np.mean(offline_pt_matched), np.median(offline_pt_matched)))
        print('  hlt jet pt       [matched only]: mean={:.1f}  median={:.1f}'.format(
            np.mean(hlt_pt_matched), np.median(hlt_pt_matched)))
        print('  dr(hlt, offline) [matched only]: mean={:.3f}  median={:.3f}'.format(
            np.mean(dr_matched), np.median(dr_matched)))
    print('=' * 100)


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--proc', default=DEFAULT_PROC,
        help='jetclass1 or jetclass2 process, e.g. "TTBarLep"/"jetclass1/HToBB" or "train_higgs2p"/'
             '"jetclass2/train_qcd" - label scheme (v1 vs v2) follows the family, same as run.sh'
             ' (default: {})'.format(DEFAULT_PROC))
    parser.add_argument('--nevent', type=int, default=DEFAULT_NEVENT,
        help='number of GEN events to generate ONCE and reuse for both cards (default: {})'.format(DEFAULT_NEVENT))
    parser.add_argument('--cards', default=DEFAULT_CARD_PAIR,
        help='"+"-joined offline+HLT Delphes card pair (same convention as run.sh\'s own'
             ' DELPHES_CARD_NAMES pair syntax), e.g. "onlyFatJetNoPU+onlyFatJetHLTNoPU"'
             ' (default: {})'.format(DEFAULT_CARD_PAIR))
    parser.add_argument('--hlt-match-dr', type=float, default=-1,
        help='max deltaR for matching an HLT jet to an offline jet in makeNtuplesPaired.C'
             ' (default: -1, meaning that macro\'s own default of jetR - see its docstring)')
    parser.add_argument('--pt-cut', type=float, default=120.0,
        help='STAGE_B pt cut in GeV - must match makeNtuplesPaired.C\'s own hardcoded cut to be meaningful (default: 120)')
    parser.add_argument('--eta-cut', type=float, default=2.5,
        help='STAGE_B |eta| cut - must match makeNtuplesPaired.C\'s own hardcoded cut to be meaningful (default: 2.5)')
    parser.add_argument('--workdir', default=None,
        help='directory to run in (default: a fresh temp dir, removed afterward unless --keep)')
    parser.add_argument('--keep', action='store_true',
        help='keep --workdir (events.hepmc, events_delphes*.root, paired_ntuple.root) instead of deleting it')
    args = parser.parse_args()

    proc_short, proc_full, use_v1_labels = normalize_proc(args.proc)

    card_parts = [c.strip() for c in args.cards.split('+') if c.strip()]
    if len(card_parts) != 2:
        raise Exception('--cards must be exactly one "+"-joined offline+HLT pair, e.g.'
                         ' "onlyFatJetNoPU+onlyFatJetHLTNoPU" - got {!r}'.format(args.cards))
    offline_card, hlt_card = card_parts

    own_workdir = args.workdir is None
    workdir = args.workdir or tempfile.mkdtemp(prefix='test_hlt_vs_offline_njets_')
    os.makedirs(workdir, exist_ok=True)
    print('workdir: {}'.format(workdir))

    try:
        hepmc_path, proc_base = generate_events(proc_full, args.nevent, workdir)

        stages = {}
        delphes_paths = {}
        for card in (offline_card, hlt_card):
            delphes_root = run_delphes(card, hepmc_path, proc_base, workdir)
            delphes_paths[card] = delphes_root
            stages[card] = count_delphes_stages(delphes_root, 'JetPUPPIAK8', args.pt_cut, args.eta_cut)

        ntuple_path = run_ntuplizer_paired(delphes_paths[offline_card], delphes_paths[hlt_card], workdir, use_v1_labels)
        paired = read_paired_ntuple(ntuple_path)

        print_report(proc_short, args.nevent, offline_card, hlt_card, args.pt_cut, args.eta_cut, stages, paired)
    finally:
        if not args.keep:
            shutil.rmtree(workdir, ignore_errors=True)
        elif own_workdir:
            print('kept workdir: {}'.format(workdir))
