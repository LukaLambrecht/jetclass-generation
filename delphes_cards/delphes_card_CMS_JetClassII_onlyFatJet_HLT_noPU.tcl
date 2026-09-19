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
#   RunPUPPIBase.UseCharged is set to FALSE (the offline card's own value is
#   true) - see --puppi-use-charged. This makes PUPPI score each candidate
#   against ALL particles rather than against leading-vertex CHARGED TRACKS
#   only, because that charged reference population is exactly what the HLT
#   tracking retuning above depletes, which otherwise drives reconstructed
#   neutral hadrons/photons per jet far BELOW offline when real scouting
#   data shows them well above it. Jet clustering, softdrop,
#   TrackPileUpSubtractor.ZVertexResolution and JetEnergyScalePUPPIAK15
#   remain UNCHANGED from the offline card - see README.md. NOTE:
#   JetEnergyScalePUPPIAK8 above was derived against the UseCharged=true
#   behaviour and has NOT been re-derived for this setting.
#
#   IMPACT-PARAMETER-DEPENDENT tracking efficiency for chargedHadron/muon:
#   the EfficiencyFormula is a (|eta|, pT, |d0|) table, offline(pt,eta) *
#   ratio(eta,pt,d0), with the ratio from hlteff/curves_ip_qcd.json
#   (hlteff/derive_ip_curves.py, generated 2026-09-18 16:55 UTC, 293373 QCD
#   jets; denominator without lost and pile-up-like tracks), assuming the
#   offline efficiency is uniform in d0; see derive_ip_curves.py and
#   delphes_cards/KNOWN_ISSUES.md.
#
#   NO PUPPI and NO CHS for the HLT jets (as real scouting AK8 jets):
#   FastJetFinderPUPPIAK8/AK15 and the ParticleFlowCandidate branch use
#   HLTEFlowMerger/eflow = TrackPileUpSubtractor/eflowTracks with
#   ZVertexResolution set to 2.5 mm, i.e. pile-up tracks farther than that
#   from the primary vertex are dropped by truth - a stand-in for HLT
#   tracking's limited z acceptance, which a Delphes formula cannot express,
#   plus ECal photons and HCal neutral hadrons. Module/branch names keep
#   "PUPPI" for compatibility. JetEnergyScalePUPPIAK8 was NOT re-derived for
#   this. All HLT candidates with reconstructed pT below 0.6 GeV are dropped
#   first (HLTEFlowPtFilter), as in the scouting producer.
#
#   JetEnergyScalePUPPIAK8 is additionally multiplied by per-HLT-jet-pT
#   factors (0.829-0.924) from hlteff/jes_correction_nopuppi.json
#   (hlteff/derive_hlt_jes_correction.py, generated 2026-09-19 12:19 UTC,
#   26152 matched QCD jets), which bring our HLT/offline jet-pT ratio onto
#   FullSim's for this card's settings.
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
#   assumption, not a measurement). Both modules' tower grids are
#   additionally coarsened by a factor 1.25 in both eta and phi (each tower
#   1.25x wider in each dimension, 1.5625x the area) - also a hand-set
#   assumption (a data-driven granularity scan found no coarsening factor
#   actually reproduces the measured effect, see
#   hlteff/calorimeters/README.md). Both ECal/HCal thresholds
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
  HLTEFlowMerger
  HLTEFlowPtFilter

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
  set MeanPileUp 0

   # maximum spread in the beam direction in m
  set ZVertexSpread 0.25

  # maximum spread in time in s
  set TVertexSpread 800E-12

  # vertex smearing formula f(z,t) (z,t need to be respectively given in m,s)
  set VertexDistributionFormula {exp(-(t^2/160e-12^2/2))*exp(-(z^2/0.053^2/2))}
  # reseed the random generator at the start of every event from (RandomSeed,
  # event index) - requires the PATCHED PileUpMerger (see
  # delphes_cards/KNOWN_ISSUES.md) and a nonzero global RandomSeed (set per
  # batch by run.sh). Makes the offline and HLT runs over the same events.hepmc
  # get the same vertex position and pile-up overlay for every event.
  set PerEventSeed true


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
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) <= 0.1) * (0.263463) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.214696) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.168685) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.116591) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0278122) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 2 && abs(d0) <= 5) * (0.00907012) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 5 && abs(d0) <= 10) * (0.00607815) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 10) * (0.00439565) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) <= 0.1) * (0.559561) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.448787) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.289541) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.174033) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0311472) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0106015) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 5 && abs(d0) <= 10) * (0.00745913) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 10) * (0.00559104) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) <= 0.1) * (0.84615) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.631846) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.371981) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.242851) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0468899) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0201276) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0121659) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 10) * (0.00815291) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) <= 0.1) * (0.866077) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.635859) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.415693) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.255557) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0520436) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0248513) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0142466) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 10) * (0.00858872) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) <= 0.1) * (0.862761) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.627711) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.462358) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.281421) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0677802) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 2 && abs(d0) <= 5) * (0.027408) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0198074) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 10) * (0.0110731) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (abs(d0) <= 0.1) * (0.858532) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.631471) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.487312) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.341784) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 1 && abs(d0) <= 2) * (0.10181) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0396314) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0273136) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 10) * (0.0142911) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) <= 0.1) * (0.85152) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.635904) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.502637) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.379277) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0933799) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0552568) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0376473) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 10) * (0.0191924) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) <= 0.1) * (0.836265) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.617781) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.486588) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.370736) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 1 && abs(d0) <= 2) * (0.11981) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0759185) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0498372) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 10) * (0.0268169) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) <= 0.1) * (0.81817) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.573781) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.467113) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.328982) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 1 && abs(d0) <= 2) * (0.133473) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0888323) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0658814) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 10) * (0.0342299) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) <= 0.1) * (0.788728) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.53106) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.429465) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.305974) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 1 && abs(d0) <= 2) * (0.146104) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 2 && abs(d0) <= 5) * (0.100174) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0695842) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 10) * (0.0425486) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) <= 0.1) * (0.747759) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.473365) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.394242) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.283603) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 1 && abs(d0) <= 2) * (0.159103) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 2 && abs(d0) <= 5) * (0.106416) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0804614) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 10) * (0.0441252) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) <= 0.1) * (0.692072) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.427361) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.351044) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.256217) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 1 && abs(d0) <= 2) * (0.141948) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 2 && abs(d0) <= 5) * (0.110598) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0764678) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 10) * (0.0514255) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) <= 0.1) * (0.623267) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.376892) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.323907) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.208503) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 1 && abs(d0) <= 2) * (0.135348) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 2 && abs(d0) <= 5) * (0.106105) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0841281) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 10) * (0.0601784) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) <= 0.1) * (0.544118) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.340969) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.286912) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.179565) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 1 && abs(d0) <= 2) * (0.141529) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 2 && abs(d0) <= 5) * (0.127941) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0851541) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 10) * (0.0738217) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) <= 0.1) * (0.465874) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.294768) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.239359) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.200643) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 1 && abs(d0) <= 2) * (0.13796) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 2 && abs(d0) <= 5) * (0.139943) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 5 && abs(d0) <= 10) * (0.145792) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 10) * (0.0915061) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) <= 0.1) * (0.367809) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.256922) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.229378) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.171669) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 1 && abs(d0) <= 2) * (0.196847) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 2 && abs(d0) <= 5) * (0.196891) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0856557) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 10) * (0.09375) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) <= 0.1) * (0.259153) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.197482) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.207791) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.213518) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 1 && abs(d0) <= 2) * (0.28178) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 2 && abs(d0) <= 5) * (0.255462) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 5 && abs(d0) <= 10) * (0.051752) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 10) * (0.140064) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) <= 0.1) * (0.192672) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.172291) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.198773) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.173358) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0577117) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0492953) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0393156) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 10) * (0.0295818) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) <= 0.1) * (0.193571) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.212687) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.234058) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.0791631) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0600342) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0512791) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0408978) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 10) * (0.0307722) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) <= 0.1) * (0.215718) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.209103) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.264966) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.0867312) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0657736) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0561815) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0448077) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 10) * (0.0337141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) <= 0.1) * (0.186568) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.163081) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.141525) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.098882) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0422604) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0169705) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 5 && abs(d0) <= 10) * (0.00897853) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.5 && pt <= 0.7) * (abs(d0) > 10) * (0.00899287) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) <= 0.1) * (0.383838) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.314499) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.259459) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.134884) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0486556) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0152876) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0129014) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.7 && pt <= 0.9) * (abs(d0) > 10) * (0.0106368) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) <= 0.1) * (0.578346) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.449331) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.314002) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.195859) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0674563) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0306051) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0205947) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 0.9 && pt <= 1.2) * (abs(d0) > 10) * (0.0161486) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) <= 0.1) * (0.584226) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.458537) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.326418) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.192596) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0703972) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0370977) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0257114) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.2 && pt <= 1.6) * (abs(d0) > 10) * (0.0170269) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) <= 0.1) * (0.57879) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.455352) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.33349) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.212413) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0915426) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0452518) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 5 && abs(d0) <= 10) * (0.032678) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1.6 && pt <= 2.2) * (abs(d0) > 10) * (0.0200805) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) <= 0.1) * (0.578278) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.461694) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.348754) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.240303) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 1 && abs(d0) <= 2) * (0.125809) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0530976) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0418383) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 10) * (0.0269554) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) <= 0.1) * (0.574892) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.474116) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.339526) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.276713) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 1 && abs(d0) <= 2) * (0.119483) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 2 && abs(d0) <= 5) * (0.076135) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0622426) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 10) * (0.0360525) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) <= 0.1) * (0.570484) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.465064) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.360441) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.246627) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 1 && abs(d0) <= 2) * (0.131208) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0950339) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0718112) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 10) * (0.0487026) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) <= 0.1) * (0.567355) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.426539) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.344331) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.23668) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 1 && abs(d0) <= 2) * (0.144257) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 2 && abs(d0) <= 5) * (0.115892) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0956954) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 10) * (0.065051) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) <= 0.1) * (0.549873) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.369159) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.31064) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.234981) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 1 && abs(d0) <= 2) * (0.149595) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 2 && abs(d0) <= 5) * (0.116763) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 5 && abs(d0) <= 10) * (0.102114) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 10) * (0.0820567) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) <= 0.1) * (0.525174) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.347727) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.297448) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.24849) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 1 && abs(d0) <= 2) * (0.158423) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 2 && abs(d0) <= 5) * (0.139119) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 5 && abs(d0) <= 10) * (0.101699) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 10) * (0.0751052) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) <= 0.1) * (0.479758) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.325187) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.259334) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.216126) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 1 && abs(d0) <= 2) * (0.146893) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 2 && abs(d0) <= 5) * (0.128246) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 5 && abs(d0) <= 10) * (0.117004) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 10) * (0.0762458) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) <= 0.1) * (0.415847) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.26487) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.218812) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.187402) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 1 && abs(d0) <= 2) * (0.152734) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 2 && abs(d0) <= 5) * (0.158913) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 5 && abs(d0) <= 10) * (0.132578) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 10) * (0.0840659) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) <= 0.1) * (0.331029) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.2567) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.219583) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.215) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 1 && abs(d0) <= 2) * (0.1768) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 2 && abs(d0) <= 5) * (0.153124) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 5 && abs(d0) <= 10) * (0.107992) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 10) * (0.101268) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) <= 0.1) * (0.250215) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.206061) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.163319) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.141691) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 1 && abs(d0) <= 2) * (0.122145) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 2 && abs(d0) <= 5) * (0.11731) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0827339) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 10) * (0.0775824) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) <= 0.1) * (0.177253) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.135764) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.112707) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.102405) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0882784) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0847838) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0597945) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 10) * (0.0560713) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) <= 0.1) * (0.134991) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.103054) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.0894516) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.0812749) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0700635) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0672899) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0474568) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 10) * (0.0445018) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) <= 0.1) * (0.151213) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.113015) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.098098) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.0891309) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0768358) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0737941) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0520439) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 10) * (0.0488034) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) <= 0.1) * (0.160686) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.113015) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.098098) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.0891309) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0768358) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0737941) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0520439) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 10) * (0.0488034) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) <= 0.1) * (0.160686) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.113015) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.098098) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.0891309) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0768358) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0737941) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0520439) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 10) * (0.0488034)
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
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) <= 0.1) * (0.0393707) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.0640299) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.0855) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.0362195) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0385714) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0138462) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 5 && abs(d0) <= 10) * (0.00795181) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 10) * (0.000991984) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) <= 0.1) * (0.23847) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.403723) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.34082) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.243769) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 1 && abs(d0) <= 2) * (0.116725) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0545669) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0474658) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 10) * (0.00549491) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) <= 0.1) * (0.359806) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.482308) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.358286) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.244588) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 1 && abs(d0) <= 2) * (0.1815) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0386719) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0108791) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 7 && pt <= 10) * (abs(d0) > 10) * (0.00470309) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) <= 0.1) * (0.655806) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.639474) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.540723) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.358696) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 1 && abs(d0) <= 2) * (0.192026) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 2 && abs(d0) <= 5) * (0.04125) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0120732) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 10 && pt <= 16) * (abs(d0) > 10) * (0.00432314) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) <= 0.1) * (0.69378) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.609661) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.53122) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.407278) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 1 && abs(d0) <= 2) * (0.107442) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0419788) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0266538) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 16 && pt <= 25) * (abs(d0) > 10) * (0.00831933) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) <= 0.1) * (0.608163) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.684973) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.55) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.365676) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 1 && abs(d0) <= 2) * (0.160541) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0368944) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 5 && abs(d0) <= 10) * (0.00846154) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 25 && pt <= 40) * (abs(d0) > 10) * (0.00798387) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) <= 0.1) * (0.607774) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.558462) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.495) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.326796) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 1 && abs(d0) <= 2) * (0.144118) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0740187) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 5 && abs(d0) <= 10) * (0.051176) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 40 && pt <= 65) * (abs(d0) > 10) * (0.0344882) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) <= 0.1) * (0.549474) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.462482) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.50325) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.297795) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 1 && abs(d0) <= 2) * (0.140241) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0691928) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 5 && abs(d0) <= 10) * (0.049799) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 65 && pt <= 100) * (abs(d0) > 10) * (0.0335602) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) <= 0.1) * (0.598923) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.494789) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.383514) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.301775) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 1 && abs(d0) <= 2) * (0.142115) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0701175) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0504645) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 100 && pt <= 160) * (abs(d0) > 10) * (0.0340087) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) <= 0.1) * (0.59625) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.534732) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.487212) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.326136) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 1 && abs(d0) <= 2) * (0.153587) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0757779) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0545384) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 160 && pt <= 250) * (abs(d0) > 10) * (0.0367541) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) <= 0.1) * (0.5976) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.506981) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.461927) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.309211) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 1 && abs(d0) <= 2) * (0.145617) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0718452) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 5 && abs(d0) <= 10) * (0.051708) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 400) * (abs(d0) > 10) * (0.0348467) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) <= 0.1) * (0.5856) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.4968) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.452652) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.303001) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 1 && abs(d0) <= 2) * (0.142693) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0704026) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0506697) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 650) * (abs(d0) > 10) * (0.0341469) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) <= 0.1) * (0.5856) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.4968) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.452652) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.303001) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 1 && abs(d0) <= 2) * (0.142693) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0704026) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0506697) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 10) * (0.0341469) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) <= 0.1) * (0.456066) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.386908) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.352525) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.235978) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 1 && abs(d0) <= 2) * (0.111129) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0548296) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0394616) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000) * (abs(d0) > 10) * (0.0265937) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) <= 0.1) * (0.0354217) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.0390551) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.0256516) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.0256516) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 1 && abs(d0) <= 2) * (0.0256516) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 2 && abs(d0) <= 5) * (0.0231824) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2.2 && pt <= 3) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0797874) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) <= 0.1) * (0.148905) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.15926) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.15926) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.15926) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 1 && abs(d0) <= 2) * (0.15926) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 2 && abs(d0) <= 5) * (0.15926) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 5 && abs(d0) <= 10) * (0.089127) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3 && pt <= 4.5) * (abs(d0) > 10) * (0.0198649) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) <= 0.1) * (0.16486) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.169491) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.169491) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.169491) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 1 && abs(d0) <= 2) * (0.169491) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 2 && abs(d0) <= 5) * (0.169491) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 4.5 && pt <= 7) * (abs(d0) > 5 && abs(d0) <= 10) * (0.0948526) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) <= 0.1) * (0.260177) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.224925) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.224925) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.224925) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 1 && abs(d0) <= 2) * (0.224925) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 2 && abs(d0) <= 5) * (0.224925) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 5 && abs(d0) <= 10) * (0.125876) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 7 && pt <= 10) * (abs(d0) > 10) * (0.0128009) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) <= 0.1) * (0.531215) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.463118) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.463118) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.463118) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 1 && abs(d0) <= 2) * (0.463118) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 2 && abs(d0) <= 5) * (0.463118) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 5 && abs(d0) <= 10) * (0.463118) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 10 && pt <= 16) * (abs(d0) > 10) * (0.463118) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) <= 0.1) * (0.590971) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.590971) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.590971) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.590971) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 1 && abs(d0) <= 2) * (0.590971) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 2 && abs(d0) <= 5) * (0.590971) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 5 && abs(d0) <= 10) * (0.590971) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 16 && pt <= 25) * (abs(d0) > 10) * (0.590971) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) <= 0.1) * (0.557414) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.557414) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.557414) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.557414) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 1 && abs(d0) <= 2) * (0.557414) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 2 && abs(d0) <= 5) * (0.557414) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 5 && abs(d0) <= 10) * (0.557414) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 25 && pt <= 40) * (abs(d0) > 10) * (0.557414) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) <= 0.1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 1 && abs(d0) <= 2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 2 && abs(d0) <= 5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 5 && abs(d0) <= 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 40 && pt <= 65) * (abs(d0) > 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) <= 0.1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 1 && abs(d0) <= 2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 2 && abs(d0) <= 5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 5 && abs(d0) <= 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 65 && pt <= 100) * (abs(d0) > 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) <= 0.1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 1 && abs(d0) <= 2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 2 && abs(d0) <= 5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 5 && abs(d0) <= 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 100 && pt <= 160) * (abs(d0) > 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) <= 0.1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 1 && abs(d0) <= 2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 2 && abs(d0) <= 5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 5 && abs(d0) <= 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 160 && pt <= 250) * (abs(d0) > 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) <= 0.1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 1 && abs(d0) <= 2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 2 && abs(d0) <= 5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 5 && abs(d0) <= 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 400) * (abs(d0) > 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) <= 0.1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 1 && abs(d0) <= 2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 2 && abs(d0) <= 5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 5 && abs(d0) <= 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 650) * (abs(d0) > 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) <= 0.1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 1 && abs(d0) <= 2) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 2 && abs(d0) <= 5) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 5 && abs(d0) <= 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 1000) * (abs(d0) > 10) * (0.528141) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) <= 0.1) * (0.411317) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 0.1 && abs(d0) <= 0.2) * (0.411317) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 0.2 && abs(d0) <= 0.5) * (0.411317) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 0.5 && abs(d0) <= 1) * (0.411317) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 1 && abs(d0) <= 2) * (0.411317) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 2 && abs(d0) <= 5) * (0.411317) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 5 && abs(d0) <= 10) * (0.411317) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000) * (abs(d0) > 10) * (0.411317)
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
  add PhiBins -3.141592654
  add PhiBins -3.119776038
  add PhiBins -3.097959422
  add PhiBins -3.076142807
  add PhiBins -3.054326191
  add PhiBins -3.032509575
  add PhiBins -3.01069296
  add PhiBins -2.988876344
  add PhiBins -2.967059728
  add PhiBins -2.945243113
  add PhiBins -2.923426497
  add PhiBins -2.901609881
  add PhiBins -2.879793266
  add PhiBins -2.85797665
  add PhiBins -2.836160034
  add PhiBins -2.814343419
  add PhiBins -2.792526803
  add PhiBins -2.770710188
  add PhiBins -2.748893572
  add PhiBins -2.727076956
  add PhiBins -2.705260341
  add PhiBins -2.683443725
  add PhiBins -2.661627109
  add PhiBins -2.639810494
  add PhiBins -2.617993878
  add PhiBins -2.596177262
  add PhiBins -2.574360647
  add PhiBins -2.552544031
  add PhiBins -2.530727415
  add PhiBins -2.5089108
  add PhiBins -2.487094184
  add PhiBins -2.465277568
  add PhiBins -2.443460953
  add PhiBins -2.421644337
  add PhiBins -2.399827721
  add PhiBins -2.378011106
  add PhiBins -2.35619449
  add PhiBins -2.334377875
  add PhiBins -2.312561259
  add PhiBins -2.290744643
  add PhiBins -2.268928028
  add PhiBins -2.247111412
  add PhiBins -2.225294796
  add PhiBins -2.203478181
  add PhiBins -2.181661565
  add PhiBins -2.159844949
  add PhiBins -2.138028334
  add PhiBins -2.116211718
  add PhiBins -2.094395102
  add PhiBins -2.072578487
  add PhiBins -2.050761871
  add PhiBins -2.028945255
  add PhiBins -2.00712864
  add PhiBins -1.985312024
  add PhiBins -1.963495408
  add PhiBins -1.941678793
  add PhiBins -1.919862177
  add PhiBins -1.898045562
  add PhiBins -1.876228946
  add PhiBins -1.85441233
  add PhiBins -1.832595715
  add PhiBins -1.810779099
  add PhiBins -1.788962483
  add PhiBins -1.767145868
  add PhiBins -1.745329252
  add PhiBins -1.723512636
  add PhiBins -1.701696021
  add PhiBins -1.679879405
  add PhiBins -1.658062789
  add PhiBins -1.636246174
  add PhiBins -1.614429558
  add PhiBins -1.592612942
  add PhiBins -1.570796327
  add PhiBins -1.548979711
  add PhiBins -1.527163095
  add PhiBins -1.50534648
  add PhiBins -1.483529864
  add PhiBins -1.461713249
  add PhiBins -1.439896633
  add PhiBins -1.418080017
  add PhiBins -1.396263402
  add PhiBins -1.374446786
  add PhiBins -1.35263017
  add PhiBins -1.330813555
  add PhiBins -1.308996939
  add PhiBins -1.287180323
  add PhiBins -1.265363708
  add PhiBins -1.243547092
  add PhiBins -1.221730476
  add PhiBins -1.199913861
  add PhiBins -1.178097245
  add PhiBins -1.156280629
  add PhiBins -1.134464014
  add PhiBins -1.112647398
  add PhiBins -1.090830782
  add PhiBins -1.069014167
  add PhiBins -1.047197551
  add PhiBins -1.025380936
  add PhiBins -1.00356432
  add PhiBins -0.9817477042
  add PhiBins -0.9599310886
  add PhiBins -0.9381144729
  add PhiBins -0.9162978573
  add PhiBins -0.8944812416
  add PhiBins -0.872664626
  add PhiBins -0.8508480103
  add PhiBins -0.8290313947
  add PhiBins -0.807214779
  add PhiBins -0.7853981634
  add PhiBins -0.7635815477
  add PhiBins -0.7417649321
  add PhiBins -0.7199483164
  add PhiBins -0.6981317008
  add PhiBins -0.6763150851
  add PhiBins -0.6544984695
  add PhiBins -0.6326818538
  add PhiBins -0.6108652382
  add PhiBins -0.5890486225
  add PhiBins -0.5672320069
  add PhiBins -0.5454153912
  add PhiBins -0.5235987756
  add PhiBins -0.5017821599
  add PhiBins -0.4799655443
  add PhiBins -0.4581489286
  add PhiBins -0.436332313
  add PhiBins -0.4145156973
  add PhiBins -0.3926990817
  add PhiBins -0.370882466
  add PhiBins -0.3490658504
  add PhiBins -0.3272492347
  add PhiBins -0.3054326191
  add PhiBins -0.2836160034
  add PhiBins -0.2617993878
  add PhiBins -0.2399827721
  add PhiBins -0.2181661565
  add PhiBins -0.1963495408
  add PhiBins -0.1745329252
  add PhiBins -0.1527163095
  add PhiBins -0.1308996939
  add PhiBins -0.1090830782
  add PhiBins -0.0872664626
  add PhiBins -0.06544984695
  add PhiBins -0.0436332313
  add PhiBins -0.02181661565
  add PhiBins 0
  add PhiBins 0.02181661565
  add PhiBins 0.0436332313
  add PhiBins 0.06544984695
  add PhiBins 0.0872664626
  add PhiBins 0.1090830782
  add PhiBins 0.1308996939
  add PhiBins 0.1527163095
  add PhiBins 0.1745329252
  add PhiBins 0.1963495408
  add PhiBins 0.2181661565
  add PhiBins 0.2399827721
  add PhiBins 0.2617993878
  add PhiBins 0.2836160034
  add PhiBins 0.3054326191
  add PhiBins 0.3272492347
  add PhiBins 0.3490658504
  add PhiBins 0.370882466
  add PhiBins 0.3926990817
  add PhiBins 0.4145156973
  add PhiBins 0.436332313
  add PhiBins 0.4581489286
  add PhiBins 0.4799655443
  add PhiBins 0.5017821599
  add PhiBins 0.5235987756
  add PhiBins 0.5454153912
  add PhiBins 0.5672320069
  add PhiBins 0.5890486225
  add PhiBins 0.6108652382
  add PhiBins 0.6326818538
  add PhiBins 0.6544984695
  add PhiBins 0.6763150851
  add PhiBins 0.6981317008
  add PhiBins 0.7199483164
  add PhiBins 0.7417649321
  add PhiBins 0.7635815477
  add PhiBins 0.7853981634
  add PhiBins 0.807214779
  add PhiBins 0.8290313947
  add PhiBins 0.8508480103
  add PhiBins 0.872664626
  add PhiBins 0.8944812416
  add PhiBins 0.9162978573
  add PhiBins 0.9381144729
  add PhiBins 0.9599310886
  add PhiBins 0.9817477042
  add PhiBins 1.00356432
  add PhiBins 1.025380936
  add PhiBins 1.047197551
  add PhiBins 1.069014167
  add PhiBins 1.090830782
  add PhiBins 1.112647398
  add PhiBins 1.134464014
  add PhiBins 1.156280629
  add PhiBins 1.178097245
  add PhiBins 1.199913861
  add PhiBins 1.221730476
  add PhiBins 1.243547092
  add PhiBins 1.265363708
  add PhiBins 1.287180323
  add PhiBins 1.308996939
  add PhiBins 1.330813555
  add PhiBins 1.35263017
  add PhiBins 1.374446786
  add PhiBins 1.396263402
  add PhiBins 1.418080017
  add PhiBins 1.439896633
  add PhiBins 1.461713249
  add PhiBins 1.483529864
  add PhiBins 1.50534648
  add PhiBins 1.527163095
  add PhiBins 1.548979711
  add PhiBins 1.570796327
  add PhiBins 1.592612942
  add PhiBins 1.614429558
  add PhiBins 1.636246174
  add PhiBins 1.658062789
  add PhiBins 1.679879405
  add PhiBins 1.701696021
  add PhiBins 1.723512636
  add PhiBins 1.745329252
  add PhiBins 1.767145868
  add PhiBins 1.788962483
  add PhiBins 1.810779099
  add PhiBins 1.832595715
  add PhiBins 1.85441233
  add PhiBins 1.876228946
  add PhiBins 1.898045562
  add PhiBins 1.919862177
  add PhiBins 1.941678793
  add PhiBins 1.963495408
  add PhiBins 1.985312024
  add PhiBins 2.00712864
  add PhiBins 2.028945255
  add PhiBins 2.050761871
  add PhiBins 2.072578487
  add PhiBins 2.094395102
  add PhiBins 2.116211718
  add PhiBins 2.138028334
  add PhiBins 2.159844949
  add PhiBins 2.181661565
  add PhiBins 2.203478181
  add PhiBins 2.225294796
  add PhiBins 2.247111412
  add PhiBins 2.268928028
  add PhiBins 2.290744643
  add PhiBins 2.312561259
  add PhiBins 2.334377875
  add PhiBins 2.35619449
  add PhiBins 2.378011106
  add PhiBins 2.399827721
  add PhiBins 2.421644337
  add PhiBins 2.443460953
  add PhiBins 2.465277568
  add PhiBins 2.487094184
  add PhiBins 2.5089108
  add PhiBins 2.530727415
  add PhiBins 2.552544031
  add PhiBins 2.574360647
  add PhiBins 2.596177262
  add PhiBins 2.617993878
  add PhiBins 2.639810494
  add PhiBins 2.661627109
  add PhiBins 2.683443725
  add PhiBins 2.705260341
  add PhiBins 2.727076956
  add PhiBins 2.748893572
  add PhiBins 2.770710188
  add PhiBins 2.792526803
  add PhiBins 2.814343419
  add PhiBins 2.836160034
  add PhiBins 2.85797665
  add PhiBins 2.879793266
  add PhiBins 2.901609881
  add PhiBins 2.923426497
  add PhiBins 2.945243113
  add PhiBins 2.967059728
  add PhiBins 2.988876344
  add PhiBins 3.01069296
  add PhiBins 3.032509575
  add PhiBins 3.054326191
  add PhiBins 3.076142807
  add PhiBins 3.097959422
  add PhiBins 3.119776038
  add PhiBins 3.141592654
  foreach eta {-1.479 -1.457281752 -1.435563504 -1.413845255 -1.392127007 -1.370408759 -1.348690511 -1.326972263 -1.305254015 -1.283535766 -1.261817518 -1.24009927 -1.218381022 -1.196662774 -1.174944526 -1.153226277 -1.131508029 -1.109789781 -1.088071533 -1.066353285 -1.044635036 -1.022916788 -1.00119854 -0.979480292 -0.9577620438 -0.9360437956 -0.9143255474 -0.8926072993 -0.8708890511 -0.8491708029 -0.8274525547 -0.8057343066 -0.7840160584 -0.7622978102 -0.740579562 -0.7188613139 -0.6971430657 -0.6754248175 -0.6537065693 -0.6319883212 -0.610270073 -0.5885518248 -0.5668335766 -0.5451153285 -0.5233970803 -0.5016788321 -0.4799605839 -0.4582423358 -0.4365240876 -0.4148058394 -0.3930875912 -0.3713693431 -0.3496510949 -0.3279328467 -0.3062145985 -0.2844963504 -0.2627781022 -0.241059854 -0.2193416058 -0.1976233577 -0.1759051095 -0.1541868613 -0.1324686131 -0.110750365 -0.08903211679 -0.06731386861 -0.04559562044 -0.02387737226 -0.002159124088 0.01955912409 0.04127737226 0.06299562044 0.08471386861 0.1064321168 0.128150365 0.1498686131 0.1715868613 0.1933051095 0.2150233577 0.2367416058 0.258459854 0.2801781022 0.3018963504 0.3236145985 0.3453328467 0.3670510949 0.3887693431 0.4104875912 0.4322058394 0.4539240876 0.4756423358 0.4973605839 0.5190788321 0.5407970803 0.5625153285 0.5842335766 0.6059518248 0.627670073 0.6493883212 0.6711065693 0.6928248175 0.7145430657 0.7362613139 0.757979562 0.7796978102 0.8014160584 0.8231343066 0.8448525547 0.8665708029 0.8882890511 0.9100072993 0.9317255474 0.9534437956 0.9751620438 0.996880292 1.01859854 1.040316788 1.062035036 1.083753285 1.105471533 1.127189781 1.148908029 1.170626277 1.192344526 1.214062774 1.235781022 1.25749927 1.279217518 1.300935766 1.322654015 1.344372263 1.366090511 1.387808759 1.409527007 1.431245255 1.452963504 1.474681752 1.4964} {
    add EtaPhiBins $eta $PhiBins
  }

  set PhiBins {}
  add PhiBins -3.141592654
  add PhiBins -3.119776038
  add PhiBins -3.097959422
  add PhiBins -3.076142807
  add PhiBins -3.054326191
  add PhiBins -3.032509575
  add PhiBins -3.01069296
  add PhiBins -2.988876344
  add PhiBins -2.967059728
  add PhiBins -2.945243113
  add PhiBins -2.923426497
  add PhiBins -2.901609881
  add PhiBins -2.879793266
  add PhiBins -2.85797665
  add PhiBins -2.836160034
  add PhiBins -2.814343419
  add PhiBins -2.792526803
  add PhiBins -2.770710188
  add PhiBins -2.748893572
  add PhiBins -2.727076956
  add PhiBins -2.705260341
  add PhiBins -2.683443725
  add PhiBins -2.661627109
  add PhiBins -2.639810494
  add PhiBins -2.617993878
  add PhiBins -2.596177262
  add PhiBins -2.574360647
  add PhiBins -2.552544031
  add PhiBins -2.530727415
  add PhiBins -2.5089108
  add PhiBins -2.487094184
  add PhiBins -2.465277568
  add PhiBins -2.443460953
  add PhiBins -2.421644337
  add PhiBins -2.399827721
  add PhiBins -2.378011106
  add PhiBins -2.35619449
  add PhiBins -2.334377875
  add PhiBins -2.312561259
  add PhiBins -2.290744643
  add PhiBins -2.268928028
  add PhiBins -2.247111412
  add PhiBins -2.225294796
  add PhiBins -2.203478181
  add PhiBins -2.181661565
  add PhiBins -2.159844949
  add PhiBins -2.138028334
  add PhiBins -2.116211718
  add PhiBins -2.094395102
  add PhiBins -2.072578487
  add PhiBins -2.050761871
  add PhiBins -2.028945255
  add PhiBins -2.00712864
  add PhiBins -1.985312024
  add PhiBins -1.963495408
  add PhiBins -1.941678793
  add PhiBins -1.919862177
  add PhiBins -1.898045562
  add PhiBins -1.876228946
  add PhiBins -1.85441233
  add PhiBins -1.832595715
  add PhiBins -1.810779099
  add PhiBins -1.788962483
  add PhiBins -1.767145868
  add PhiBins -1.745329252
  add PhiBins -1.723512636
  add PhiBins -1.701696021
  add PhiBins -1.679879405
  add PhiBins -1.658062789
  add PhiBins -1.636246174
  add PhiBins -1.614429558
  add PhiBins -1.592612942
  add PhiBins -1.570796327
  add PhiBins -1.548979711
  add PhiBins -1.527163095
  add PhiBins -1.50534648
  add PhiBins -1.483529864
  add PhiBins -1.461713249
  add PhiBins -1.439896633
  add PhiBins -1.418080017
  add PhiBins -1.396263402
  add PhiBins -1.374446786
  add PhiBins -1.35263017
  add PhiBins -1.330813555
  add PhiBins -1.308996939
  add PhiBins -1.287180323
  add PhiBins -1.265363708
  add PhiBins -1.243547092
  add PhiBins -1.221730476
  add PhiBins -1.199913861
  add PhiBins -1.178097245
  add PhiBins -1.156280629
  add PhiBins -1.134464014
  add PhiBins -1.112647398
  add PhiBins -1.090830782
  add PhiBins -1.069014167
  add PhiBins -1.047197551
  add PhiBins -1.025380936
  add PhiBins -1.00356432
  add PhiBins -0.9817477042
  add PhiBins -0.9599310886
  add PhiBins -0.9381144729
  add PhiBins -0.9162978573
  add PhiBins -0.8944812416
  add PhiBins -0.872664626
  add PhiBins -0.8508480103
  add PhiBins -0.8290313947
  add PhiBins -0.807214779
  add PhiBins -0.7853981634
  add PhiBins -0.7635815477
  add PhiBins -0.7417649321
  add PhiBins -0.7199483164
  add PhiBins -0.6981317008
  add PhiBins -0.6763150851
  add PhiBins -0.6544984695
  add PhiBins -0.6326818538
  add PhiBins -0.6108652382
  add PhiBins -0.5890486225
  add PhiBins -0.5672320069
  add PhiBins -0.5454153912
  add PhiBins -0.5235987756
  add PhiBins -0.5017821599
  add PhiBins -0.4799655443
  add PhiBins -0.4581489286
  add PhiBins -0.436332313
  add PhiBins -0.4145156973
  add PhiBins -0.3926990817
  add PhiBins -0.370882466
  add PhiBins -0.3490658504
  add PhiBins -0.3272492347
  add PhiBins -0.3054326191
  add PhiBins -0.2836160034
  add PhiBins -0.2617993878
  add PhiBins -0.2399827721
  add PhiBins -0.2181661565
  add PhiBins -0.1963495408
  add PhiBins -0.1745329252
  add PhiBins -0.1527163095
  add PhiBins -0.1308996939
  add PhiBins -0.1090830782
  add PhiBins -0.0872664626
  add PhiBins -0.06544984695
  add PhiBins -0.0436332313
  add PhiBins -0.02181661565
  add PhiBins 0
  add PhiBins 0.02181661565
  add PhiBins 0.0436332313
  add PhiBins 0.06544984695
  add PhiBins 0.0872664626
  add PhiBins 0.1090830782
  add PhiBins 0.1308996939
  add PhiBins 0.1527163095
  add PhiBins 0.1745329252
  add PhiBins 0.1963495408
  add PhiBins 0.2181661565
  add PhiBins 0.2399827721
  add PhiBins 0.2617993878
  add PhiBins 0.2836160034
  add PhiBins 0.3054326191
  add PhiBins 0.3272492347
  add PhiBins 0.3490658504
  add PhiBins 0.370882466
  add PhiBins 0.3926990817
  add PhiBins 0.4145156973
  add PhiBins 0.436332313
  add PhiBins 0.4581489286
  add PhiBins 0.4799655443
  add PhiBins 0.5017821599
  add PhiBins 0.5235987756
  add PhiBins 0.5454153912
  add PhiBins 0.5672320069
  add PhiBins 0.5890486225
  add PhiBins 0.6108652382
  add PhiBins 0.6326818538
  add PhiBins 0.6544984695
  add PhiBins 0.6763150851
  add PhiBins 0.6981317008
  add PhiBins 0.7199483164
  add PhiBins 0.7417649321
  add PhiBins 0.7635815477
  add PhiBins 0.7853981634
  add PhiBins 0.807214779
  add PhiBins 0.8290313947
  add PhiBins 0.8508480103
  add PhiBins 0.872664626
  add PhiBins 0.8944812416
  add PhiBins 0.9162978573
  add PhiBins 0.9381144729
  add PhiBins 0.9599310886
  add PhiBins 0.9817477042
  add PhiBins 1.00356432
  add PhiBins 1.025380936
  add PhiBins 1.047197551
  add PhiBins 1.069014167
  add PhiBins 1.090830782
  add PhiBins 1.112647398
  add PhiBins 1.134464014
  add PhiBins 1.156280629
  add PhiBins 1.178097245
  add PhiBins 1.199913861
  add PhiBins 1.221730476
  add PhiBins 1.243547092
  add PhiBins 1.265363708
  add PhiBins 1.287180323
  add PhiBins 1.308996939
  add PhiBins 1.330813555
  add PhiBins 1.35263017
  add PhiBins 1.374446786
  add PhiBins 1.396263402
  add PhiBins 1.418080017
  add PhiBins 1.439896633
  add PhiBins 1.461713249
  add PhiBins 1.483529864
  add PhiBins 1.50534648
  add PhiBins 1.527163095
  add PhiBins 1.548979711
  add PhiBins 1.570796327
  add PhiBins 1.592612942
  add PhiBins 1.614429558
  add PhiBins 1.636246174
  add PhiBins 1.658062789
  add PhiBins 1.679879405
  add PhiBins 1.701696021
  add PhiBins 1.723512636
  add PhiBins 1.745329252
  add PhiBins 1.767145868
  add PhiBins 1.788962483
  add PhiBins 1.810779099
  add PhiBins 1.832595715
  add PhiBins 1.85441233
  add PhiBins 1.876228946
  add PhiBins 1.898045562
  add PhiBins 1.919862177
  add PhiBins 1.941678793
  add PhiBins 1.963495408
  add PhiBins 1.985312024
  add PhiBins 2.00712864
  add PhiBins 2.028945255
  add PhiBins 2.050761871
  add PhiBins 2.072578487
  add PhiBins 2.094395102
  add PhiBins 2.116211718
  add PhiBins 2.138028334
  add PhiBins 2.159844949
  add PhiBins 2.181661565
  add PhiBins 2.203478181
  add PhiBins 2.225294796
  add PhiBins 2.247111412
  add PhiBins 2.268928028
  add PhiBins 2.290744643
  add PhiBins 2.312561259
  add PhiBins 2.334377875
  add PhiBins 2.35619449
  add PhiBins 2.378011106
  add PhiBins 2.399827721
  add PhiBins 2.421644337
  add PhiBins 2.443460953
  add PhiBins 2.465277568
  add PhiBins 2.487094184
  add PhiBins 2.5089108
  add PhiBins 2.530727415
  add PhiBins 2.552544031
  add PhiBins 2.574360647
  add PhiBins 2.596177262
  add PhiBins 2.617993878
  add PhiBins 2.639810494
  add PhiBins 2.661627109
  add PhiBins 2.683443725
  add PhiBins 2.705260341
  add PhiBins 2.727076956
  add PhiBins 2.748893572
  add PhiBins 2.770710188
  add PhiBins 2.792526803
  add PhiBins 2.814343419
  add PhiBins 2.836160034
  add PhiBins 2.85797665
  add PhiBins 2.879793266
  add PhiBins 2.901609881
  add PhiBins 2.923426497
  add PhiBins 2.945243113
  add PhiBins 2.967059728
  add PhiBins 2.988876344
  add PhiBins 3.01069296
  add PhiBins 3.032509575
  add PhiBins 3.054326191
  add PhiBins 3.076142807
  add PhiBins 3.097959422
  add PhiBins 3.119776038
  add PhiBins 3.141592654
  foreach eta {-2.9406 -2.918718182 -2.896836364 -2.874954545 -2.853072727 -2.831190909 -2.809309091 -2.787427273 -2.765545455 -2.743663636 -2.721781818 -2.6999 -2.678018182 -2.656136364 -2.634254545 -2.612372727 -2.590490909 -2.568609091 -2.546727273 -2.524845455 -2.502963636 -2.481081818 -2.4592 -2.437318182 -2.415436364 -2.393554545 -2.371672727 -2.349790909 -2.327909091 -2.306027273 -2.284145455 -2.262263636 -2.240381818 -2.2185 -2.196618182 -2.174736364 -2.152854545 -2.130972727 -2.109090909 -2.087209091 -2.065327273 -2.043445455 -2.021563636 -1.999681818 -1.9778 -1.955918182 -1.934036364 -1.912154545 -1.890272727 -1.868390909 -1.846509091 -1.824627273 -1.802745455 -1.780863636 -1.758981818 -1.7371 -1.715218182 -1.693336364 -1.671454545 -1.649572727 -1.627690909 -1.605809091 -1.583927273 -1.562045455 -1.540163636 -1.518281818 -1.4964} {
    add EtaPhiBins $eta $PhiBins
  }

  set PhiBins {}
  add PhiBins -3.141592654
  add PhiBins -3.119776038
  add PhiBins -3.097959422
  add PhiBins -3.076142807
  add PhiBins -3.054326191
  add PhiBins -3.032509575
  add PhiBins -3.01069296
  add PhiBins -2.988876344
  add PhiBins -2.967059728
  add PhiBins -2.945243113
  add PhiBins -2.923426497
  add PhiBins -2.901609881
  add PhiBins -2.879793266
  add PhiBins -2.85797665
  add PhiBins -2.836160034
  add PhiBins -2.814343419
  add PhiBins -2.792526803
  add PhiBins -2.770710188
  add PhiBins -2.748893572
  add PhiBins -2.727076956
  add PhiBins -2.705260341
  add PhiBins -2.683443725
  add PhiBins -2.661627109
  add PhiBins -2.639810494
  add PhiBins -2.617993878
  add PhiBins -2.596177262
  add PhiBins -2.574360647
  add PhiBins -2.552544031
  add PhiBins -2.530727415
  add PhiBins -2.5089108
  add PhiBins -2.487094184
  add PhiBins -2.465277568
  add PhiBins -2.443460953
  add PhiBins -2.421644337
  add PhiBins -2.399827721
  add PhiBins -2.378011106
  add PhiBins -2.35619449
  add PhiBins -2.334377875
  add PhiBins -2.312561259
  add PhiBins -2.290744643
  add PhiBins -2.268928028
  add PhiBins -2.247111412
  add PhiBins -2.225294796
  add PhiBins -2.203478181
  add PhiBins -2.181661565
  add PhiBins -2.159844949
  add PhiBins -2.138028334
  add PhiBins -2.116211718
  add PhiBins -2.094395102
  add PhiBins -2.072578487
  add PhiBins -2.050761871
  add PhiBins -2.028945255
  add PhiBins -2.00712864
  add PhiBins -1.985312024
  add PhiBins -1.963495408
  add PhiBins -1.941678793
  add PhiBins -1.919862177
  add PhiBins -1.898045562
  add PhiBins -1.876228946
  add PhiBins -1.85441233
  add PhiBins -1.832595715
  add PhiBins -1.810779099
  add PhiBins -1.788962483
  add PhiBins -1.767145868
  add PhiBins -1.745329252
  add PhiBins -1.723512636
  add PhiBins -1.701696021
  add PhiBins -1.679879405
  add PhiBins -1.658062789
  add PhiBins -1.636246174
  add PhiBins -1.614429558
  add PhiBins -1.592612942
  add PhiBins -1.570796327
  add PhiBins -1.548979711
  add PhiBins -1.527163095
  add PhiBins -1.50534648
  add PhiBins -1.483529864
  add PhiBins -1.461713249
  add PhiBins -1.439896633
  add PhiBins -1.418080017
  add PhiBins -1.396263402
  add PhiBins -1.374446786
  add PhiBins -1.35263017
  add PhiBins -1.330813555
  add PhiBins -1.308996939
  add PhiBins -1.287180323
  add PhiBins -1.265363708
  add PhiBins -1.243547092
  add PhiBins -1.221730476
  add PhiBins -1.199913861
  add PhiBins -1.178097245
  add PhiBins -1.156280629
  add PhiBins -1.134464014
  add PhiBins -1.112647398
  add PhiBins -1.090830782
  add PhiBins -1.069014167
  add PhiBins -1.047197551
  add PhiBins -1.025380936
  add PhiBins -1.00356432
  add PhiBins -0.9817477042
  add PhiBins -0.9599310886
  add PhiBins -0.9381144729
  add PhiBins -0.9162978573
  add PhiBins -0.8944812416
  add PhiBins -0.872664626
  add PhiBins -0.8508480103
  add PhiBins -0.8290313947
  add PhiBins -0.807214779
  add PhiBins -0.7853981634
  add PhiBins -0.7635815477
  add PhiBins -0.7417649321
  add PhiBins -0.7199483164
  add PhiBins -0.6981317008
  add PhiBins -0.6763150851
  add PhiBins -0.6544984695
  add PhiBins -0.6326818538
  add PhiBins -0.6108652382
  add PhiBins -0.5890486225
  add PhiBins -0.5672320069
  add PhiBins -0.5454153912
  add PhiBins -0.5235987756
  add PhiBins -0.5017821599
  add PhiBins -0.4799655443
  add PhiBins -0.4581489286
  add PhiBins -0.436332313
  add PhiBins -0.4145156973
  add PhiBins -0.3926990817
  add PhiBins -0.370882466
  add PhiBins -0.3490658504
  add PhiBins -0.3272492347
  add PhiBins -0.3054326191
  add PhiBins -0.2836160034
  add PhiBins -0.2617993878
  add PhiBins -0.2399827721
  add PhiBins -0.2181661565
  add PhiBins -0.1963495408
  add PhiBins -0.1745329252
  add PhiBins -0.1527163095
  add PhiBins -0.1308996939
  add PhiBins -0.1090830782
  add PhiBins -0.0872664626
  add PhiBins -0.06544984695
  add PhiBins -0.0436332313
  add PhiBins -0.02181661565
  add PhiBins 0
  add PhiBins 0.02181661565
  add PhiBins 0.0436332313
  add PhiBins 0.06544984695
  add PhiBins 0.0872664626
  add PhiBins 0.1090830782
  add PhiBins 0.1308996939
  add PhiBins 0.1527163095
  add PhiBins 0.1745329252
  add PhiBins 0.1963495408
  add PhiBins 0.2181661565
  add PhiBins 0.2399827721
  add PhiBins 0.2617993878
  add PhiBins 0.2836160034
  add PhiBins 0.3054326191
  add PhiBins 0.3272492347
  add PhiBins 0.3490658504
  add PhiBins 0.370882466
  add PhiBins 0.3926990817
  add PhiBins 0.4145156973
  add PhiBins 0.436332313
  add PhiBins 0.4581489286
  add PhiBins 0.4799655443
  add PhiBins 0.5017821599
  add PhiBins 0.5235987756
  add PhiBins 0.5454153912
  add PhiBins 0.5672320069
  add PhiBins 0.5890486225
  add PhiBins 0.6108652382
  add PhiBins 0.6326818538
  add PhiBins 0.6544984695
  add PhiBins 0.6763150851
  add PhiBins 0.6981317008
  add PhiBins 0.7199483164
  add PhiBins 0.7417649321
  add PhiBins 0.7635815477
  add PhiBins 0.7853981634
  add PhiBins 0.807214779
  add PhiBins 0.8290313947
  add PhiBins 0.8508480103
  add PhiBins 0.872664626
  add PhiBins 0.8944812416
  add PhiBins 0.9162978573
  add PhiBins 0.9381144729
  add PhiBins 0.9599310886
  add PhiBins 0.9817477042
  add PhiBins 1.00356432
  add PhiBins 1.025380936
  add PhiBins 1.047197551
  add PhiBins 1.069014167
  add PhiBins 1.090830782
  add PhiBins 1.112647398
  add PhiBins 1.134464014
  add PhiBins 1.156280629
  add PhiBins 1.178097245
  add PhiBins 1.199913861
  add PhiBins 1.221730476
  add PhiBins 1.243547092
  add PhiBins 1.265363708
  add PhiBins 1.287180323
  add PhiBins 1.308996939
  add PhiBins 1.330813555
  add PhiBins 1.35263017
  add PhiBins 1.374446786
  add PhiBins 1.396263402
  add PhiBins 1.418080017
  add PhiBins 1.439896633
  add PhiBins 1.461713249
  add PhiBins 1.483529864
  add PhiBins 1.50534648
  add PhiBins 1.527163095
  add PhiBins 1.548979711
  add PhiBins 1.570796327
  add PhiBins 1.592612942
  add PhiBins 1.614429558
  add PhiBins 1.636246174
  add PhiBins 1.658062789
  add PhiBins 1.679879405
  add PhiBins 1.701696021
  add PhiBins 1.723512636
  add PhiBins 1.745329252
  add PhiBins 1.767145868
  add PhiBins 1.788962483
  add PhiBins 1.810779099
  add PhiBins 1.832595715
  add PhiBins 1.85441233
  add PhiBins 1.876228946
  add PhiBins 1.898045562
  add PhiBins 1.919862177
  add PhiBins 1.941678793
  add PhiBins 1.963495408
  add PhiBins 1.985312024
  add PhiBins 2.00712864
  add PhiBins 2.028945255
  add PhiBins 2.050761871
  add PhiBins 2.072578487
  add PhiBins 2.094395102
  add PhiBins 2.116211718
  add PhiBins 2.138028334
  add PhiBins 2.159844949
  add PhiBins 2.181661565
  add PhiBins 2.203478181
  add PhiBins 2.225294796
  add PhiBins 2.247111412
  add PhiBins 2.268928028
  add PhiBins 2.290744643
  add PhiBins 2.312561259
  add PhiBins 2.334377875
  add PhiBins 2.35619449
  add PhiBins 2.378011106
  add PhiBins 2.399827721
  add PhiBins 2.421644337
  add PhiBins 2.443460953
  add PhiBins 2.465277568
  add PhiBins 2.487094184
  add PhiBins 2.5089108
  add PhiBins 2.530727415
  add PhiBins 2.552544031
  add PhiBins 2.574360647
  add PhiBins 2.596177262
  add PhiBins 2.617993878
  add PhiBins 2.639810494
  add PhiBins 2.661627109
  add PhiBins 2.683443725
  add PhiBins 2.705260341
  add PhiBins 2.727076956
  add PhiBins 2.748893572
  add PhiBins 2.770710188
  add PhiBins 2.792526803
  add PhiBins 2.814343419
  add PhiBins 2.836160034
  add PhiBins 2.85797665
  add PhiBins 2.879793266
  add PhiBins 2.901609881
  add PhiBins 2.923426497
  add PhiBins 2.945243113
  add PhiBins 2.967059728
  add PhiBins 2.988876344
  add PhiBins 3.01069296
  add PhiBins 3.032509575
  add PhiBins 3.054326191
  add PhiBins 3.076142807
  add PhiBins 3.097959422
  add PhiBins 3.119776038
  add PhiBins 3.141592654
  foreach eta {1.5138 1.535681818 1.557563636 1.579445455 1.601327273 1.623209091 1.645090909 1.666972727 1.688854545 1.710736364 1.732618182 1.7545 1.776381818 1.798263636 1.820145455 1.842027273 1.863909091 1.885790909 1.907672727 1.929554545 1.951436364 1.973318182 1.9952 2.017081818 2.038963636 2.060845455 2.082727273 2.104609091 2.126490909 2.148372727 2.170254545 2.192136364 2.214018182 2.2359 2.257781818 2.279663636 2.301545455 2.323427273 2.345309091 2.367190909 2.389072727 2.410954545 2.432836364 2.454718182 2.4766 2.498481818 2.520363636 2.542245455 2.564127273 2.586009091 2.607890909 2.629772727 2.651654545 2.673536364 2.695418182 2.7173 2.739181818 2.761063636 2.782945455 2.804827273 2.826709091 2.848590909 2.870472727 2.892354545 2.914236364 2.936118182 2.958} {
    add EtaPhiBins $eta $PhiBins
  }

  set PhiBins {}
  add PhiBins -3.141592654
  add PhiBins -2.924931091
  add PhiBins -2.708269529
  add PhiBins -2.491607967
  add PhiBins -2.274946404
  add PhiBins -2.058284842
  add PhiBins -1.84162328
  add PhiBins -1.624961717
  add PhiBins -1.408300155
  add PhiBins -1.191638593
  add PhiBins -0.9749770304
  add PhiBins -0.7583154681
  add PhiBins -0.5416539058
  add PhiBins -0.3249923435
  add PhiBins -0.1083307812
  add PhiBins 0.1083307812
  add PhiBins 0.3249923435
  add PhiBins 0.5416539058
  add PhiBins 0.7583154681
  add PhiBins 0.9749770304
  add PhiBins 1.191638593
  add PhiBins 1.408300155
  add PhiBins 1.624961717
  add PhiBins 1.84162328
  add PhiBins 2.058284842
  add PhiBins 2.274946404
  add PhiBins 2.491607967
  add PhiBins 2.708269529
  add PhiBins 2.924931091
  add PhiBins 3.141592654
  foreach eta {-5 -4.661111111 -4.447222222 -4.233333333 -4.019444444 -3.805555556 -3.591666667 -3.377777778 -3.163888889 -2.958 3.125 3.34375 3.5625 3.78125 4 4.21875 4.4375 4.65625 5} {
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
  add PhiBins -3.141592654
  add PhiBins -3.033261872
  add PhiBins -2.924931091
  add PhiBins -2.81660031
  add PhiBins -2.708269529
  add PhiBins -2.599938748
  add PhiBins -2.491607967
  add PhiBins -2.383277185
  add PhiBins -2.274946404
  add PhiBins -2.166615623
  add PhiBins -2.058284842
  add PhiBins -1.949954061
  add PhiBins -1.84162328
  add PhiBins -1.733292499
  add PhiBins -1.624961717
  add PhiBins -1.516630936
  add PhiBins -1.408300155
  add PhiBins -1.299969374
  add PhiBins -1.191638593
  add PhiBins -1.083307812
  add PhiBins -0.9749770304
  add PhiBins -0.8666462493
  add PhiBins -0.7583154681
  add PhiBins -0.6499846869
  add PhiBins -0.5416539058
  add PhiBins -0.4333231246
  add PhiBins -0.3249923435
  add PhiBins -0.2166615623
  add PhiBins -0.1083307812
  add PhiBins 0
  add PhiBins 0.1083307812
  add PhiBins 0.2166615623
  add PhiBins 0.3249923435
  add PhiBins 0.4333231246
  add PhiBins 0.5416539058
  add PhiBins 0.6499846869
  add PhiBins 0.7583154681
  add PhiBins 0.8666462493
  add PhiBins 0.9749770304
  add PhiBins 1.083307812
  add PhiBins 1.191638593
  add PhiBins 1.299969374
  add PhiBins 1.408300155
  add PhiBins 1.516630936
  add PhiBins 1.624961717
  add PhiBins 1.733292499
  add PhiBins 1.84162328
  add PhiBins 1.949954061
  add PhiBins 2.058284842
  add PhiBins 2.166615623
  add PhiBins 2.274946404
  add PhiBins 2.383277185
  add PhiBins 2.491607967
  add PhiBins 2.599938748
  add PhiBins 2.708269529
  add PhiBins 2.81660031
  add PhiBins 2.924931091
  add PhiBins 3.033261872
  add PhiBins 3.141592654
  foreach eta {-1.566 -1.4587 -1.3514 -1.2441 -1.1368 -1.0295 -0.9222 -0.8149 -0.7076 -0.6003 -0.493 -0.3857 -0.2784 -0.1711 -0.0638 0.0435 0.1508 0.2581 0.3654 0.4727 0.58 0.6873 0.7946 0.9019 1.0092 1.1165 1.2238 1.3311 1.4384 1.5457 1.653} {
    add EtaPhiBins $eta $PhiBins
  }

  set PhiBins {}
  add PhiBins -3.141592654
  add PhiBins -2.924931091
  add PhiBins -2.708269529
  add PhiBins -2.491607967
  add PhiBins -2.274946404
  add PhiBins -2.058284842
  add PhiBins -1.84162328
  add PhiBins -1.624961717
  add PhiBins -1.408300155
  add PhiBins -1.191638593
  add PhiBins -0.9749770304
  add PhiBins -0.7583154681
  add PhiBins -0.5416539058
  add PhiBins -0.3249923435
  add PhiBins -0.1083307812
  add PhiBins 0.1083307812
  add PhiBins 0.3249923435
  add PhiBins 0.5416539058
  add PhiBins 0.7583154681
  add PhiBins 0.9749770304
  add PhiBins 1.191638593
  add PhiBins 1.408300155
  add PhiBins 1.624961717
  add PhiBins 1.84162328
  add PhiBins 2.058284842
  add PhiBins 2.274946404
  add PhiBins 2.491607967
  add PhiBins 2.708269529
  add PhiBins 2.924931091
  add PhiBins 3.141592654
  foreach eta {-4.35 -4.125 -3.9 -3.675 -3.45 -3.225 -3 -2.868 -2.607142857 -2.398285714 -2.193428571 -2.026857143 -1.887142857 -1.765714286 -1.653 1.74 1.858571429 1.994571429 2.153571429 2.347428571 2.564285714 2.805714286 2.95 3.175 3.4 3.625 3.85 4.075 4.3 4.525} {
    add EtaPhiBins $eta $PhiBins
  }

  set PhiBins {}
  add PhiBins -3.141592654
  add PhiBins -2.692793703
  add PhiBins -2.243994753
  add PhiBins -1.795195802
  add PhiBins -1.346396852
  add PhiBins -0.897597901
  add PhiBins -0.4487989505
  add PhiBins 0
  add PhiBins 0.4487989505
  add PhiBins 0.897597901
  add PhiBins 1.346396852
  add PhiBins 1.795195802
  add PhiBins 2.243994753
  add PhiBins 2.692793703
  add PhiBins 3.141592654
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
  set ZVertexResolution {0.0025}
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

module Merger HLTEFlowMerger {
  add InputArray TrackPileUpSubtractor/eflowTracks
  add InputArray ECal/eflowPhotons
  add InputArray HCal/eflowNeutralHadrons
  set OutputArray eflow
}

module PdgCodeFilter HLTEFlowPtFilter {
  set InputArray HLTEFlowMerger/eflow
  set OutputArray eflow
  set PTMin 0.6
}

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
  add UseCharged          false false
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
  set InputArray HLTEFlowPtFilter/eflow

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
  set InputArray HLTEFlowPtFilter/eflow

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
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt <= 250) * (0.895695) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 250 && pt <= 300) * (0.890044) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 300 && pt <= 400) * (0.840805) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 400 && pt <= 500) * (0.896875) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 500 && pt <= 650) * (0.900665) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 650 && pt <= 800) * (0.900086) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 800 && pt <= 1000) * (0.917291) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1000 && pt <= 1500) * (0.915995) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 1500 && pt <= 2000) * (0.912079) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 2000 && pt <= 3000) * (0.900176) +
  (abs(eta) > 0 && abs(eta) <= 1.5) * (pt > 3000) * (0.886591) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt <= 250) * (0.95339) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 250 && pt <= 300) * (0.933019) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 300 && pt <= 400) * (0.868418) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 400 && pt <= 500) * (0.914701) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 500 && pt <= 650) * (0.910305) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 650 && pt <= 800) * (0.90359) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 800 && pt <= 1000) * (0.915509) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1000 && pt <= 1500) * (0.911584) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 1500 && pt <= 2000) * (0.907738) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 2000 && pt <= 3000) * (0.896902) +
  (abs(eta) > 1.5 && abs(eta) <= 2.5) * (pt > 3000) * (0.884749)
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

  add Branch HLTEFlowPtFilter/eflow ParticleFlowCandidate ParticleFlowCandidate

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
