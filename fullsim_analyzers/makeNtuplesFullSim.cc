// FullSim ntuplizer: writes EXACTLY the same ntuple schema as the Delphes
// paired ntuplizer (delphes_analyzers/makeNtuplesPaired.C), but from CMSSW
// AODSIM produced by the fullsim backend (backends/fullsim.sh), so that a
// downstream training/analysis script works on either backend's output
// unchanged. One row per selected OFFLINE jet, with its matched HLT jet's
// content under the parallel `hlt_`-prefixed branches.
//
// The gen-level jet labelling is NOT reimplemented here: this file fills the
// stand-in classes of StandaloneTypes.h from the CMSSW objects and then calls
// the very same FatJetMatching used by the Delphes ntuplizers, so the two
// backends cannot drift apart in how a jet is labelled. See
// fullsim_analyzers/StandaloneTypes.h for how that works.
//
// What the two sides are, concretely:
//   offline : `ak8PFJetsCHS` (AODSIM) + `offlinePrimaryVertices`
//   HLT     : `hltAK8PFJets` + `hltVerticesPFSelector` - the HLT reconstruction
//             itself, NOT the compressed scouting format (which has no impact
//             parameters at all in 2018); see fullsim_configs/README.md
// Constituents are the jets' own reco::PFCandidate daughters on both sides, so
// each charged one carries a reco::TrackRef and hence real impact parameters.
//
// CONVENTIONS - deliberately the Delphes/JetClass ones, not CMS's, so that the
// two backends' ntuples are interchangeable (see delphes_cards/KNOWN_ISSUES.md,
// "Impact parameters: units and sign"):
//   *_d0val  = -dxy * 10   (cm -> mm, and CMS's dxy sign is opposite to Delphes' D0)
//   *_dzval  =  dz  * 10   (cm -> mm), w.r.t. that side's OWN primary vertex
//   *_d0err/_dzerr = the errors * 10 (no sign flip)
// So these columns mean the same thing as in our Delphes ntuples and in central
// JetClass(-II). To get CMS's own convention back: dxy_cm = -d0val/10.
//
// OFFLINE JET SELECTION: pT > 200 GeV, |eta| < 2.4, chosen to match the CMS
// offline+scouting reference dataset this whole pipeline is reproducing
// (/eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/, see
// hlteff/README.md "Data source"), whose own selection was measured to be a
// hard edge at exactly those values: min fj_pt = 200.00 and max |fj_eta| =
// 2.3999 over 1.2M jet pairs, with nothing below/beyond. It also matches the
// Delphes backend, whose AK8 cards impose the same 200 GeV via their
// FastJetFinder JetPTMin (so makeNtuplesPaired.C's literal 120 never binds -
// copying that 120 here was a mistake, fixed 2026-10-05; it had let 23% extra,
// 94%-QCD-labeled jets into the FullSim sample and inflated its QCD fraction
// from 58% to 66%).
//
// NO pT or eta requirement is applied to the matched HLT jet, deliberately -
// see makeNtuplesPaired.C's docstring for why a vanished or merely-softer HLT
// jet must stay distinguishable. The reference dataset does cut its scouting
// jet at 170 GeV (also a hard edge, verified: zero jets below, 0.3% between 170
// and 200), so a strict comparison against it should additionally require
// hlt_jet_pt > 170 downstream - that removes 0.35% of FullSim and 3.4% of
// Delphes jets. The reference applies no eta cut to the scouting jet (its
// |scoutfj_eta| reaches 2.84, i.e. the offline 2.4 plus the matching cone).
//
// jet_sdmass and jet_tau1..4 are not stored in AODSIM for AK8 (and do not exist
// at all for HLT jets), so they are computed here from the jet's constituents
// with fastjet, using the SAME parameters as the Delphes cards' FastJetFinder
// (anti-kT R, SoftDrop beta=0/zcut=0.1/R0=R, N-subjettiness with
// NormalizedMeasure(beta=1, R) and OnePass_KT_Axes) - see
// delphes_cards/delphes_card_CMS_JetClassII_onlyFatJet.tcl and Delphes'
// modules/FastJetFinder.cc for where each of those comes from.
//
// Built as a standalone executable (fullsim_analyzers/build.sh), NOT as a ROOT
// macro: ACLiC works, but the moment FWLite opens the file, cling auto-parses
// the CMSSW headers and ROOT 6.14 segfaults reverting a transaction that
// contains a lambda. A compiled binary takes the interpreter out of the picture
// entirely (and starts faster). Usage:
//   makeNtuplesFullSim in=reco.root out=ntuple.root [key=value ...]
// see main() at the bottom for the keys.

#define JETCLASS_STANDALONE_TYPES

#include <iostream>
#include <vector>
#include <string>
#include <algorithm>
#include <memory>
#include <cmath>
#include <map>
#include <stdexcept>

#include "TFile.h"
#include "TTree.h"
#include "TObjArray.h"
#include "TSystem.h"

#include "FatJetMatching.h"
#include "EventData.h"

#include "FWCore/FWLite/interface/FWLiteEnabler.h"
#include "DataFormats/FWLite/interface/Event.h"
#include "DataFormats/FWLite/interface/Handle.h"
#include "DataFormats/JetReco/interface/PFJet.h"
#include "DataFormats/JetReco/interface/GenJet.h"
#include "DataFormats/VertexReco/interface/Vertex.h"
#include "DataFormats/HepMCCandidate/interface/GenParticle.h"
#include "DataFormats/ParticleFlowCandidate/interface/PFCandidate.h"
#include "DataFormats/TrackReco/interface/Track.h"

#include "fastjet/ClusterSequence.hh"
#include "fastjet/PseudoJet.hh"
#include "fastjet/contrib/Nsubjettiness.hh"
#include "fastjet/contrib/SoftDrop.hh"

namespace {

// Substructure of one jet, recomputed from its constituents. Delphes' own
// FastJetFinder applies SoftDrop/N-subjettiness to the anti-kT jet it just
// clustered, so the constituents are reclustered here with the same anti-kT R
// to get a jet that carries a cluster sequence, and the same parameters are
// then applied to it. Reclustering a jet's own constituents reproduces that
// jet (up to the rare case of it splitting, where the hardest piece is taken).
struct Substructure {
    float sdmass = -999;
    float tau[4] = {-999, -999, -999, -999};
};

Substructure computeSubstructure(const std::vector<fastjet::PseudoJet> &parts, double jetR) {
    Substructure out;
    if (parts.empty()) return out;
    fastjet::JetDefinition jetDef(fastjet::antikt_algorithm, jetR);
    fastjet::ClusterSequence cs(parts, jetDef);
    std::vector<fastjet::PseudoJet> jets = fastjet::sorted_by_pt(cs.inclusive_jets(0.0));
    if (jets.empty()) return out;
    const fastjet::PseudoJet &jet = jets[0];

    fastjet::contrib::SoftDrop softDrop(0.0, 0.1, jetR);   // beta, symmetry cut, R0
    try {
        fastjet::PseudoJet sd = softDrop(jet);
        if (sd != 0) out.sdmass = sd.m();
    } catch (const fastjet::Error &e) {
        std::cerr << "** WARNING: SoftDrop failed on a jet (" << e.message() << ") - sdmass left at -999" << std::endl;
    }

    for (int n = 1; n <= 4; ++n) {
        try {
            fastjet::contrib::Nsubjettiness nSub(n, fastjet::contrib::OnePass_KT_Axes(),
                                                 fastjet::contrib::NormalizedMeasure(1.0, jetR));
            out.tau[n - 1] = nSub(jet);
        } catch (const fastjet::Error &e) {
            std::cerr << "** WARNING: N-subjettiness tau" << n << " failed (" << e.message() << ")" << std::endl;
        }
    }
    return out;
}

// One jet side (offline or HLT): the constituents as both the stand-in
// ParticleFlowCandidates the shared filling code wants and the PseudoJets the
// substructure needs, already pT-ordered.
struct JetContent {
    std::vector<ParticleInfo> particles;
    Substructure substructure;
};

JetContent buildJetContent(const reco::PFJet &jet, const reco::Vertex::Point &pv, double jetR) {
    JetContent out;
    std::vector<fastjet::PseudoJet> fjParts;
    for (const auto &candPtr : jet.getPFConstituents()) {
        if (candPtr.isNull()) continue;
        const reco::PFCandidate &cand = *candPtr;
        // same constituent sanity cuts as the Delphes ntuplizers
        if (cand.pt() <= 0 || std::abs(cand.eta()) > 5 || std::abs(cand.pz()) > 10000) continue;

        // a stack-local stand-in is enough: ParticleInfo copies the values out of
        // it, it holds no pointer back into it
        ParticleFlowCandidate pfc;
        pfc.PT = cand.pt();
        pfc.Eta = cand.eta();
        pfc.Phi = cand.phi();
        pfc.Mass = cand.mass();
        pfc.E = cand.energy();
        pfc.Charge = cand.charge();
        pfc.PID = cand.pdgId();
        const reco::TrackRef trk = cand.trackRef();
        if (trk.isNonnull()) {
            // cm -> mm, and CMS's dxy has the opposite sign to Delphes' D0 (see
            // this file's header and delphes_cards/KNOWN_ISSUES.md)
            pfc.D0 = -10. * trk->dxy(pv);
            pfc.DZ = 10. * trk->dz(pv);
            pfc.ErrorD0 = 10. * trk->dxyError();
            pfc.ErrorDZ = 10. * trk->dzError();
        }
        out.particles.emplace_back(&pfc);
        fjParts.emplace_back(cand.px(), cand.py(), cand.pz(), cand.energy());
    }
    std::sort(out.particles.begin(), out.particles.end(),
              [](const ParticleInfo &a, const ParticleInfo &b) { return a.pt > b.pt; });
    out.substructure = computeSubstructure(fjParts, jetR);
    return out;
}

// Greedy nearest-deltaR one-to-one jet matching - same algorithm (and the same
// reasoning) as makeNtuplesPaired.C's own matchJets(), see its comment there.
std::vector<int> matchJets(const std::vector<const reco::PFJet *> &offlineJets,
                           const std::vector<const reco::PFJet *> &hltJets, double drMax) {
    std::vector<int> match(offlineJets.size(), -1);
    if (offlineJets.empty() || hltJets.empty()) return match;
    std::vector<std::tuple<double, int, int>> pairs;
    for (size_t i = 0; i < offlineJets.size(); ++i) {
        for (size_t j = 0; j < hltJets.size(); ++j) {
            double dr = deltaR(offlineJets[i]->eta(), offlineJets[i]->phi(),
                               hltJets[j]->eta(), hltJets[j]->phi());
            if (dr < drMax) pairs.emplace_back(dr, (int)i, (int)j);
        }
    }
    std::sort(pairs.begin(), pairs.end());
    std::vector<bool> usedOff(offlineJets.size(), false), usedHlt(hltJets.size(), false);
    for (const auto &t : pairs) {
        int i = std::get<1>(t), j = std::get<2>(t);
        if (usedOff[i] || usedHlt[j]) continue;
        usedOff[i] = true;
        usedHlt[j] = true;
        match[i] = j;
    }
    return match;
}

}   // namespace

void makeNtuplesFullSim(TString inputFile, TString outputFile,
                        TString jetCollection = "ak8PFJetsCHS",
                        TString hltJetCollection = "hltAK8PFJets",
                        bool assignQCDLabel = false, bool debug = false, bool useV1Labels = false,
                        bool doHlt = true,
                        bool keepGenParticles = false, bool keepAuxGenParticles = false,
                        bool keepGenJet = false, double hltMatchDR = -1,
                        TString vertexCollection = "offlinePrimaryVertices",
                        TString hltVertexCollection = "hltVerticesPFSelector",
                        TString genParticleCollection = "genParticles",
                        TString genJetCollection = "ak8GenJets",
                        double jetPtMin = 200., double jetEtaMax = 2.4) {

    TFile *fout = new TFile(outputFile, "RECREATE");
    TTree *tree = new TTree("tree", "tree");

    // Branch list: identical set AND order to makeNtuplesPaired.C's, so the two
    // backends' ntuples are drop-in replacements for each other
    std::vector<std::pair<std::string, std::string>> branchList = {
        {"part_px", "vector<float>"},
        {"part_py", "vector<float>"},
        {"part_pz", "vector<float>"},
        {"part_energy", "vector<float>"},
        {"part_deta", "vector<float>"},
        {"part_dphi", "vector<float>"},
        {"part_d0val", "vector<float>"},
        {"part_d0err", "vector<float>"},
        {"part_dzval", "vector<float>"},
        {"part_dzerr", "vector<float>"},
        {"part_charge", "vector<int>"},
        {"part_isElectron", "vector<bool>"},
        {"part_isMuon", "vector<bool>"},
        {"part_isPhoton", "vector<bool>"},
        {"part_isChargedHadron", "vector<bool>"},
        {"part_isNeutralHadron", "vector<bool>"},
        {"jet_pt", "float"},
        {"jet_eta", "float"},
        {"jet_phi", "float"},
        {"jet_energy", "float"},
        {"jet_sdmass", "float"},
        {"jet_nparticles", "int"},
        {"jet_tau1", "float"},
        {"jet_tau2", "float"},
        {"jet_tau3", "float"},
        {"jet_tau4", "float"},
        {"jet_label", "int"},
        {"hlt_matched", "bool"},
        {"hlt_jet_pt", "float"},
        {"hlt_jet_eta", "float"},
        {"hlt_jet_phi", "float"},
        {"hlt_jet_energy", "float"},
        {"hlt_jet_sdmass", "float"},
        {"hlt_jet_nparticles", "int"},
        {"hlt_jet_tau1", "float"},
        {"hlt_jet_tau2", "float"},
        {"hlt_jet_tau3", "float"},
        {"hlt_jet_tau4", "float"},
        {"hlt_jet_dr_offline", "float"},
        {"hlt_part_px", "vector<float>"},
        {"hlt_part_py", "vector<float>"},
        {"hlt_part_pz", "vector<float>"},
        {"hlt_part_energy", "vector<float>"},
        {"hlt_part_deta", "vector<float>"},
        {"hlt_part_dphi", "vector<float>"},
        {"hlt_part_d0val", "vector<float>"},
        {"hlt_part_d0err", "vector<float>"},
        {"hlt_part_dzval", "vector<float>"},
        {"hlt_part_dzerr", "vector<float>"},
        {"hlt_part_charge", "vector<int>"},
        {"hlt_part_isElectron", "vector<bool>"},
        {"hlt_part_isMuon", "vector<bool>"},
        {"hlt_part_isPhoton", "vector<bool>"},
        {"hlt_part_isChargedHadron", "vector<bool>"},
        {"hlt_part_isNeutralHadron", "vector<bool>"},
    };
    if (keepGenParticles) {
        std::vector<std::pair<std::string, std::string>> b = {
            {"genpart_px", "vector<float>"},      {"genpart_py", "vector<float>"},
            {"genpart_pz", "vector<float>"},      {"genpart_energy", "vector<float>"},
            {"genpart_jet_deta", "vector<float>"},{"genpart_jet_dphi", "vector<float>"},
            {"genpart_x", "vector<float>"},       {"genpart_y", "vector<float>"},
            {"genpart_z", "vector<float>"},       {"genpart_t", "vector<float>"},
            {"genpart_pid", "vector<int>"},
        };
        branchList.insert(branchList.end(), b.begin(), b.end());
    }
    if (keepGenJet) {
        std::vector<std::pair<std::string, std::string>> b = {
            {"genjet_pt", "float"},     {"genjet_eta", "float"},
            {"genjet_phi", "float"},    {"genjet_energy", "float"},
            {"genjet_sdmass", "float"}, {"genjet_nparticles", "int"},
        };
        branchList.insert(branchList.end(), b.begin(), b.end());
    }
    if (keepAuxGenParticles) {
        std::vector<std::pair<std::string, std::string>> b = {
            {"aux_genpart_pt", "vector<float>"},   {"aux_genpart_eta", "vector<float>"},
            {"aux_genpart_phi", "vector<float>"},  {"aux_genpart_mass", "vector<float>"},
            {"aux_genpart_pid", "vector<int>"},    {"aux_genpart_isResX", "vector<bool>"},
            {"aux_genpart_isResY", "vector<bool>"},{"aux_genpart_isResDecayProd", "vector<bool>"},
            {"aux_genpart_isTauDecayProd", "vector<bool>"}, {"aux_genpart_isQcdParton", "vector<bool>"},
        };
        branchList.insert(branchList.end(), b.begin(), b.end());
    }
    EventData data(branchList);
    data.setOutputBranch(tree);

    double jetR = jetCollection.Contains("AK15") || jetCollection.Contains("ak15") ? 1.5 : 0.8;
    if (hltMatchDR < 0) hltMatchDR = jetR;

    std::cerr << "** Input file:        " << inputFile << std::endl;
    std::cerr << "** Offline jets:      " << jetCollection << " (pT > " << jetPtMin
              << ", |eta| < " << jetEtaMax << ")" << std::endl;
    std::cerr << "** HLT jets:          " << (doHlt ? hltJetCollection : TString("(disabled)")) << std::endl;
    std::cerr << "** jetR = " << jetR << ", hltMatchDR = " << hltMatchDR << std::endl;

    FatJetMatching fjmatch(jetR, assignQCDLabel, debug, useV1Labels);

    TFile *fin = TFile::Open(inputFile);
    if (fin == nullptr || fin->IsZombie()) {
        std::cerr << "** ERROR: cannot open input file " << inputFile << std::endl;
        return;
    }
    fwlite::Event ev(fin);

    fwlite::Handle<std::vector<reco::PFJet>> hOfflineJets, hHltJets;
    fwlite::Handle<std::vector<reco::Vertex>> hOfflineVtx, hHltVtx;
    fwlite::Handle<std::vector<reco::GenParticle>> hGenParticles;
    fwlite::Handle<std::vector<reco::GenJet>> hGenJets;

    int num_processed = 0, num_events = 0, num_no_offline_vtx = 0, num_no_hlt_vtx = 0;
    long num_noncontiguous_daughters = 0, num_gen_particles = 0;

    for (ev.toBegin(); !ev.atEnd(); ++ev) {
        ++num_events;
        if (num_events % 100 == 1) {
            std::cerr << "processing event " << num_events << std::endl;
        }

        hOfflineJets.getByLabel(ev, jetCollection.Data());
        hOfflineVtx.getByLabel(ev, vertexCollection.Data());
        hGenParticles.getByLabel(ev, genParticleCollection.Data());
        const std::vector<reco::PFJet> &offlineJets = *hOfflineJets;
        const std::vector<reco::Vertex> &offlineVtx = *hOfflineVtx;
        const std::vector<reco::GenParticle> &genParticles = *hGenParticles;

        if (offlineVtx.empty()) {
            // No offline primary vertex: every impact parameter of the event
            // would be measured from an arbitrary point, so the event is
            // dropped rather than written with meaningless IPs (counted and
            // reported at the end).
            ++num_no_offline_vtx;
            continue;
        }
        const reco::Vertex::Point offlinePv = offlineVtx[0].position();

        // ---- gen particles -> the stand-in array FatJetMatching walks ----
        // Delphes' convention, reproduced here: M1/M2 and D1/D2 are the FIRST
        // and LAST index of the mothers/daughters, and getDaughters() walks the
        // whole range in between (DelphesHepMC2Reader fills them from the HepMC
        // vertex' in/out particle ranges). reco::GenParticle keeps the HepMC
        // order, in which a vertex' outgoing particles are consecutive, so the
        // range is the daughter set - verified by the contiguity counter below,
        // which is reported if it ever fires.
        TObjArray genArray(genParticles.size());
        std::vector<std::unique_ptr<GenParticle>> genOwner;
        genOwner.reserve(genParticles.size());
        for (const auto &gp : genParticles) {
            auto sgp = std::make_unique<GenParticle>();
            sgp->PID = gp.pdgId();
            sgp->Status = gp.status();
            sgp->Charge = gp.charge();
            sgp->Mass = gp.mass();
            sgp->PT = gp.pt();
            sgp->Eta = gp.pt() > 0 ? gp.eta() : (gp.pz() > 0 ? 999. : -999.);
            sgp->Phi = gp.phi();
            sgp->E = gp.energy();
            sgp->X = 10. * gp.vx();   // cm -> mm (Delphes units)
            sgp->Y = 10. * gp.vy();
            sgp->Z = 10. * gp.vz();
            sgp->T = 0;               // no production time in reco::GenParticle
            int m1 = -1, m2 = -1, d1 = -1, d2 = -1;
            for (size_t i = 0; i < gp.numberOfMothers(); ++i) {
                int k = (int)gp.motherRef(i).key();
                m1 = (m1 < 0 || k < m1) ? k : m1;
                m2 = (m2 < 0 || k > m2) ? k : m2;
            }
            for (size_t i = 0; i < gp.numberOfDaughters(); ++i) {
                int k = (int)gp.daughterRef(i).key();
                d1 = (d1 < 0 || k < d1) ? k : d1;
                d2 = (d2 < 0 || k > d2) ? k : d2;
            }
            if (d1 >= 0 && (size_t)(d2 - d1 + 1) != gp.numberOfDaughters()) {
                ++num_noncontiguous_daughters;
            }
            sgp->M1 = m1;
            sgp->M2 = m2;
            sgp->D1 = d1;
            sgp->D2 = d2;
            genArray.AddLast(sgp.get());
            genOwner.push_back(std::move(sgp));
        }
        num_gen_particles += genParticles.size();

        // ---- HLT side of the event ----
        const std::vector<reco::PFJet> *hltJets = nullptr;
        reco::Vertex::Point hltPv;
        bool hltUsable = false;
        if (doHlt) {
            hHltJets.getByLabel(ev, hltJetCollection.Data());
            hHltVtx.getByLabel(ev, hltVertexCollection.Data());
            hltJets = hHltJets.ptr();
            if (hHltVtx.isValid() && !hHltVtx->empty()) {
                // the HLT run's OWN primary vertex: HLT dz must be measured
                // w.r.t. what HLT itself reconstructed, not the offline vertex
                hltPv = (*hHltVtx)[0].position();
                hltUsable = (hltJets != nullptr);
            } else {
                ++num_no_hlt_vtx;
            }
        }

        // ---- phase 1: select and label offline jets ----
        struct SelectedJet {
            const reco::PFJet *jet;
            int labelIndex;
        };
        std::vector<SelectedJet> selected;
        for (const auto &jet : offlineJets) {
            if (jet.pt() < jetPtMin || std::abs(jet.eta()) > jetEtaMax) continue;
            Jet sjet;
            sjet.PT = jet.pt();
            sjet.Eta = jet.eta();
            sjet.Phi = jet.phi();
            sjet.Mass = jet.mass();
            fjmatch.getLabel(&sjet, &genArray);
            if (fjmatch.getResult().label == "Invalid") continue;
            if (useV1Labels && fjmatch.shouldRejectV1()) continue;
            selected.push_back({&jet, fjmatch.findLabelIndex()});
        }
        if (selected.empty()) continue;

        // ---- phase 2: offline <-> HLT jet matching, once per event ----
        std::vector<const reco::PFJet *> offlinePtrs, hltPtrs;
        for (const auto &sj : selected) offlinePtrs.push_back(sj.jet);
        if (hltUsable) {
            for (const auto &hj : *hltJets) hltPtrs.push_back(&hj);
        }
        std::vector<int> hltMatchIdx = matchJets(offlinePtrs, hltPtrs, hltMatchDR);

        // ---- phase 3: one row per selected offline jet ----
        std::vector<int> genjet_used_inds;
        for (size_t si = 0; si < selected.size(); ++si) {
            const reco::PFJet &jet = *selected[si].jet;
            data.reset();
            data.intVars.at("jet_label") = selected[si].labelIndex;

            if (keepAuxGenParticles) {
                Jet sjet;
                sjet.PT = jet.pt();
                sjet.Eta = jet.eta();
                sjet.Phi = jet.phi();
                sjet.Mass = jet.mass();
                fjmatch.getLabel(&sjet, &genArray);   // recompute result_ for this jet
                auto fillAux = [](EventData &data, const GenParticle *part, bool isResX, bool isResY,
                                  bool isResDecayProd, bool isTauDecayProd, bool isQcdParton) {
                    data.vfloatVars.at("aux_genpart_pt")->push_back(part->PT);
                    data.vfloatVars.at("aux_genpart_eta")->push_back(part->Eta);
                    data.vfloatVars.at("aux_genpart_phi")->push_back(part->Phi);
                    data.vfloatVars.at("aux_genpart_mass")->push_back(part->Mass);
                    data.vintVars.at("aux_genpart_pid")->push_back(part->PID);
                    data.vboolVars.at("aux_genpart_isResX")->push_back(isResX);
                    data.vboolVars.at("aux_genpart_isResY")->push_back(isResY);
                    data.vboolVars.at("aux_genpart_isResDecayProd")->push_back(isResDecayProd);
                    data.vboolVars.at("aux_genpart_isTauDecayProd")->push_back(isTauDecayProd);
                    data.vboolVars.at("aux_genpart_isQcdParton")->push_back(isQcdParton);
                };
                int nRes = 0;
                for (const auto *p : fjmatch.getResult().resParticles) { fillAux(data, p, nRes == 0, nRes > 0, false, false, false); ++nRes; }
                for (const auto *p : fjmatch.getResult().decayParticles) fillAux(data, p, false, false, true, false, false);
                for (const auto *p : fjmatch.getResult().tauDecayParticles) fillAux(data, p, false, false, false, true, false);
                for (const auto *p : fjmatch.getResult().qcdPartons) fillAux(data, p, false, false, false, false, true);
            }

            JetContent off = buildJetContent(jet, offlinePv, jetR);

            data.floatVars.at("jet_pt") = jet.pt();
            data.floatVars.at("jet_eta") = jet.eta();
            data.floatVars.at("jet_phi") = jet.phi();
            data.floatVars.at("jet_energy") = jet.energy();
            data.floatVars.at("jet_sdmass") = off.substructure.sdmass;
            data.floatVars.at("jet_tau1") = off.substructure.tau[0];
            data.floatVars.at("jet_tau2") = off.substructure.tau[1];
            data.floatVars.at("jet_tau3") = off.substructure.tau[2];
            data.floatVars.at("jet_tau4") = off.substructure.tau[3];
            data.intVars["jet_nparticles"] = off.particles.size();
            for (const auto &p : off.particles) {
                data.vfloatVars.at("part_px")->push_back(p.px);
                data.vfloatVars.at("part_py")->push_back(p.py);
                data.vfloatVars.at("part_pz")->push_back(p.pz);
                data.vfloatVars.at("part_energy")->push_back(p.energy);
                data.vfloatVars.at("part_deta")->push_back((jet.eta() > 0 ? 1 : -1) * (p.eta - jet.eta()));
                data.vfloatVars.at("part_dphi")->push_back(deltaPhi(p.phi, jet.phi()));
                data.vfloatVars.at("part_d0val")->push_back(p.d0);
                data.vfloatVars.at("part_d0err")->push_back(p.d0err);
                data.vfloatVars.at("part_dzval")->push_back(p.dz);
                data.vfloatVars.at("part_dzerr")->push_back(p.dzerr);
                data.vintVars.at("part_charge")->push_back(p.charge);
                data.vboolVars.at("part_isElectron")->push_back(p.pid == 11 || p.pid == -11);
                data.vboolVars.at("part_isMuon")->push_back(p.pid == 13 || p.pid == -13);
                data.vboolVars.at("part_isPhoton")->push_back(p.pid == 22);
                data.vboolVars.at("part_isChargedHadron")->push_back(p.charge != 0 && !(p.pid == 11 || p.pid == -11 || p.pid == 13 || p.pid == -13));
                data.vboolVars.at("part_isNeutralHadron")->push_back(p.charge == 0 && !(p.pid == 22));
            }

            // ---- the matched HLT jet (or the "no match" sentinel) ----
            int hi = (si < hltMatchIdx.size()) ? hltMatchIdx[si] : -1;
            if (hi < 0) {
                data.boolVars.at("hlt_matched") = false;
                for (const char *n : {"hlt_jet_pt", "hlt_jet_eta", "hlt_jet_phi", "hlt_jet_energy",
                                      "hlt_jet_sdmass", "hlt_jet_tau1", "hlt_jet_tau2", "hlt_jet_tau3",
                                      "hlt_jet_tau4", "hlt_jet_dr_offline"}) {
                    data.floatVars.at(n) = -999;
                }
                data.intVars["hlt_jet_nparticles"] = 0;
            } else {
                const reco::PFJet &hltJet = *hltPtrs[hi];
                JetContent hlt = buildJetContent(hltJet, hltPv, jetR);
                data.boolVars.at("hlt_matched") = true;
                data.floatVars.at("hlt_jet_pt") = hltJet.pt();
                data.floatVars.at("hlt_jet_eta") = hltJet.eta();
                data.floatVars.at("hlt_jet_phi") = hltJet.phi();
                data.floatVars.at("hlt_jet_energy") = hltJet.energy();
                data.floatVars.at("hlt_jet_sdmass") = hlt.substructure.sdmass;
                data.floatVars.at("hlt_jet_tau1") = hlt.substructure.tau[0];
                data.floatVars.at("hlt_jet_tau2") = hlt.substructure.tau[1];
                data.floatVars.at("hlt_jet_tau3") = hlt.substructure.tau[2];
                data.floatVars.at("hlt_jet_tau4") = hlt.substructure.tau[3];
                data.floatVars.at("hlt_jet_dr_offline") =
                    deltaR(hltJet.eta(), hltJet.phi(), jet.eta(), jet.phi());
                data.intVars["hlt_jet_nparticles"] = hlt.particles.size();
                for (const auto &p : hlt.particles) {
                    data.vfloatVars.at("hlt_part_px")->push_back(p.px);
                    data.vfloatVars.at("hlt_part_py")->push_back(p.py);
                    data.vfloatVars.at("hlt_part_pz")->push_back(p.pz);
                    data.vfloatVars.at("hlt_part_energy")->push_back(p.energy);
                    data.vfloatVars.at("hlt_part_deta")->push_back((hltJet.eta() > 0 ? 1 : -1) * (p.eta - hltJet.eta()));
                    data.vfloatVars.at("hlt_part_dphi")->push_back(deltaPhi(p.phi, hltJet.phi()));
                    data.vfloatVars.at("hlt_part_d0val")->push_back(p.d0);
                    data.vfloatVars.at("hlt_part_d0err")->push_back(p.d0err);
                    data.vfloatVars.at("hlt_part_dzval")->push_back(p.dz);
                    data.vfloatVars.at("hlt_part_dzerr")->push_back(p.dzerr);
                    data.vintVars.at("hlt_part_charge")->push_back(p.charge);
                    data.vboolVars.at("hlt_part_isElectron")->push_back(p.pid == 11 || p.pid == -11);
                    data.vboolVars.at("hlt_part_isMuon")->push_back(p.pid == 13 || p.pid == -13);
                    data.vboolVars.at("hlt_part_isPhoton")->push_back(p.pid == 22);
                    data.vboolVars.at("hlt_part_isChargedHadron")->push_back(p.charge != 0 && !(p.pid == 11 || p.pid == -11 || p.pid == 13 || p.pid == -13));
                    data.vboolVars.at("hlt_part_isNeutralHadron")->push_back(p.charge == 0 && !(p.pid == 22));
                }
            }

            // ---- gen jet / gen particles (offline side only, as in makeNtuplesPaired.C) ----
            if (keepGenJet || keepGenParticles) {
                hGenJets.getByLabel(ev, genJetCollection.Data());
                if (hGenJets.isValid()) {
                    float min_dr = 999;
                    int min_dr_index = -1;
                    for (size_t j = 0; j < hGenJets->size(); ++j) {
                        const reco::GenJet &genjet = (*hGenJets)[j];
                        float dr = deltaR(genjet.eta(), genjet.phi(), jet.eta(), jet.phi());
                        bool used = std::find(genjet_used_inds.begin(), genjet_used_inds.end(), (int)j) != genjet_used_inds.end();
                        if (dr < min_dr && !used) { min_dr = dr; min_dr_index = (int)j; }
                    }
                    if (min_dr < jetR && min_dr_index >= 0) {
                        genjet_used_inds.push_back(min_dr_index);
                        const reco::GenJet &genjet = (*hGenJets)[min_dr_index];
                        std::vector<ParticleInfo> genparticles;
                        std::vector<fastjet::PseudoJet> fjParts;
                        for (const auto &dauPtr : genjet.getJetConstituents()) {
                            if (dauPtr.isNull()) continue;
                            const auto &dau = *dauPtr;
                            if (dau.pt() <= 0 || std::abs(dau.eta()) > 5 || std::abs(dau.pz()) > 10000) continue;
                            GenParticle sgp;
                            sgp.PID = dau.pdgId();
                            sgp.Charge = dau.charge();
                            sgp.Mass = dau.mass();
                            sgp.PT = dau.pt();
                            sgp.Eta = dau.eta();
                            sgp.Phi = dau.phi();
                            sgp.X = 10. * dau.vx();
                            sgp.Y = 10. * dau.vy();
                            sgp.Z = 10. * dau.vz();
                            genparticles.emplace_back(&sgp);
                            fjParts.emplace_back(dau.px(), dau.py(), dau.pz(), dau.energy());
                        }
                        std::sort(genparticles.begin(), genparticles.end(),
                                  [](const ParticleInfo &a, const ParticleInfo &b) { return a.pt > b.pt; });
                        if (keepGenJet) {
                            data.floatVars.at("genjet_pt") = genjet.pt();
                            data.floatVars.at("genjet_eta") = genjet.eta();
                            data.floatVars.at("genjet_phi") = genjet.phi();
                            data.floatVars.at("genjet_energy") = genjet.energy();
                            data.floatVars.at("genjet_sdmass") = computeSubstructure(fjParts, jetR).sdmass;
                            data.intVars["genjet_nparticles"] = genparticles.size();
                        }
                        if (keepGenParticles) {
                            for (const auto &p : genparticles) {
                                data.vfloatVars.at("genpart_px")->push_back(p.px);
                                data.vfloatVars.at("genpart_py")->push_back(p.py);
                                data.vfloatVars.at("genpart_pz")->push_back(p.pz);
                                data.vfloatVars.at("genpart_energy")->push_back(p.energy);
                                data.vfloatVars.at("genpart_jet_deta")->push_back((jet.eta() > 0 ? 1 : -1) * (p.eta - jet.eta()));
                                data.vfloatVars.at("genpart_jet_dphi")->push_back(deltaPhi(p.phi, jet.phi()));
                                // z/t relative to the primary vertex, as in makeNtuplesPaired.C
                                // (offlinePv is in cm, the stored positions in mm)
                                float dzmm = p.z - 10. * offlinePv.z();
                                data.vfloatVars.at("genpart_z")->push_back(dzmm);
                                data.vfloatVars.at("genpart_t")->push_back(0.);
                                data.vfloatVars.at("genpart_x")->push_back(std::abs(dzmm) < 1e-10 ? 0. : p.x);
                                data.vfloatVars.at("genpart_y")->push_back(std::abs(dzmm) < 1e-10 ? 0. : p.y);
                                data.vintVars.at("genpart_pid")->push_back(p.pid);
                            }
                        }
                    }
                }
            }

            tree->Fill();
            ++num_processed;
        }
    }

    // back to the output file: opening the input file made IT the current
    // directory, and TTree::Write() writes to whatever that is
    fout->cd();
    tree->Write();
    std::cerr << TString::Format("** Written %d jets (offline-selected, HLT-matched where possible) from %d events to %s",
                                 num_processed, num_events, outputFile.Data()) << std::endl;
    if (num_no_offline_vtx) {
        std::cerr << "** WARNING: " << num_no_offline_vtx << " of " << num_events
                  << " events had NO offline primary vertex and were skipped" << std::endl;
    }
    if (num_no_hlt_vtx) {
        std::cerr << "** WARNING: " << num_no_hlt_vtx << " of " << num_events
                  << " events had no HLT primary vertex - their jets are written with hlt_matched=false"
                  << std::endl;
    }
    if (num_noncontiguous_daughters) {
        // Not fatal, but worth knowing: it means FatJetMatching's getDaughters()
        // (which walks the whole [D1, D2] range) saw particles that are not
        // actual daughters, exactly as it would on a Delphes file with the same
        // property. See the gen-particle block above.
        std::cerr << "** NOTE: " << num_noncontiguous_daughters << " of " << num_gen_particles
                  << " gen particles had a non-contiguous daughter index range" << std::endl;
    }
    delete fout;
    fin->Close();
}


// ---------------------------------------------------------------------------
// Command line: key=value pairs, so the caller (fullsim_configs/run_chain.sh)
// never has to care about argument ORDER. `in` and `out` are required.
// ---------------------------------------------------------------------------
namespace {

bool parseBool(const std::string &v, const std::string &key) {
    if (v == "true" || v == "1" || v == "True") return true;
    if (v == "false" || v == "0" || v == "False") return false;
    throw std::invalid_argument("expected true/false for '" + key + "', got '" + v + "'");
}

}   // namespace

int main(int argc, char **argv) {
    std::map<std::string, std::string> opt = {
        {"in", ""},
        {"out", ""},
        {"jets", "ak8PFJetsCHS"},
        {"hltjets", "hltAK8PFJets"},
        {"vertices", "offlinePrimaryVertices"},
        {"hltvertices", "hltVerticesPFSelector"},
        {"genparticles", "genParticles"},
        {"genjets", "ak8GenJets"},
        {"qcdlabel", "true"},
        {"debug", "false"},
        {"v1labels", "false"},
        {"dohlt", "true"},
        {"keepgenparticles", "false"},
        {"keepauxgenparticles", "false"},
        {"keepgenjet", "false"},
        {"hltmatchdr", "-1"},
        {"jetptmin", "200"},
        {"jetetamax", "2.4"},
    };
    for (int i = 1; i < argc; ++i) {
        std::string a(argv[i]);
        auto eq = a.find('=');
        if (eq == std::string::npos) {
            std::cerr << "** ERROR: argument '" << a << "' is not of the form key=value" << std::endl;
            return 2;
        }
        std::string key = a.substr(0, eq), val = a.substr(eq + 1);
        if (opt.find(key) == opt.end()) {
            std::cerr << "** ERROR: unknown argument '" << key << "'. Known: ";
            for (const auto &kv : opt) std::cerr << kv.first << " ";
            std::cerr << std::endl;
            return 2;
        }
        opt[key] = val;
    }
    if (opt["in"].empty() || opt["out"].empty()) {
        std::cerr << "** ERROR: both in=<AODSIM file> and out=<ntuple file> are required" << std::endl;
        return 2;
    }

    FWLiteEnabler::enable();

    try {
        makeNtuplesFullSim(opt["in"].c_str(), opt["out"].c_str(), opt["jets"].c_str(), opt["hltjets"].c_str(),
                           parseBool(opt["qcdlabel"], "qcdlabel"), parseBool(opt["debug"], "debug"),
                           parseBool(opt["v1labels"], "v1labels"), parseBool(opt["dohlt"], "dohlt"),
                           parseBool(opt["keepgenparticles"], "keepgenparticles"),
                           parseBool(opt["keepauxgenparticles"], "keepauxgenparticles"),
                           parseBool(opt["keepgenjet"], "keepgenjet"),
                           std::stod(opt["hltmatchdr"]), opt["vertices"].c_str(), opt["hltvertices"].c_str(),
                           opt["genparticles"].c_str(), opt["genjets"].c_str(),
                           std::stod(opt["jetptmin"]), std::stod(opt["jetetamax"]));
    } catch (const std::exception &e) {
        std::cerr << "** ERROR: " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
