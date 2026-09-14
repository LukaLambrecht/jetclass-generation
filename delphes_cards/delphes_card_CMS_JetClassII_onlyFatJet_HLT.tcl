##############################################################################
# Approximate CMS Phase-2 HLT ("scouting")-like reconstruction - GENERATED,
# do not hand-edit. Produced by hlteff/generate_hlt_card.py from:
#   - the offline card as baseline: delphes_cards/delphes_card_CMS_JetClassII_onlyFatJet.tcl
#   - data-driven degradation curves: hlteff/curves_qcd.json
#     (generated 2026-08-28 07:56 UTC by hlteff/derive_curves.py, reading
#      256098 QCD jets, deltaR match window 0.03, from:
#      /eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/QCD_PT-mixed_TuneCP5_13p6TeV_pythia8_new
#      files: dnnTuples_nanov15_0000.root, dnnTuples_nanov15_0001.root, dnnTuples_nanov15_0002.root)
#
# Method (see hlteff/README.md for full details): two combination rules,
# chosen per module by what physically makes sense for that quantity.
#   Multiplicative (ChargedHadronTrackingEfficiency, ElectronTrackingEfficiency,
#   MuonTrackingEfficiency, JetEnergyScalePUPPIAK8): HLT(pt,eta) =
#   offline(pt,eta) * (a data-driven ratio measured in real paired
#   offline/scouting CMS data, binned in (pt,|eta|) for tracking, or jet
#   (pT,|eta|) for JES).
#   Quadrature (ChargedHadronMomentumSmearing, Electron/MuonMomentumSmearing,
#   TrackSmearing D0/DZResolutionFormula): HLT(pt,eta) = sqrt(offline(pt,eta)^2
#   + extra(pt,eta)^2), where extra is the additional smearing/spread
#   measured for matched offline-scouting pairs in that bin.
#   PUPPI, jet clustering, softdrop, TrackPileUpSubtractor.ZVertexResolution,
#   and JetEnergyScalePUPPIAK15 are UNCHANGED from the offline card - see
#   README.md for why.
#
#   Charged/Electron/Muon TrackingEfficiency are additionally HARD-SET to 0
#   in every pT bin entirely below 0.5 GeV, all |eta|
#   (--charged-eff-pt-floor) - a hand override, not data-driven: the
#   measured curves return a small nonzero efficiency there that is not
#   trusted.
#
#   ECal/HCal ResolutionFormula are hand-set to (offline formula) * 1.1
#   ("plan B": data-driven closure checks found the matched-pair approach
#   does not work for calorimeters the way it does for tracking - see
#   hlteff/calorimeters/README.md - so this is a documented placeholder
#   assumption, not a measurement). Both modules' tower grids are left at
#   their offline granularity. Both ECal/HCal thresholds
#   (EnergyMin/EnergySignificanceMin) are left at their offline values.
#
#   FastJetFinderPUPPIAK8/AK15's own JetPTMin is HAND-SET to 1 GeV
#   (not copied from the offline card's 200/120 GeV, unlike every other
#   untouched module) - a structural requirement, not a measurement: the
#   offline<->HLT jet-matching ntuplizer (delphes_analyzers/makeNtuplesPaired.C)
#   needs Delphes to actually construct/write a jet that degraded below the
#   offline analysis threshold, rather than silently dropping it here first -
#   see generate_hlt_card.py's own module docstring. JetEnergyScalePUPPIAK8's
#   ScaleFormula covers this newly-reachable low-pT region by extending the
#   lowest measured bin's value downward (see format_piecewise_table() in
#   delphes_formula.py), not a phantom zero.
#
# To regenerate after new data or a change to the offline card:
#   python hlteff/derive_curves.py       # only if the input data changed
#   python hlteff/generate_hlt_card.py
##############################################################################

#######################################
# Order of execution of various modules
#######################################

set ExecutionPath {

  PileUpMerger
  ParticlePropagator

  ChargedHadronTrackingEfficiency
  ElectronTrackingEfficiency
  MuonTrackingEfficiency

  ChargedHadronMomentumSmearing
  ElectronMomentumSmearing
  MuonMomentumSmearing

  TrackMerger
  TrackSmearing

  ECal
  HCal

  ElectronFilter
  TrackPileUpSubtractor
  RecoPuFilter
  NeutralEFlowMerger
  EFlowMerger

  LeptonFilterNoLep
  LeptonFilterLep
  RunPUPPIBase
  RunPUPPIMerger
  RunPUPPI

  EFlowFilterPuppi

  MissingET
  PuppiMissingET
  GenPileUpMissingET
  ScalarHT
  NeutrinoFilter
  GenJetFinderAK8
  GenJetFinderAK15
  GenMissingET
  FastJetFinderPUPPIAK8
  FastJetFinderPUPPIAK15

  JetEnergyScalePUPPIAK8
  JetEnergyScalePUPPIAK15

  TreeWriter
}

###############
# PileUp Merger
###############

module PileUpMerger PileUpMerger {
  set InputArray Delphes/stableParticles

  set ParticleOutputArray stableParticles
  set VertexOutputArray vertices

  # pre-generated minbias input file
  set PileUpFile MinBias_100k.pileup

  # average expected pile up
  set MeanPileUp 50

   # maximum spread in the beam direction in m
  set ZVertexSpread 0.25

  # maximum spread in time in s
  set TVertexSpread 800E-12

  # vertex smearing formula f(z,t) (z,t need to be respectively given in m,s)
  set VertexDistributionFormula {exp(-(t^2/160e-12^2/2))*exp(-(z^2/0.053^2/2))}


}

#################################
# Propagate particles in cylinder
#################################

module ParticlePropagator ParticlePropagator {
  set InputArray PileUpMerger/stableParticles

  set OutputArray stableParticles
  set NeutralOutputArray neutralParticles
  set ChargedHadronOutputArray chargedHadrons
  set ElectronOutputArray electrons
  set MuonOutputArray muons

  # radius of the magnetic field coverage, in m
  set Radius 1.29
  # half-length of the magnetic field coverage, in m
  set HalfLength 3.00

  # magnetic field
  set Bz 3.8
}

####################################
# Charged hadron tracking efficiency
####################################

module Efficiency ChargedHadronTrackingEfficiency {
  set InputArray ParticlePropagator/chargedHadrons
  set OutputArray chargedHadrons

  # add EfficiencyFormula {efficiency formula as a function of eta and pt}

  # tracking efficiency formula for charged hadrons
  set EfficiencyFormula {
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt <= 0.2) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.2 && pt <= 0.35) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.35 && pt <= 0.5) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (0.152472) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (0.281638) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (0.42857) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (0.497586) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (0.548724) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (0.588006) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (0.636903) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (0.675885) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (0.697767) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (0.696845) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (0.679896) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (0.639398) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (0.58028) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (0.507491) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (0.434112) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (0.344658) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (0.24641) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (0.18908) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (0.199274) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (0.201925) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt <= 0.2) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.2 && pt <= 0.35) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.35 && pt <= 0.5) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (0.0760607) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (0.152179) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (0.215831) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (0.255465) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (0.294938) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (0.32839) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (0.375562) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (0.421514) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (0.450422) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (0.459572) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (0.459082) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (0.429001) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (0.376569) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (0.306094) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (0.236813) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (0.176684) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (0.138737) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (0.147379) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (0.147379) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (0.147379)
  }
}

##############################
# Electron tracking efficiency
##############################

module Efficiency ElectronTrackingEfficiency {
  set InputArray ParticlePropagator/electrons
  set OutputArray electrons

  # set EfficiencyFormula {efficiency formula as a function of eta and pt}

  # tracking efficiency formula for electrons
  set EfficiencyFormula {
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt <= 0.2) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.2 && pt <= 0.35) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.35 && pt <= 0.5) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt <= 0.2) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.2 && pt <= 0.35) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.35 && pt <= 0.5) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (0)
  }
}

##########################
# Muon tracking efficiency
##########################

module Efficiency MuonTrackingEfficiency {
  set InputArray ParticlePropagator/muons
  set OutputArray muons

  # set EfficiencyFormula {efficiency formula as a function of eta and pt}

  # tracking efficiency formula for muons
  set EfficiencyFormula {
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt <= 0.2) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.2 && pt <= 0.35) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.35 && pt <= 0.5) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (0) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (0.00534413) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (0.0250812) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (0.116503) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (0.118462) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (0.165281) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (0.162554) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (0.160227) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (0.170974) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (0.180642) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (0.192325) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (0.154785) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (0.131459) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (0.0863489) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (0.0491925) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (0.0153861) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt <= 0.2) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.2 && pt <= 0.35) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.35 && pt <= 0.5) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (0) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (0.000904059) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (0.0215759) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (0.0815772) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (0.0875) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (0.0986433) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (0.180179) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (0.249588) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (0.243805) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (0.243805) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (0.243805) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (0.243805) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (0.243805) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (0.243805) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (0.243805) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (0.243805) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (0.189875)
  }
}

########################################
# Momentum resolution for charged tracks
########################################

module MomentumSmearing ChargedHadronMomentumSmearing {
  set InputArray ChargedHadronTrackingEfficiency/chargedHadrons
  set OutputArray chargedHadrons

  # set ResolutionFormula {resolution formula as a function of eta and pt}

  # resolution formula for charged hadrons
  # based on arXiv:1405.6569
  set ResolutionFormula {
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt <= 0.2) * (0.100665) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.2 && pt <= 0.35) * (0.100666) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.35 && pt <= 0.5) * (0.100667) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (0.10067) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (0.100434) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (0.100228) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (0.100146) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (0.100125) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (0.100152) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (0.10025) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (0.100527) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (0.101104) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (0.102514) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (0.106258) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (0.129561) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (0.284264) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (0.407185) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (0.492546) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (0.590044) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (0.737336) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (0.902224) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (1.4072) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (2.55219) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt <= 0.2) * (0.253805) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.2 && pt <= 0.35) * (0.253806) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.35 && pt <= 0.5) * (0.253808) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (0.253812) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (0.250936) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (0.250553) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (0.250387) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (0.250461) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (0.250618) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (0.251038) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (0.251714) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (0.253113) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (0.260767) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (0.320418) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (0.40907) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (0.488629) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (0.568952) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (0.66915) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (0.785341) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (1.04142) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (1.64872) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (2.57105) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (4.65747)
  }
}

###################################
# Momentum resolution for electrons
###################################

module MomentumSmearing ElectronMomentumSmearing {
  set InputArray ElectronTrackingEfficiency/electrons
  set OutputArray electrons

  # set ResolutionFormula {resolution formula as a function of eta and energy}

  # resolution formula for electrons
  # based on arXiv:1405.6569
  set ResolutionFormula {
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt <= 0.2) * (0.0500007) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.2 && pt <= 0.35) * (0.0500022) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.35 && pt <= 0.5) * (0.0500052) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (0.0500104) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (0.0500185) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (0.0500319) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (0.0500566) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (0.0501042) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (0.050195) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (0.0504048) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (0.0509465) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (0.0520462) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (0.0546664) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (0.0609469) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (0.0745155) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (0.102301) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (0.148896) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (0.226586) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (0.352069) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (0.554758) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (0.893899) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (1.40339) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (2.55049) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt <= 0.2) * (0.150001) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.2 && pt <= 0.35) * (0.150002) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.35 && pt <= 0.5) * (0.150006) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (0.150012) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (0.15002) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (0.150035) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (0.150063) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (0.150116) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (0.150216) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (0.15045) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (0.151055) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (0.152297) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (0.155319) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (0.162907) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (0.180695) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (0.221331) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (0.296493) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (0.43001) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (0.652963) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (1.01861) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (1.6344) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (2.5619) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (4.65242)
  }
}

###############################
# Momentum resolution for muons
###############################

module MomentumSmearing MuonMomentumSmearing {
  set InputArray MuonTrackingEfficiency/muons
  set OutputArray muons

  # set ResolutionFormula {resolution formula as a function of eta and pt}

  # resolution formula for muons
  set ResolutionFormula {
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt <= 0.2) * (0.0150815) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.2 && pt <= 0.35) * (0.0150815) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.35 && pt <= 0.5) * (0.0150816) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (0.0150817) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (0.0150819) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (0.0150823) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (0.0150829) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (0.0150842) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (0.0150865) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (0.0150919) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (0.0151061) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (0.0151438) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (0.0153282) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (0.0155867) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (0.0161589) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (0.0182118) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (0.0231983) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (0.0305656) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (0.0387243) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (0.0541347) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (0.0821923) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (0.125969) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (0.226228) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt <= 0.2) * (0.0250001) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.2 && pt <= 0.35) * (0.0250002) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.35 && pt <= 0.5) * (0.0250004) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (0.0250009) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (0.0250016) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (0.0250027) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (0.0250048) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (0.0250088) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (0.0250166) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (0.0250344) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (0.0250809) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (0.0251764) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (0.0254107) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (0.0260092) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (0.0274662) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (0.0310265) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (0.0381938) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (0.0519158) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (0.0759807) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (0.116465) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (0.185443) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (0.28983) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (0.525595)
  }
}

##############
# Track merger
##############

module Merger TrackMerger {
# add InputArray InputArray
  add InputArray ChargedHadronMomentumSmearing/chargedHadrons
  add InputArray ElectronMomentumSmearing/electrons
  add InputArray MuonMomentumSmearing/muons
  set OutputArray tracks
}



################################                                                                    
# Track impact parameter smearing                                                                   
################################                                                                    

module TrackSmearing TrackSmearing {
  set InputArray TrackMerger/tracks
#  set BeamSpotInputArray BeamSpotFilter/beamSpotParticle
  set OutputArray tracks
#  set ApplyToPileUp true

  # magnetic field
  set Bz 3.8

  # source trackResolutionCMS.tcl
  set PResolutionFormula { 0.0 }
  set CtgThetaResolutionFormula { 0.0 }
  set PhiResolutionFormula { 0.0 }
  # taken from arXiv:1405.6569 fig. 15
  set D0ResolutionFormula {
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt <= 0.2) * (0.358774) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.2 && pt <= 0.35) * (0.426383) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.35 && pt <= 0.5) * (0.393543) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (0.147484) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (0.0938066) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (0.0786118) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (0.0609298) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (0.0554238) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (0.041351) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (0.036541) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (0.0307982) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (0.0270361) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (0.0238641) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (0.0232168) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (0.0235746) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (0.0250602) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (0.0296599) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (0.0380673) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (0.0600523) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (0.109751) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (0.157729) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (0.155722) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (0.177801) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt <= 0.2) * (0.59825) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.2 && pt <= 0.35) * (0.800247) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.35 && pt <= 0.5) * (0.688017) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (0.288314) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (0.189011) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (0.161122) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (0.106857) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (0.0969849) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (0.0711278) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (0.0557533) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (0.0488215) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (0.0407116) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (0.0374349) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (0.0353455) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (0.0333961) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (0.0337484) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (0.0419306) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (0.0654104) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (0.113237) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (0.181009) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (0.181009) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (0.181009) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (0.181009)
  }
  set DZResolutionFormula {
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt <= 0.2) * (1.46642) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.2 && pt <= 0.35) * (1.49935) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.35 && pt <= 0.5) * (1.48315) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (0.19554) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (0.137585) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (0.113906) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (0.0910885) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (0.0815563) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (0.0650857) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (0.0558303) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (0.0501506) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (0.047825) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (0.0437041) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (0.044409) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (0.0504743) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (0.062117) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (0.0766251) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (0.0966241) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (0.121061) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (0.167579) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (0.208372) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (0.216005) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (0.201508) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt <= 0.2) * (0.113281) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.2 && pt <= 0.35) * (2.071) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.35 && pt <= 0.5) * (1.44375) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (1.20504) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (0.830275) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (0.675329) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (0.44455) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (0.380114) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (0.284377) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (0.224291) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (0.184915) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (0.161226) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (0.142915) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (0.15369) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (0.163082) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (0.197297) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (0.230802) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (0.291936) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (0.432702) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (0.49521) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (0.49521) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (0.49521) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (0.49521)
  }
}



#############
#   ECAL
#############

module SimpleCalorimeter ECal {
  set ParticleInputArray ParticlePropagator/stableParticles
  set TrackInputArray TrackSmearing/tracks

  set TowerOutputArray ecalTowers
  set EFlowTrackOutputArray eflowTracks
  set EFlowTowerOutputArray eflowPhotons

  set IsEcal true

  set EnergyMin 0.5
  set EnergySignificanceMin 2.0

  set SmearTowerCenter true

  set pi [expr {acos(-1)}]

  # lists of the edges of each tower in eta and phi
  # each list starts with the lower edge of the first tower
  # the list ends with the higher edged of the last tower

  # assume 0.02 x 0.02 resolution in eta,phi in the barrel |eta| < 1.5

  set PhiBins {}
  for {set i -180} {$i <= 180} {incr i} {
    add PhiBins [expr {$i * $pi/180.0}]
  }

  # 0.02 unit in eta up to eta = 1.5 (barrel)
  for {set i -85} {$i <= 86} {incr i} {
    set eta [expr {$i * 0.0174}]
    add EtaPhiBins $eta $PhiBins
  }

  # assume 0.02 x 0.02 resolution in eta,phi in the endcaps 1.5 < |eta| < 3.0 (HGCAL- ECAL)

  set PhiBins {}
  for {set i -180} {$i <= 180} {incr i} {
    add PhiBins [expr {$i * $pi/180.0}]
  }

  # 0.02 unit in eta up to eta = 3
  for {set i 1} {$i <= 84} {incr i} {
    set eta [expr { -2.958 + $i * 0.0174}]
    add EtaPhiBins $eta $PhiBins
  }

  for {set i 1} {$i <= 84} {incr i} {
    set eta [expr { 1.4964 + $i * 0.0174}]
    add EtaPhiBins $eta $PhiBins
  }

  # take present CMS granularity for HF

  # 0.175 x (0.175 - 0.35) resolution in eta,phi in the HF 3.0 < |eta| < 5.0
  set PhiBins {}
  for {set i -18} {$i <= 18} {incr i} {
    add PhiBins [expr {$i * $pi/18.0}]
  }

  foreach eta {-5 -4.7 -4.525 -4.35 -4.175 -4 -3.825 -3.65 -3.475 -3.3 -3.125 -2.958 3.125 3.3 3.475 3.65 3.825 4 4.175 4.35 4.525 4.7 5} {
    add EtaPhiBins $eta $PhiBins
  }


  add EnergyFraction {0} {0.0}
  # energy fractions for e, gamma and pi0
  add EnergyFraction {11} {1.0}
  add EnergyFraction {22} {1.0}
  add EnergyFraction {111} {1.0}
  # energy fractions for muon, neutrinos and neutralinos
  add EnergyFraction {12} {0.0}
  add EnergyFraction {13} {0.0}
  add EnergyFraction {14} {0.0}
  add EnergyFraction {16} {0.0}
  add EnergyFraction {1000022} {0.0}
  add EnergyFraction {1000023} {0.0}
  add EnergyFraction {1000025} {0.0}
  add EnergyFraction {1000035} {0.0}
  add EnergyFraction {1000045} {0.0}
  # energy fractions for K0short and Lambda
  add EnergyFraction {310} {0.3}
  add EnergyFraction {3122} {0.3}

  # set ResolutionFormula {resolution formula as a function of eta and energy}

  # for the ECAL barrel (|eta| < 1.5), see hep-ex/1306.2016 and 1502.02701

  # set ECalResolutionFormula {resolution formula as a function of eta and energy}
  # Eta shape from arXiv:1306.2016, Energy shape from arXiv:1502.02701
  set ResolutionFormula {
((abs(eta) <= 1.5) * (1+0.64*eta^2) * sqrt(energy^2*0.008^2 + energy*0.11^2 + 0.40^2) +
                             (abs(eta) > 1.5 && abs(eta) <= 2.5) * (2.16 + 5.6*(abs(eta)-2)^2) * sqrt(energy^2*0.008^2 + energy*0.11^2 + 0.40^2) +
                             (abs(eta) > 2.5 && abs(eta) <= 5.0) * sqrt(energy^2*0.107^2 + energy*2.08^2)) * 1.1
  }

}


#############
#   HCAL
#############

module SimpleCalorimeter HCal {
  set ParticleInputArray ParticlePropagator/stableParticles
  set TrackInputArray ECal/eflowTracks

  set TowerOutputArray hcalTowers
  set EFlowTrackOutputArray eflowTracks
  set EFlowTowerOutputArray eflowNeutralHadrons

  set IsEcal false

  set EnergyMin 1.0
  set EnergySignificanceMin 1.0

  set SmearTowerCenter true

  set pi [expr {acos(-1)}]

  # lists of the edges of each tower in eta and phi
  # each list starts with the lower edge of the first tower
  # the list ends with the higher edged of the last tower

  # 5 degrees towers
  set PhiBins {}
  for {set i -36} {$i <= 36} {incr i} {
    add PhiBins [expr {$i * $pi/36.0}]
  }
  foreach eta {-1.566 -1.479 -1.392 -1.305 -1.218 -1.131 -1.044 -0.957 -0.87 -0.783 -0.696 -0.609 -0.522 -0.435 -0.348 -0.261 -0.174 -0.087 0 0.087 0.174 0.261 0.348 0.435 0.522 0.609 0.696 0.783 0.87 0.957 1.044 1.131 1.218 1.305 1.392 1.479 1.566 1.653} {
    add EtaPhiBins $eta $PhiBins
  }

  # 10 degrees towers
  set PhiBins {}
  for {set i -18} {$i <= 18} {incr i} {
    add PhiBins [expr {$i * $pi/18.0}]
  }
  foreach eta {-4.35 -4.175 -4 -3.825 -3.65 -3.475 -3.3 -3.125 -2.95 -2.868 -2.65 -2.5 -2.322 -2.172 -2.043 -1.93 -1.83 -1.74 -1.653 1.74 1.83 1.93 2.043 2.172 2.322 2.5 2.65 2.868 2.95 3.125 3.3 3.475 3.65 3.825 4 4.175 4.35 4.525} {
    add EtaPhiBins $eta $PhiBins
  }

  # 20 degrees towers
  set PhiBins {}
  for {set i -9} {$i <= 9} {incr i} {
    add PhiBins [expr {$i * $pi/9.0}]
  }
  foreach eta {-5 -4.7 -4.525 4.7 5} {
    add EtaPhiBins $eta $PhiBins
  }

  # default energy fractions {abs(PDG code)} {Fecal Fhcal}
  add EnergyFraction {0} {1.0}
  # energy fractions for e, gamma and pi0
  add EnergyFraction {11} {0.0}
  add EnergyFraction {22} {0.0}
  add EnergyFraction {111} {0.0}
  # energy fractions for muon, neutrinos and neutralinos
  add EnergyFraction {12} {0.0}
  add EnergyFraction {13} {0.0}
  add EnergyFraction {14} {0.0}
  add EnergyFraction {16} {0.0}
  add EnergyFraction {1000022} {0.0}
  add EnergyFraction {1000023} {0.0}
  add EnergyFraction {1000025} {0.0}
  add EnergyFraction {1000035} {0.0}
  add EnergyFraction {1000045} {0.0}
  # energy fractions for K0short and Lambda
  add EnergyFraction {310} {0.7}
  add EnergyFraction {3122} {0.7}

  # set HCalResolutionFormula {resolution formula as a function of eta and energy}
  set ResolutionFormula {
((abs(eta) <= 3.0) * sqrt(energy^2*0.050^2 + energy*1.50^2) +
                             (abs(eta) > 3.0 && abs(eta) <= 5.0) * sqrt(energy^2*0.130^2 + energy*2.70^2)) * 1.1
  }

}

#################
# Electron filter
#################

module PdgCodeFilter ElectronFilter {
  set InputArray HCal/eflowTracks
  set OutputArray electrons
  set Invert true
  add PdgCode {11}
  add PdgCode {-11}
}


##########################
# Track pile-up subtractor
##########################

module TrackPileUpSubtractor TrackPileUpSubtractor {
# add InputArray InputArray OutputArray
  add InputArray HCal/eflowTracks eflowTracks
  add InputArray ElectronFilter/electrons electrons
  add InputArray MuonMomentumSmearing/muons muons

  set VertexInputArray PileUpMerger/vertices
  # assume perfect pile-up subtraction for tracks with |z| > fZVertexResolution
  # Z vertex resolution in m
  set ZVertexResolution {0.0001}
}

########################
# Reco PU filter
########################

module RecoPuFilter RecoPuFilter {
  set InputArray HCal/eflowTracks
  set OutputArray eflowTracks
}

###################################################
# Tower Merger (in case not using e-flow algorithm)
###################################################

module Merger TowerMerger {
# add InputArray InputArray
  add InputArray ECal/ecalTowers
  add InputArray HCal/hcalTowers
  set OutputArray towers
}

####################
# Neutral eflow merger
####################

module Merger NeutralEFlowMerger {
# add InputArray InputArray
  add InputArray ECal/eflowPhotons
  add InputArray HCal/eflowNeutralHadrons
  set OutputArray eflowTowers
}


####################
# Energy flow merger
####################

module Merger EFlowMerger {
# add InputArray InputArray
  add InputArray HCal/eflowTracks
  add InputArray ECal/eflowPhotons
  add InputArray HCal/eflowNeutralHadrons
  set OutputArray eflow
}

#########################################
### Run the puppi code (to be tuned) ###
#########################################

module PdgCodeFilter LeptonFilterNoLep {
  set InputArray HCal/eflowTracks
  set OutputArray eflowTracksNoLeptons
  set Invert false
  add PdgCode {13}
  add PdgCode {-13}
  add PdgCode {11}
  add PdgCode {-11}
}

module PdgCodeFilter LeptonFilterLep {
  set InputArray HCal/eflowTracks
  set OutputArray eflowTracksLeptons
  set Invert true
  add PdgCode {11}
  add PdgCode {-11}
  add PdgCode {13}
  add PdgCode {-13}
}

module RunPUPPI RunPUPPIBase {
  ## input information
  set TrackInputArray   LeptonFilterNoLep/eflowTracksNoLeptons
  set NeutralInputArray NeutralEFlowMerger/eflowTowers
  set PVInputArray      PileUpMerger/vertices
  set MinPuppiWeight    0.05
  set UseExp            false
  set UseNoLep          false

  ## define puppi algorithm parameters (more than one for the same eta region is possible)
  add EtaMinBin           0.0   2.5  
  add EtaMaxBin           2.5   10.0   
  add PtMinBin            0.0   0.0   
  add ConeSizeBin         0.4   0.4
  add RMSPtMinBin         0.1   0.5   
  add RMSScaleFactorBin   1.0   1.0   
  add NeutralMinEBin      0.2   0.2   
  add NeutralPtSlope      0.006 0.013
  add ApplyCHS            true  true  
  add UseCharged          true  true  
  add ApplyLowPUCorr      true  true  
  add MetricId            5     5     
  add CombId              0     0  

  ## output name
  set OutputArray         PuppiParticles
  set OutputArrayTracks   puppiTracks
  set OutputArrayNeutrals puppiNeutrals
}

module Merger RunPUPPIMerger {
  add InputArray RunPUPPIBase/PuppiParticles
  add InputArray LeptonFilterLep/eflowTracksLeptons
  set OutputArray PuppiParticles
}

# need this because of leptons that were added back
module RecoPuFilter RunPUPPI {
  set InputArray RunPUPPIMerger/PuppiParticles
  set OutputArray PuppiParticles
}

######################
# EFlowFilterPuppi
######################

module PdgCodeFilter EFlowFilterPuppi {
  set InputArray RunPUPPI/PuppiParticles
  set OutputArray eflow

  add PdgCode {11}
  add PdgCode {-11}
  add PdgCode {13}
  add PdgCode {-13}
}

###################
# Missing ET merger
###################

module Merger MissingET {
# add InputArray InputArray
#  add InputArray RunPUPPI/PuppiParticles
  add InputArray EFlowMerger/eflow
  set MomentumOutputArray momentum
}

module Merger PuppiMissingET {
  #add InputArray InputArray
  add InputArray RunPUPPI/PuppiParticles
  #add InputArray EFlowMerger/eflow
  set MomentumOutputArray momentum
}

###################
# Ger PileUp Missing ET
###################

module Merger GenPileUpMissingET {
# add InputArray InputArray
#  add InputArray RunPUPPI/PuppiParticles
  add InputArray ParticlePropagator/stableParticles
  set MomentumOutputArray momentum
}

##################
# Scalar HT merger
##################

module Merger ScalarHT {
# add InputArray InputArray
  add InputArray RunPUPPI/PuppiParticles
  set EnergyOutputArray energy
}

#################
# Neutrino Filter
#################

module PdgCodeFilter NeutrinoFilter {

  set InputArray Delphes/stableParticles
  set OutputArray filteredParticles

  set PTMin 0.0

  add PdgCode {12}
  add PdgCode {14}
  add PdgCode {16}
  add PdgCode {-12}
  add PdgCode {-14}
  add PdgCode {-16}

}


#####################
# MC truth jet finder
#####################

module FastJetFinder GenJetFinderAK8 {
  set InputArray NeutrinoFilter/filteredParticles

  set OutputArray jets

  # algorithm: 1 CDFJetClu, 2 MidPoint, 3 SIScone, 4 kt, 5 Cambridge/Aachen, 6 antikt
  set JetAlgorithm 6
  set ParameterR 0.8

  set ComputeNsubjettiness 1
  set Beta 1.0
  set AxisMode 4

  set ComputeSoftDrop 1
  set BetaSoftDrop 0.0
  set SymmetryCutSoftDrop 0.1
  set R0SoftDrop 0.8

  set JetPTMin 200.0
}

module FastJetFinder GenJetFinderAK15 {
  set InputArray NeutrinoFilter/filteredParticles

  set OutputArray jets

  # algorithm: 1 CDFJetClu, 2 MidPoint, 3 SIScone, 4 kt, 5 Cambridge/Aachen, 6 antikt
  set JetAlgorithm 6
  set ParameterR 1.5

  set ComputeNsubjettiness 1
  set Beta 1.0
  set AxisMode 4

  set ComputeSoftDrop 1
  set BetaSoftDrop 0.0
  set SymmetryCutSoftDrop 0.1
  set R0SoftDrop 1.5

  set JetPTMin 120.0
}

#########################
# Gen Missing ET merger
########################

module Merger GenMissingET {

# add InputArray InputArray
  add InputArray NeutrinoFilter/filteredParticles
  set MomentumOutputArray momentum
}


##############
# Jet finder
##############

module FastJetFinder FastJetFinderPUPPIAK8 {
#  set InputArray TowerMerger/towers
  set InputArray RunPUPPI/PuppiParticles

  set OutputArray jets

  set JetAlgorithm 6
  set ParameterR 0.8

  set ComputeNsubjettiness 1
  set Beta 1.0
  set AxisMode 4

  set ComputeTrimming 1
  set RTrim 0.2
  set PtFracTrim 0.05

  set ComputePruning 1
  set ZcutPrun 0.1
  set RcutPrun 0.5
  set RPrun 0.8

  set ComputeSoftDrop 1
  set BetaSoftDrop 0.0
  set SymmetryCutSoftDrop 0.1
  set R0SoftDrop 0.8

  set JetPTMin 1
}

module FastJetFinder FastJetFinderPUPPIAK15 {
#  set InputArray TowerMerger/towers
  set InputArray RunPUPPI/PuppiParticles

  set OutputArray jets

  set JetAlgorithm 6
  set ParameterR 1.5

  set ComputeNsubjettiness 1
  set Beta 1.0
  set AxisMode 4

  set ComputeTrimming 1
  set RTrim 0.2
  set PtFracTrim 0.05

  set ComputePruning 1
  set ZcutPrun 0.1
  set RcutPrun 0.5
  set RPrun 1.5

  set ComputeSoftDrop 1
  set BetaSoftDrop 0.0
  set SymmetryCutSoftDrop 0.1
  set R0SoftDrop 1.5

  set JetPTMin 1
}

##################
# Jet Energy Scale
##################

module EnergyScale JetEnergyScalePUPPIAK8 {
  set InputArray FastJetFinderPUPPIAK8/jets
  set OutputArray jets

 # scale formula for jets
  set ScaleFormula {
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt <= 250) * (1.02948) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 300) * (1.02298) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 300 && pt <= 400) * (1.01411) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 500) * (1.00739) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 500 && pt <= 650) * (1.00143) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 800) * (0.9968) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 800 && pt <= 1000) * (0.993623) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000 && pt <= 1500) * (0.990814) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1500 && pt <= 2000) * (0.990758) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2000 && pt <= 3000) * (0.989641) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3000) * (0.988095) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt <= 250) * (1.09579) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 300) * (1.07237) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 300 && pt <= 400) * (1.04741) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 500) * (1.02741) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 500 && pt <= 650) * (1.01215) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 800) * (1.00068) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 800 && pt <= 1000) * (0.991693) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000 && pt <= 1500) * (0.986043) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1500 && pt <= 2000) * (0.986043) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2000 && pt <= 3000) * (0.986043) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3000) * (0.986043)
  }
}

module EnergyScale JetEnergyScalePUPPIAK15 {
  set InputArray FastJetFinderPUPPIAK15/jets
  set OutputArray jets

 # scale formula for jets
  set ScaleFormula {1.00}
}


##################
# ROOT tree writer
##################

# tracks, towers and eflow objects are not stored by default in the output.
# if needed (for jet constituent or other studies), uncomment the relevant
# "add Branch ..." lines.

module TreeWriter TreeWriter {
# add Branch InputArray BranchName BranchClass
  add Branch Delphes/allParticles Particle GenParticle

  add Branch RunPUPPI/PuppiParticles ParticleFlowCandidate ParticleFlowCandidate

  add Branch GenJetFinderAK8/jets GenJetAK8 Jet
  add Branch GenJetFinderAK15/jets GenJetAK15 Jet
  add Branch GenMissingET/momentum GenMissingET MissingET
  add Branch GenPileUpMissingET/momentum GenPileUpMissingET MissingET

  add Branch JetEnergyScalePUPPIAK8/jets JetPUPPIAK8 Jet
  add Branch JetEnergyScalePUPPIAK15/jets JetPUPPIAK15 Jet

  add Branch MissingET/momentum MissingET MissingET
  add Branch PuppiMissingET/momentum PuppiMissingET MissingET
  add Branch ScalarHT/energy ScalarHT ScalarHT

  add Branch PileUpMerger/vertices Vertex Vertex
}
