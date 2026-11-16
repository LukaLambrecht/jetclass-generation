"""Take the generator-level event from our own HepMC file instead of Pythia8.

The generators under gen_configs/ already produce events.hepmc with MG5_aMC and
Pythia8, which is the same input the Delphes backend reconstructs. This makes the CMSSW
GEN,SIM step read that file, so both backends start from the same generated events and
no physics generation is duplicated in CMSSW.

Applied to a cmsDriver GEN,SIM config with

    import patch_gen; process = patch_gen.apply(process, 'events.hepmc')
"""
import FWCore.ParameterSet.Config as cms


def apply(process, hepmc_file='events.hepmc'):
    """Point `process` at a HepMC file and remove CMSSW's own generator.

    Five things all have to be right, and each fails silently or confusingly on its own:
    MCFileSource needs firstLuminosityBlockForEachRun; the HepMC product's instance label
    makes the InputTag ('source', 'generator'); the module that reads it is VtxSmeared,
    since generatorSmeared has no `src`; the internal Pythia8 generator must be removed
    rather than replaced, because swapping the Path object out breaks the schedule later;
    and the output module's SelectEvents must stop referencing the generation path.
    """
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

    # Keep the generation path, for vertex smearing and genParticles, but drop the
    # internal Pythia8 generator and everything that depended on it.
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
