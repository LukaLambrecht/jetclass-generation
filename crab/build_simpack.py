#!/usr/bin/env python3

'''
Assemble a "simpack": one self-contained directory holding everything a CRAB job
needs to run the fullsim chain, plus the CRAB config to submit it.

Why a simpack rather than submitting the repo: CRAB ships `JobType.inputFiles` to
every worker node, so the job has to be given an explicit, closed set of files. The
layout mirrors what backends/fullsim.sh builds locally, so run_chain.sh runs
unmodified on the grid:

    <simpack>/
        crab_config.py       rendered from crab/templates/
        crab_submit.sh
        pset.py              dummy; CRAB reads the output file name from it
        run_in_container.sh  scriptExe: launches the container on the worker node
        run_job.sh           inside the container: run_chain.sh setup + batches + hadd
        payload/cfg/         patch_*.py, run_chain.sh, <fragment>.py  (fragment processes)
        payload/gen/         mg5_*.dat, py8.dat, run_gen.sh            (hepmc processes)
        payload/ana/         ntuplizer sources (shared headers included)

Both process kinds are supported, detected exactly as run.sh detects them:
  * a process WITH gen_configs/<proc>/fragment.py (jetclass2sb/*) has CMSSW generate
    its own events - nothing else is needed;
  * a process WITHOUT one (jetclass2/*) needs a standalone MadGraph5 + Pythia8 run
    first, writing events.hepmc. The MG5 install is fetched over xrootd at job start
    (see --mg5-url and crab/make_mg5_tarball.sh) because it is ~850 MB and the CVMFS
    copy is a different major version.

The one site-dependent prerequisite is /cvmfs/cms-opendata-conddb.cern.ch, which is
NOT in the cern.ch domain config that grid sites auto-mount, and at ~1.6 GB cannot be
shipped in the sandbox. run_job.sh therefore checks for it and exits 65 immediately if
it is missing, and falls back to fetching them from the CERN Open Data portal over
xrootd, so NO site whitelist is required (see crab/README.md "Conditions"). The
optional site probe, which measures which sites avoid that download, lives in
crab/site-probe/.

Usage:
  # a real (small) production
  python3 build_simpack.py --proc jetclass2sb/QCD_PT-470to600 \\
      --njobs 2 --nevents-per-job 10 --batch-size 5 -o /tmp/simpack_test
'''

import os
import re
import shutil
import argparse

THISDIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(THISDIR)
TEMPLATES = os.path.join(THISDIR, 'templates')

# the conditions files the chain actually opens - see fullsim_configs/patch_cond.py
CONDDB_FILES = ['102X_upgrade2018_design_v9.db', '106X_mcRun2_asymptotic_v17.db']

INPUTFILES = ['run_job.sh', 'payload']   # what the job needs on the worker node

# Where a hepmc process gets MadGraph5 from. The install is ~850 MB (over the CRAB
# sandbox limit) and /cvmfs/cms.cern.ch has only madgraph5amcatnlo 2.x while this setup
# needs v3.7.2, so jobs fetch a staged tarball over xrootd. Make it with
# crab/make_mg5_tarball.sh.
DEFAULT_MG5_URL = ('root://eosuser.cern.ch//eos/user/{}/{}/jetclass/crab_inputs/'
                   'MG5_aMC_v3_7_2.tar.gz').format(os.environ.get('USER', 'x')[0],
                                                   os.environ.get('USER', 'x'))

CFG_FILES = ['patch_cond.py', 'patch_gen.py', 'patch_hlt.py', 'run_chain.sh']
ANA_FILES = [
    ('delphes_analyzers', 'EventData.h'),
    ('delphes_analyzers', 'FatJetMatching.h'),
    ('delphes_analyzers', 'ParticleID.h'),
    ('delphes_analyzers', 'ParticleInfo.h'),
    ('fullsim_analyzers', 'StandaloneTypes.h'),
    ('fullsim_analyzers', 'makeNtuplesFullSim.cc'),
    ('fullsim_analyzers', 'build.sh'),
]


def check_inputfiles(outdir, inputfiles):
    """CRAB refuses to submit if anything in JobType.inputFiles is missing, and the
    error surfaces only at submit time - after the simpack looks fine. Catch it here:
    a probe simpack listing 'payload' (which it has no reason to contain) is exactly
    how this went wrong once."""
    missing = [f for f in inputfiles if not os.path.exists(os.path.join(outdir, f))]
    if missing:
        raise Exception('simpack lists input file(s) it does not contain: {} - CRAB would '
                        'refuse to submit'.format(missing))


def render(src, dst, subs):
    with open(src) as f:
        text = f.read()
    for k, v in subs.items():
        text = text.replace(k, str(v))
    left = re.findall(r'__[A-Z_]+__', text)
    if left:
        raise Exception('{}: unsubstituted placeholders {}'.format(os.path.basename(src), sorted(set(left))))
    with open(dst, 'w') as f:
        f.write(text)
    shutil.copymode(src, dst)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('-o', '--outdir', required=True, help='simpack directory to create')
    p.add_argument('--proc', required=True,
                   help='process as run.sh takes it, e.g. jetclass2sb/QCD_PT-470to600')
    p.add_argument('--njobs', type=int, required=True, help='number of CRAB jobs')
    p.add_argument('--nevents-per-job', type=int, default=10)
    p.add_argument('--batch-size', type=int, default=None,
                   help='events per batch (must divide --nevents-per-job; default: half of it)')
    p.add_argument('--request-name', default=None, help='CRAB requestName (default: derived from --proc)')
    p.add_argument('--storage-site', default='T3_CH_CERNBOX')
    p.add_argument('--outlfn', default=None,
                   help='default: /store/user/<user>/jetclass/<requestName>')
    p.add_argument('--whitelist', default=None, help='comma-separated sites for config.Site.whitelist')
    p.add_argument('--blacklist', default=None, help='comma-separated sites for config.Site.blacklist')
    p.add_argument('--memory', type=int, default=2500,
                   help='maxMemoryMB (default 2500). CRAB REFUSES a 1-core task above 3000 - the '
                        'lxplus-condor default of 4096 is rejected. Measured peak usage was ~1.4 GB. '
                        'If jobs are ever held for memory, raise --cores rather than this.')
    p.add_argument('--cores', type=int, default=1,
                   help='numCores (default 1). The memory cap scales with cores, so 2 cores is the '
                        'way to get past 3000 MB if that is ever needed.')
    p.add_argument('--runtime-min', type=int, default=1315, help='maxJobRuntimeMin (default 1315 = 21.9 h)')
    p.add_argument('--jet-pt-min', type=float, default=200.)
    p.add_argument('--jet-eta-max', type=float, default=2.4)
    p.add_argument('--transfer-logs', action='store_true')
    p.add_argument('--mg5-url', default=DEFAULT_MG5_URL,
                   help='xrootd URL of the MG5 tarball, for processes WITHOUT a CMSSW GEN '
                        'fragment (PROC_KIND=hepmc). Ignored for fragment processes. '
                        'Default: {}'.format(DEFAULT_MG5_URL))
    args = p.parse_args()

    nev = args.nevents_per_job
    batch = args.batch_size or max(1, nev // 2)
    if nev % batch:
        raise Exception('--batch-size {} does not divide --nevents-per-job {} (run_chain.sh would drop '
                        'the remainder)'.format(batch, nev))

    # Same rule run.sh uses: a CMSSW GEN fragment means CMSSW generates the events
    # itself; otherwise MG5+Pythia8 must run first and hand over events.hepmc.
    procdir = os.path.join(REPO_DIR, 'gen_configs', args.proc)
    if not os.path.isdir(procdir):
        raise Exception('no such process: gen_configs/{}'.format(args.proc))
    has_fragment = os.path.exists(os.path.join(procdir, 'fragment.py'))
    family, procname = (args.proc.split('/', 1) + [''])[:2]
    if not procname:
        raise Exception('--proc must be <family>/<process>, e.g. jetclass2sb/QCD_PT-470to600')
    proc_kind = 'cmssw_fragment' if has_fragment else 'hepmc'
    fragname = re.sub(r'[^A-Za-z0-9_]', '_', args.proc)
    reqname = args.request_name or fragname
    user = os.environ.get('USER', 'unknown')
    # one base for a whole production; CRAB appends <family>/<proc>/... under it, so
    # the result is directly readable by the validation scripts
    outlfn = args.outlfn or '/store/user/{}/jetclass/{}/'.format(user, reqname)

    out = os.path.abspath(args.outdir)
    if os.path.exists(out):
        raise Exception('{} already exists - remove it or pick another --outdir'.format(out))
    os.makedirs(os.path.join(out, 'payload', 'cfg'))
    os.makedirs(os.path.join(out, 'payload', 'ana'))

    # ---- payload ----
    for f in CFG_FILES:
        shutil.copy(os.path.join(REPO_DIR, 'fullsim_configs', f), os.path.join(out, 'payload', 'cfg', f))
    for sub, f in ANA_FILES:
        shutil.copy(os.path.join(REPO_DIR, sub, f), os.path.join(out, 'payload', 'ana', f))
    if proc_kind == 'cmssw_fragment':
        shutil.copy(os.path.join(procdir, 'fragment.py'),
                    os.path.join(out, 'payload', 'cfg', fragname + '.py'))
    else:
        # the generator pack: every card in the process directory, plus the generation
        # driver. run.sh falls back to gen_configs/run_gen_default.sh when a process
        # has no run_gen.sh of its own - reproduce that choice here, once, so the job
        # does not have to.
        gendst = os.path.join(out, 'payload', 'gen')
        os.makedirs(gendst)
        for f in sorted(os.listdir(procdir)):
            src = os.path.join(procdir, f)
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(gendst, f))
        own = os.path.join(procdir, 'run_gen.sh')
        driver = own if os.path.exists(own) else os.path.join(REPO_DIR, 'gen_configs',
                                                              'run_gen_default.sh')
        shutil.copy(driver, os.path.join(gendst, 'run_gen.sh'))
        os.chmod(os.path.join(gendst, 'run_gen.sh'), 0o755)

    # ---- scripts ----
    jobsubs = {'__FRAGNAME__': fragname, '__JETPTMIN__': args.jet_pt_min,
               '__JETETAMAX__': args.jet_eta_max, '__CONDDB_FILES__': ' '.join(CONDDB_FILES),
               '__PROCKIND__': proc_kind, '__MG5_URL__': args.mg5_url}
    render(os.path.join(TEMPLATES, 'run_job.sh'), os.path.join(out, 'run_job.sh'), jobsubs)
    shutil.copy(os.path.join(TEMPLATES, 'run_in_container.sh'), os.path.join(out, 'run_in_container.sh'))
    render(os.path.join(TEMPLATES, 'pset.py'), os.path.join(out, 'pset.py'),
           {'__CORES__': args.cores})
    shutil.copy(os.path.join(TEMPLATES, 'crab_submit.sh'), os.path.join(out, 'crab_submit.sh'))
    # driver for any crab subcommand; crab/monitoring/ shells out to it per simpack
    shutil.copy(os.path.join(TEMPLATES, 'crab_command.sh'), os.path.join(out, 'crab_command.sh'))
    os.chmod(os.path.join(out, 'crab_command.sh'), 0o755)
    os.chmod(os.path.join(out, 'run_in_container.sh'), 0o755)
    os.chmod(os.path.join(out, 'crab_submit.sh'), 0o755)

    wl = []
    if args.whitelist:
        wl.append('config.Site.whitelist = {}'.format([s.strip() for s in args.whitelist.split(',') if s.strip()]))
    if args.blacklist:
        wl.append('config.Site.blacklist = {}'.format([s.strip() for s in args.blacklist.split(',') if s.strip()]))

    render(os.path.join(TEMPLATES, 'crab_config.py'), os.path.join(out, 'crab_config.py'), {
        '__REQUESTNAME__': reqname,
        '__NEVENTS__': nev,
        '__BATCH__': batch,
        '__NJOBS__': args.njobs,
        '__TOTALUNITS__': nev * args.njobs,
        '__OUTLFN__': outlfn,
        # CRAB writes <outLFNDirBase>/<primaryDataset>/<datasetTag>/<timestamp>/<counter>/.
        # Naming these after the family and the process makes that path parse exactly
        # like a local production - validation/print_njets.py splits the path relative
        # to --output-path as <family>/<proc>/.../<card>/ntuple_*.root and checks the
        # family against OURS_FAMILIES. Call the primary dataset 'JetClass2SB' instead
        # and every file is silently skipped.
        '__PRIMARYDS__': family,
        '__DATASETTAG__': procname,
        '__INPUTFILES__': INPUTFILES,
        '__MEMORY__': args.memory,
        '__CORES__': args.cores,
        '__RUNTIMEMIN__': args.runtime_min,
        '__STORAGESITE__': args.storage_site,
        '__TRANSFERLOGS__': 'True' if args.transfer_logs else 'False',
        '__WHITELIST__': '\n'.join(wl),
    })

    check_inputfiles(out, INPUTFILES)
    print('simpack written to {}'.format(out))
    print('  process   : {}  ({})'.format(args.proc, proc_kind))
    if proc_kind == 'hepmc':
        print('  MG5       : {}'.format(args.mg5_url))
    print('  jobs      : {} x {} events (batch {})'.format(args.njobs, nev, batch))
    print('  output    : {} at {}'.format(outlfn, args.storage_site))
    if wl:
        print('  ' + '\n  '.join(wl))
    print('\nsubmit with:\n  cd {} && ./crab_submit.sh'.format(out))
