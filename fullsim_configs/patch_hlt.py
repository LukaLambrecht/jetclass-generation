"""Keep the full HLT jet objects, not just the compressed scouting format.

Why: the 2018 scouting data format (ScoutingParticle) has NO impact parameters,
and its jets are AK4 only. But HLTScoutingPFProducer is just a packer: it reads
the ordinary HLT objects - reco::PFCandidate from 'hltParticleFlow' and
reco::Vertex - and throws away everything that does not fit the online bandwidth
budget. Since we run the HLT ourselves, that budget does not apply and we can
keep the real objects instead, which gives
  - AK8 PF jets at HLT ('hltAK8PFJets'), with constituent refs into
    hltParticleFlow, so no AK4-vs-AK8 mismatch with the offline side;
  - full reco::PFCandidate constituents with a reco::TrackRef, hence dxy/dz at
    full precision (more than even the Run-3 scouting format, which quantises);
  - HLT PF primary vertices ('hltVerticesPF', a 3D fit) rather than pixel-only
    ones, which matters: hltPixelVertices fixes x and y at the beamspot, which
    makes every dxy come out at ~0.43 mm, i.e. the beam offset, instead of a
    real impact parameter.

The scouting products are still written as well (patch_cond.prune_hlt keeps the
scouting paths), so the two views can be compared in the same file.
"""
import FWCore.ParameterSet.Config as cms


def add_hlt_jets(process, ak8=True, pfvertices=True, corrected=True):
    """Produce the HLT AK8 PF jets and HLT PF vertices for EVERY event.

    The HLT menu builds hltAK8PFJets only INSIDE the AK8 trigger paths, i.e.
    only for events passing their calo-jet filters, and hltVerticesPF only
    inside PF paths. For a jet dataset we want both unconditionally, so they go
    into their own paths with no filter in front of them. The sequences contain
    no filters themselves and pull in their own prerequisites (tracking + PF),
    so this works even with every trigger path pruned away. Measured cost:
    about +25% on the HLT step.
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

    The AODSIM event content keeps the SCOUTING products (they are the scouting
    stream's payload) but drops the ordinary HLT ones. With these keeps, a single
    AODSIM file holds the offline AND the HLT view of the same event, both with
    impact parameters - which is what the ntuplizer reads.
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
