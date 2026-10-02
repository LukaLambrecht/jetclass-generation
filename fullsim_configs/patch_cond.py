"""Make CMS FullSim run for 2018 using ONLY openly available conditions.

Applied to any cmsDriver-generated config with

    import patch_cond; process = patch_cond.apply(process)

and, for the HLT step, additionally patch_cond.prune_hlt(process).

Nothing here needs a CERN account or CMS membership: the conditions are the two
open-data condition databases (see fullsim_configs/README.md for where they come
from and how to copy them anywhere), pointed at by FULLSIM_CONDDB.

What it does, and why each piece is needed (all found empirically, 2026-10-02):
 1. point the GlobalTag at the open condition sqlite files;
 2. push snapshotTime into the future: the open 102X snapshot was taken
    (2018-10-01) BEFORE its own tags were re-inserted (2018-10-30), so with the
    stored snapshot time CMSSW sees no valid IOV for ANY record - this single
    setting is the difference between "the 2018 open conditions are unusable"
    and "everything works";
 3. fill the gaps of the trimmed 2018 tag from the open 2016 UL MC tag - the
    2018 snapshot was prepared for MiniAOD analysis and misses simulation
    payloads (EcalSimPulseShape, SiStripApvSimulationParameters), the e/gamma
    regressions and the b-tag payloads. Only records the 2018 tag does not have
    AT ALL are taken from 2016, so no geometry, alignment or channel-status
    payload ever comes from the wrong year;
 4. override the PF calibration payloads: the 2018 tag's '...newCodeCompliant'
    encoding makes PFProducer assert in CMSSW_10_6_30 (offline and HLT). The
    2018 and 2016 payloads are the same 2017 calibration vintage in two
    different encodings;
 5. map SiPixelQuality to the 'forDigitizer' label the digitiser asks for (the
    snapshot keeps only the default label);
 6. switch off the 2018 'bad FED channel' simulation
    (SiPixelStatusScenarioProbabilityRcd is not in the open conditions; these
    are design conditions, i.e. an ideal detector, anyway);
 7. drop GEM (no GEMeMapRcd in the open conditions; irrelevant for jets).

set_beamspot() fixes a separate, easily-missed problem - see its own docstring.
"""
import os
import math
import FWCore.ParameterSet.Config as cms

# Where the open condition sqlite files are. The default is the public CVMFS
# mirror; set FULLSIM_CONDDB to a plain directory holding the same .db files to
# run somewhere without CVMFS (they are ~1.7 GB in total, see README.md).
CONDDB = os.environ.get('FULLSIM_CONDDB', '/cvmfs/cms-opendata-conddb.cern.ch')
GT = '102X_upgrade2018_design_v9'
GT_FALLBACK = '106X_mcRun2_asymptotic_v17'
SNAPSHOT = '2030-01-01 00:00:00.000'

# The vertex smearing the GEN step uses. Kept here, rather than in the cmsDriver
# command line, so that set_beamspot() below can read the ACTUAL numbers out of
# the corresponding cfi instead of a second, hand-copied set that could drift.
BEAMSPOT_NAME = 'Realistic25ns13TeVEarly2018Collision'

# (record, label, tag, source db) overridden explicitly rather than gap-filled
EXPLICIT = [
    ('PFCalibrationRcd', '', 'PFCalibration_UL2016_mc', GT_FALLBACK),
    ('PFCalibrationRcd', 'HLT', 'PFCalibration_2017_25ns_Spring17_v3_hlt', GT_FALLBACK),
    ('SiPixelQualityFromDbRcd', 'forDigitizer', 'SiPixelQuality_phase1_ideal', GT),
]


def _db(name):
    return 'sqlite_file:%s/%s.db' % (CONDDB, name)


def _gt_map(db):
    """{(record, label): tag} of a global tag, read straight out of its sqlite."""
    import sqlite3
    path = '%s/%s.db' % (CONDDB, db)
    try:  # python3
        c = sqlite3.connect('file:%s?mode=ro' % path, uri=True)
    except TypeError:  # python2 (CMSSW_10_6 configs) has no uri= support
        c = sqlite3.connect(path)
    out = {}
    for rec, tag, lab in c.execute("select record, tag_name, label from GLOBAL_TAG_MAP"):
        out[(str(rec), '' if lab in (None, '-') else str(lab))] = str(tag)
    c.close()
    return out


def apply(process):
    process.GlobalTag.connect = cms.string(_db(GT))
    process.GlobalTag.snapshotTime = cms.string(SNAPSHOT)

    toGet = []
    for rec, lab, tag, db in EXPLICIT:
        ps = cms.PSet(record=cms.string(rec), tag=cms.string(tag), connect=cms.string(_db(db)))
        if lab:
            ps.label = cms.untracked.string(lab)
        toGet.append(ps)

    try:
        main, fallback = _gt_map(GT), _gt_map(GT_FALLBACK)
        explicit_keys = set((r, l) for r, l, _t, _d in EXPLICIT)
        missing = sorted(k for k in fallback if k not in main and k not in explicit_keys)
        for rec, lab in missing:
            ps = cms.PSet(record=cms.string(rec), tag=cms.string(fallback[(rec, lab)]),
                          connect=cms.string(_db(GT_FALLBACK)))
            if lab:
                ps.label = cms.untracked.string(lab)
            toGet.append(ps)
        print('[patch_cond] %d explicit overrides + %d records gap-filled from %s'
              % (len(EXPLICIT), len(missing), GT_FALLBACK))
    except Exception as e:
        # Loud, because a silently skipped gap-fill shows up much later as a
        # missing-record exception in an unrelated-looking module
        print('[patch_cond] WARNING: could not gap-fill automatically (%s)' % e)
    process.GlobalTag.toGet = cms.VPSet(*toGet)

    if hasattr(process, 'mix') and hasattr(process.mix, 'digitizers') \
            and hasattr(process.mix.digitizers, 'pixel'):
        process.mix.digitizers.pixel.KillBadFEDChannels = cms.bool(False)

    for m in ['gemPacker', 'muonGEMDigis', 'gemRecHits', 'gemSegments']:
        remove_module(process, m)
    return process


def remove_module(process, name):
    """Remove a module from every sequence/task/path it appears in (if present)."""
    if not hasattr(process, name):
        return
    mod = getattr(process, name)
    for coll in (process.sequences_(), process.tasks_(), process.paths_(), process.endpaths_()):
        for _k, v in coll.items():
            try:
                v.remove(mod)
            except Exception:
                pass


# kept as the old private name too, since the generator patch used to call it
_remove_module = remove_module


def simulated_beamspot():
    """The beamspot the GEN step actually simulates, read from its own cfi."""
    import importlib
    mod = importlib.import_module(
        'IOMC.EventVertexGenerators.VtxSmeared%s_cfi' % BEAMSPOT_NAME)
    p = mod.VtxSmeared
    width = math.sqrt(p.Emittance.value() * p.BetaStar.value())
    return dict(X0=p.X0.value(), Y0=p.Y0.value(), Z0=p.Z0.value(),
                sigmaZ=p.SigmaZ.value(), widthX=width, widthY=width)


def set_beamspot(process, **kw):
    """Make the RECONSTRUCTED beamspot match the SIMULATED one.

    Needed because the open 2018 conditions are DESIGN conditions: their
    BeamSpotObjects sits at the origin with a 15 um width, while the standard
    2018 vertex smearing puts collisions 108 um / 417 um away in x / y - i.e. 7
    and 28 'sigma' off the beam the reconstruction assumes. Offline track
    selection and primary-vertex clustering use that beamspot, so with the
    mismatch the hard interaction is split into several low-ndof vertices and
    EVERY offline impact parameter is measured from a wrong point (median |d0|
    0.35 mm instead of 0.011 mm, measured on 2 QCD events; the offline vertex
    also disagrees with the HLT one). HLT tracking is barely affected - its
    regions are wide enough that it finds the vertex correctly either way - but
    this is applied in every step, since there is no reason not to.

    Done with the BeamSpotFakeConditions ESSource, which takes the beamspot from
    the configuration, so no new condition payload has to be produced.
    """
    p = simulated_beamspot()
    p.update(kw)
    process.BeamSpotFakeConditions = cms.ESSource(
        "BeamSpotFakeConditions",
        getDataFromFile=cms.bool(False),
        InputFilename=cms.FileInPath("RecoVertex/BeamSpotProducer/test/EarlyCollision.txt"),
        X0=cms.double(p['X0']), Y0=cms.double(p['Y0']), Z0=cms.double(p['Z0']),
        dxdz=cms.double(0.), dydz=cms.double(0.),
        sigmaZ=cms.double(p['sigmaZ']),
        widthX=cms.double(p['widthX']), widthY=cms.double(p['widthY']),
        emittanceX=cms.double(0.), emittanceY=cms.double(0.), betaStar=cms.double(0.),
        errorX0=cms.double(1e-4), errorY0=cms.double(1e-4), errorZ0=cms.double(1e-3),
        errordxdz=cms.double(1e-6), errordydz=cms.double(1e-6),
        errorSigmaZ=cms.double(1e-2), errorWidth=cms.double(1e-5))
    process.es_prefer_BeamSpotFakeConditions = cms.ESPrefer("BeamSpotFakeConditions")
    print('[patch_cond] beamspot set to the simulated one (%s): x=%.5f y=%.5f z=%.5f cm, width=%.1f um'
          % (BEAMSPOT_NAME, p['X0'], p['Y0'], p['Z0'], p['widthX'] * 1e4))
    return process


def prune_hlt(process, keep=('HT410_PFScouting', 'CaloJet40_CaloScouting_PFScouting',
                             'HT250_CaloScouting'),
              drop_endpaths=('HLTAnalyzerEndpath',)):
    """Keep only the named HLT paths (plus the DIGI/L1/output steps).

    The GRun menu shipped in CMSSW_10_6_30 is newer than the 2018 L1 menu in the
    open conditions, so unrelated paths request L1 seeds (Run-3 style names) that
    do not exist there and the job dies on the first event. The hadronic
    PF-scouting paths use Run-2 seeds that do exist. Note that the jets we
    actually ntuplize do NOT come from any of these paths - patch_hlt.py adds
    its own, unconditional one - these are kept only so that the scouting
    products are in the file as well, for comparison.
    """
    names = {}
    for n, o in list(process.paths_().items()) + list(process.endpaths_().items()):
        names[id(o)] = n
    new = []
    for item in process.schedule:
        n = names.get(id(item))
        if n is None:
            new.append(item)
            continue
        if n in drop_endpaths:
            continue
        if n.startswith(('HLT_', 'DST_', 'AlCa_', 'MC_')) and not any(k in n for k in keep):
            continue
        new.append(item)
    print('[prune_hlt] keeping:', [names.get(id(i)) for i in new if names.get(id(i))])
    process.schedule = cms.Schedule(*new, tasks=list(getattr(process.schedule, '_tasks', [])))
    return process
