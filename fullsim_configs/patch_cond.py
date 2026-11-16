"""Make CMS FullSim run for 2018 using only openly available conditions.

Applied to any cmsDriver-generated config with

    import patch_cond; process = patch_cond.apply(process)

and, for the HLT step, additionally patch_cond.prune_hlt(process).

Nothing here needs a CERN account or CMS membership: the conditions are the two
open-data condition databases, pointed at by FULLSIM_CONDDB.

What it does, and why each piece is needed:
 1. point the GlobalTag at the open condition sqlite files;
 2. push snapshotTime into the future, because the open snapshot was taken before its
    own tags were re-inserted, so with the stored time CMSSW sees no valid IOV for any
    record at all - this one setting is the difference between the conditions being
    unusable and everything working;
 3. fill the gaps of the trimmed 2018 tag from the open 2016 UL MC tag, since the 2018
    snapshot was prepared for analysis and misses simulation payloads, the e/gamma
    regressions and the b-tag payloads. Only records the 2018 tag lacks entirely are
    taken from 2016, so no geometry, alignment or channel-status payload ever comes
    from the wrong year;
 4. override the PF calibration payloads, whose 2018 encoding makes PFProducer assert;
    the two years' payloads are the same calibration vintage in different encodings;
 5. map SiPixelQuality to the 'forDigitizer' label the digitiser asks for, which the
    snapshot does not carry;
 6. switch off the bad-FED-channel simulation, whose record is not in the open
    conditions and which is meaningless for design conditions anyway;
 7. drop GEM, whose map is not in the open conditions and which is irrelevant for jets.

set_beamspot() fixes a separate, easily-missed problem; see its own docstring.
"""
import os
import math
import FWCore.ParameterSet.Config as cms

# Where the open condition sqlite files are. The default is the public CVMFS mirror;
# set FULLSIM_CONDDB to a plain directory holding the same .db files to run somewhere
# without CVMFS.
CONDDB = os.environ.get('FULLSIM_CONDDB', '/cvmfs/cms-opendata-conddb.cern.ch')
GT = '102X_upgrade2018_design_v9'
GT_FALLBACK = '106X_mcRun2_asymptotic_v17'
SNAPSHOT = '2030-01-01 00:00:00.000'

# The vertex smearing the GEN step uses. Kept here rather than on the cmsDriver
# command line so set_beamspot() can read the actual numbers out of the matching cfi,
# instead of a hand-copied second set that could drift.
BEAMSPOT_NAME = 'Realistic25ns13TeVEarly2018Collision'

# (record, label, tag, source db) overridden explicitly rather than gap-filled
EXPLICIT = [
    ('PFCalibrationRcd', '', 'PFCalibration_UL2016_mc', GT_FALLBACK),
    ('PFCalibrationRcd', 'HLT', 'PFCalibration_2017_25ns_Spring17_v3_hlt', GT_FALLBACK),
    ('SiPixelQualityFromDbRcd', 'forDigitizer', 'SiPixelQuality_phase1_ideal', GT),
]


def _db(name):
    """Path to one of the open condition sqlite files."""
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
    """Point the GlobalTag at the open conditions and apply every fix listed in the module
    docstring.
    """
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
        # Loud, because a silently skipped gap-fill surfaces much later as a missing-record
        # exception in an unrelated-looking module.
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


# also exposed under the private name, which other patches call it by
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
    """Make the reconstructed beamspot match the simulated one.

    The open 2018 conditions are design conditions, so their beamspot sits at the origin,
    while the standard 2018 vertex smearing puts collisions some tens of microns away -
    many sigma off the beam the reconstruction assumes. Offline track selection and
    primary-vertex clustering use that beamspot, so with the mismatch the hard interaction
    splits into several low-quality vertices and every offline impact parameter is measured
    from a wrong point. HLT tracking is barely affected, but this is applied in every step
    anyway.

    Done with the BeamSpotFakeConditions ESSource, which takes the beamspot from the
    configuration, so no new condition payload has to be produced.
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
    """Keep only the named HLT paths, plus the DIGI/L1/output steps.

    The GRun menu shipped in this release is newer than the 2018 L1 menu in the open
    conditions, so unrelated paths request L1 seeds that do not exist there and the job
    dies on the first event. The hadronic PF-scouting paths use seeds that do exist.

    The jets actually ntuplized do not come from any of these paths - patch_hlt.py adds
    its own unconditional one - so these are kept only to have the scouting products in
    the file for comparison.
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
