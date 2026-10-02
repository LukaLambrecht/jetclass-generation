"""Take the generator-level event from our own HepMC file instead of Pythia8.

The repo's generators (gen_configs/, driven by run.sh) already produce
events.hepmc with MG5_aMC + Pythia8 - exactly the same input the Delphes backend
reconstructs. This makes the CMSSW GEN,SIM step read that file, so both backends
start from the very same generated events and nothing about the physics
generation is duplicated in CMSSW.

Applied to a cmsDriver GEN,SIM config with

    import patch_gen; process = patch_gen.apply(process, 'events.hepmc')

Found the hard way, in this order (each one is a silent or confusing failure):
 - MCFileSource needs firstLuminosityBlockForEachRun, or it refuses to start;
 - the HepMC product's instance label is 'generator', so the InputTag is
   ('source', 'generator'), not just 'source';
 - the module that reads it is VtxSmeared (generatorSmeared has no `src`);
 - the internal Pythia8 'generator' module has to be REMOVED, not replaced:
   swapping the Path object out breaks the schedule later, in _insertPaths;
 - the output module's SelectEvents still referenced the generation path, which
   no longer exists after that removal.
"""
import FWCore.ParameterSet.Config as cms


def apply(process, hepmc_file='events.hepmc'):
    process.source = cms.Source(
        'MCFileSource',
        fileNames=cms.untracked.vstring('file:%s' % hepmc_file),
        # required by MCFileSource, even (especially) when empty
        firstLuminosityBlockForEachRun=cms.untracked.VLuminosityBlockID())

    # the HepMC product of MCFileSource is ('source', 'generator')
    src = cms.InputTag('source', 'generator')
    if hasattr(process, 'VtxSmeared'):
        process.VtxSmeared.src = src
    else:
        raise RuntimeError('patch_gen: no VtxSmeared module in this config - '
                           'is this really a GEN,SIM config?')
    if hasattr(process, 'genParticles'):
        process.genParticles.src = src

    # keep the generation path (vertex smearing, genParticles) but drop the
    # internal Pythia8 generator, and everything that depended on it
    import patch_cond
    patch_cond.remove_module(process, 'generator')
    if hasattr(process, 'genfiltersummary_step'):
        try:
            process.schedule.remove(process.genfiltersummary_step)
        except Exception:
            pass
    for out in process.outputModules_():
        mod = getattr(process, out)
        if hasattr(mod, 'SelectEvents'):
            # selected on the generation path, which no longer exists
            mod.SelectEvents = cms.untracked.PSet()
    print('[patch_gen] generator-level events taken from %s' % hepmc_file)
    return process
