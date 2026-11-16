"""Keep the full HLT jet objects, not just the compressed scouting format.

The 2018 scouting format carries no impact parameters and its jets are AK4 only. But
the scouting producer is just a packer: it reads the ordinary HLT objects and throws
away whatever does not fit the online bandwidth budget. Since we run the HLT ourselves
that budget does not apply, so the real objects can be kept instead, which gives
  - AK8 PF jets at HLT, with constituent refs into hltParticleFlow, so there is no
    AK4-against-AK8 mismatch with the offline side;
  - full PF candidates carrying a track, hence dxy/dz at full precision;
  - HLT PF primary vertices from a 3D fit rather than pixel-only ones, which matters:
    the pixel vertices fix x and y at the beamspot, which makes every dxy come out at
    the beam offset instead of a real impact parameter.

The scouting products are still written as well, so the two views can be compared in
the same file.
"""
import FWCore.ParameterSet.Config as cms


def add_hlt_jets(process, ak8=True, pfvertices=True, corrected=True):
    """Produce the HLT AK8 PF jets and HLT PF vertices for every event.

    The menu builds the AK8 jets only inside the AK8 trigger paths, and the PF vertices
    only inside PF paths, so for a jet dataset both go into their own unfiltered paths. The
    sequences contain no filters themselves and pull in their own prerequisites, so this
    works even with every trigger path pruned. Costs about 25% more on the HLT step.
    """
    new = []
    if ak8:
        seq = process.HLTAK8PFJetsSequence if corrected else cms.Sequence(
            process.HLTPreAK8PFJetsRecoSequence + process.HLTAK8PFJetsReconstructionSequence)
        process.jetclassAK8Path = cms.Path(seq)
        new.append(process.jetclassAK8Path)
    if pfvertices:
        # hltVerticesPFSelector is an EDFilter, so it goes LAST in the path (a
        # failing filter does not unmake the products already written)
        process.jetclassVtxPath = cms.Path(process.hltVerticesPF + process.hltVerticesPFSelector)
        new.append(process.jetclassVtxPath)

    items = list(process.schedule)
    paths = [i for i in items if not isinstance(i, cms.EndPath)]
    ends = [i for i in items if isinstance(i, cms.EndPath)]
    process.schedule = cms.Schedule(*(paths + new + ends),
                                    tasks=list(getattr(process.schedule, '_tasks', [])))
    print('[patch_hlt] added unconditional paths: %s'
          % [p.label_() if hasattr(p, 'label_') else '?' for p in new])
    return process


# The HLT products the ntuplizer needs, which the AODSIM event content drops.
# The tracks are needed too: without them the PFCandidates' trackRefs cannot be
# resolved, and every HLT impact parameter would silently be 0.
HLT_KEEPS = [
    'keep recoPFCandidates_hltParticleFlow_*_*',
    'keep recoPFJets_hltAK8PFJets_*_*',
    'keep recoPFJets_hltAK8PFJetsCorrected_*_*',
    'keep recoPFJets_hltAK4PFJets_*_*',
    'keep recoTracks_hltPFMuonMerging_*_*',
    'keep recoVertexs_hltVerticesPFSelector_*_*',
    'keep recoVertexs_hltPixelVertices_*_*',
    'keep recoBeamSpot_hltOnlineBeamSpot_*_*',
]


def keep_hlt_products(process, keeps=HLT_KEEPS):
    """Keep the HLT jet objects in the RECO-step output, next to the offline ones.

    The AODSIM event content keeps the scouting products but drops the ordinary HLT ones.
    With these keeps, one AODSIM file holds both views of the same event, each with impact
    parameters, which is what the ntuplizer reads.
    """
    n = 0
    for name in process.outputModules_():
        out = getattr(process, name)
        if not hasattr(out, 'outputCommands'):
            continue
        out.outputCommands.extend(keeps)
        n += 1
    print('[patch_hlt] added %d HLT keep statements to %d output module(s)' % (len(keeps), n))
    return process
