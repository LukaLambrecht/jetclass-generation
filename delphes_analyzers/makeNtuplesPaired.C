#include <iostream>
#include <unordered_set>
#include <utility>
#include <tuple>
#include <algorithm>
#include "TClonesArray.h"
#include "classes/DelphesClasses.h"
#include "ExRootAnalysis/ExRootTreeReader.h"

#include "FatJetMatching.h"
#include "EventData.h"

// Paired offline/HLT ntuplizer: reads two Delphes files produced from the same
// events.hepmc by two different cards, and writes one ntuple with a row per selected
// offline jet, carrying its own branches - the same schema as makeNtuples.C - plus its
// matched HLT jet under a parallel hlt_* group.
//
// Pairing is what makes the question "what does HLT reconstruct for the jets I would
// select offline?" answerable at all. Each card's FatJetFinder clusters independently
// from its own degraded particle content, so two separate ntuples share no jet count,
// order or index. The CMS reference ntuples solve this by construction, every row
// already being one (offline, HLT) pair, and this reproduces that row structure.
//
// The one correspondence that comes for free is event level: entry N of each file is
// the same physical event, because both cards process the identical events.hepmc in
// the identical order and Delphes writes one entry per input event whatever its jet
// content, which hadd preserves. Jet-level correspondence within an event is what
// matchJets() adds.
//
// Selection is offline-only by design: a row exists if the offline jet passes the
// pT/eta pre-cut and, under v1, the is_signal check. The matched HLT jet is then
// written as is, with no requirement of its own, so a jet HLT reconstructed softer
// stays distinguishable from one HLT lost entirely (hlt_matched false). For that
// distinction to mean the physics rather than a threshold, the HLT card paired with
// this ntuplizer needs its FastJetFinder JetPTMin relaxed to near zero.
//
// keepGenParticles/keepAuxGenParticles/keepGenJet work as in makeNtuples.C, offline
// side only: generator truth is detector-independent, so there is nothing to
// duplicate.
void makeNtuplesPaired(TString offlineInputFile, TString hltInputFile, TString outputFile,
                        TString jetBranch = "JetPUPPIAK8", TString genjetBranch = "GenJetAK8",
                        bool assignQCDLabel = false, bool debug = false, bool useV1Labels = false,
                        bool keepGenParticles = false, bool keepAuxGenParticles = false, bool keepGenJet = false,
                        double hltMatchDR = -1) {

    TFile *fout = new TFile(outputFile, "RECREATE");
    TTree *tree = new TTree("tree", "tree");

    // Offline branches, in the same set and order as makeNtuples.C, so a paired
    // ntuple's offline columns read exactly like a plain one.
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
        // HLT side. hlt_matched says whether an HLT jet was found within
        // hltMatchDR; when false every other hlt_* scalar is -999, rather than 0,
        // which would be a plausible real value, and every hlt_part_* vector is
        // empty rather than merely short.
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
        {"hlt_jet_dr_offline", "float"},   // deltaR(hlt jet, offline jet) - the match quality itself
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
        std::vector<std::pair<std::string, std::string>> genPartBranches = {
            {"genpart_px", "vector<float>"},
            {"genpart_py", "vector<float>"},
            {"genpart_pz", "vector<float>"},
            {"genpart_energy", "vector<float>"},
            {"genpart_jet_deta", "vector<float>"},
            {"genpart_jet_dphi", "vector<float>"},
            {"genpart_x", "vector<float>"},
            {"genpart_y", "vector<float>"},
            {"genpart_z", "vector<float>"},
            {"genpart_t", "vector<float>"},
            {"genpart_pid", "vector<int>"},
        };
        branchList.insert(branchList.end(), genPartBranches.begin(), genPartBranches.end());
    }
    if (keepGenJet) {
        std::vector<std::pair<std::string, std::string>> genJetBranches = {
            {"genjet_pt", "float"},
            {"genjet_eta", "float"},
            {"genjet_phi", "float"},
            {"genjet_energy", "float"},
            {"genjet_sdmass", "float"},
            {"genjet_nparticles", "int"},
        };
        branchList.insert(branchList.end(), genJetBranches.begin(), genJetBranches.end());
    }
    if (keepAuxGenParticles) {
        std::vector<std::pair<std::string, std::string>> auxGenPartBranches = {
            {"aux_genpart_pt", "vector<float>"},
            {"aux_genpart_eta", "vector<float>"},
            {"aux_genpart_phi", "vector<float>"},
            {"aux_genpart_mass", "vector<float>"},
            {"aux_genpart_pid", "vector<int>"},
            {"aux_genpart_isResX", "vector<bool>"},
            {"aux_genpart_isResY", "vector<bool>"},
            {"aux_genpart_isResDecayProd", "vector<bool>"},
            {"aux_genpart_isTauDecayProd", "vector<bool>"},
            {"aux_genpart_isQcdParton", "vector<bool>"},
        };
        branchList.insert(branchList.end(), auxGenPartBranches.begin(), auxGenPartBranches.end());
    }
    EventData data(branchList);
    data.setOutputBranch(tree);

    // Two separate readers, one per file, rather than one merged chain: the event
    // loop has to read both in lockstep by entry index.
    TChain *offlineChain = new TChain("Delphes");
    offlineChain->Add(offlineInputFile);
    ExRootTreeReader *offlineReader = new ExRootTreeReader(offlineChain);
    Long64_t offlineEntries = offlineReader->GetEntries();

    TChain *hltChain = new TChain("Delphes");
    hltChain->Add(hltInputFile);
    ExRootTreeReader *hltReader = new ExRootTreeReader(hltChain);
    Long64_t hltEntries = hltReader->GetEntries();

    std::cerr << "** Offline input file: " << offlineInputFile << std::endl;
    std::cerr << "** HLT input file:     " << hltInputFile << std::endl;
    std::cerr << "** Jet branch:         " << jetBranch << std::endl;
    std::cerr << "** GenJet branch:      " << genjetBranch << std::endl;
    std::cerr << "** Offline entries:    " << offlineEntries << std::endl;
    std::cerr << "** HLT entries:        " << hltEntries << std::endl;
    if (offlineEntries != hltEntries) {
        // Not fatal, and should not happen, since both files come from the same
        // events.hepmc. But if one card's run did crash on a batch the other
        // completed, process only the entries both files have, loudly, rather than
        // silently pairing entry N with a different event.
        std::cerr << "** WARNING: offline/HLT entry count mismatch (" << offlineEntries << " vs "
                   << hltEntries << ") - only the first " << std::min(offlineEntries, hltEntries)
                   << " entries (common to both) will be processed. This should not normally happen -"
                   << " see this function's own docstring for why entry-by-entry correspondence is"
                   << " otherwise guaranteed." << std::endl;
    }
    Long64_t allEntries = std::min(offlineEntries, hltEntries);

    TClonesArray *offlineBranchVertex = offlineReader->UseBranch("Vertex");
    TClonesArray *offlineBranchParticle = offlineReader->UseBranch("Particle");
    TClonesArray *offlineBranchPFCand = offlineReader->UseBranch("ParticleFlowCandidate");
    TClonesArray *offlineBranchJet = offlineReader->UseBranch(jetBranch);
    TClonesArray *offlineBranchGenJet = offlineReader->UseBranch(genjetBranch);

    // The HLT run's own vertices: the two runs are seeded independently and place
    // the primary vertex at different z for the same event, so HLT dz must be taken
    // against this one.
    TClonesArray *hltBranchVertex = hltReader->UseBranch("Vertex");
    TClonesArray *hltBranchPFCand = hltReader->UseBranch("ParticleFlowCandidate");
    TClonesArray *hltBranchJet = hltReader->UseBranch(jetBranch);
    // hltBranchPFCand is read only implicitly, through each matched HLT jet's own
    // constituents, so registering the branch is all that is needed here.
    (void)hltBranchPFCand;

    double jetR = jetBranch.Contains("AK15") ? 1.5 : 0.8;
    if (hltMatchDR < 0) hltMatchDR = jetR;   // see module docstring for the default's reasoning
    std::cerr << "jetR = " << jetR << ", hltMatchDR = " << hltMatchDR << std::endl;

    FatJetMatching fjmatch(jetR, assignQCDLabel, debug, useV1Labels);

    // Greedy nearest-deltaR, one-to-one matching of the selected offline jets
    // against all HLT jets in the event, with no pre-cut on the HLT side. Returns,
    // per offline jet, the matched index into hltJets, or -1 if none is within
    // dr_max. A plain nested loop is fast enough for the few jets per event.
    auto matchJets = [](const std::vector<const Jet*>& offlineJets, const std::vector<const Jet*>& hltJets,
                         double dr_max) -> std::vector<int> {
        int nOff = offlineJets.size();
        int nHlt = hltJets.size();
        std::vector<int> match(nOff, -1);
        if (nOff == 0 || nHlt == 0) return match;

        std::vector<std::tuple<double, int, int>> pairs;
        for (int i = 0; i < nOff; ++i) {
            for (int j = 0; j < nHlt; ++j) {
                double dr = deltaR(offlineJets[i], hltJets[j]);
                if (dr < dr_max) pairs.push_back(std::make_tuple(dr, i, j));
            }
        }
        std::sort(pairs.begin(), pairs.end());
        std::vector<bool> usedOff(nOff, false), usedHlt(nHlt, false);
        for (const auto& t : pairs) {
            int i = std::get<1>(t);
            int j = std::get<2>(t);
            if (usedOff[i] || usedHlt[j]) continue;
            usedOff[i] = true;
            usedHlt[j] = true;
            match[i] = j;
        }
        return match;
    };

    // Fill the hlt_* branches for one offline jet's matched HLT jet, or leave them
    // at the "no match" sentinel when hltJet is null. Factored out because the
    // constituent handling is the same as the offline side's.
    auto fillHltJet = [&](EventData& data, const Jet* hltJet, double drToOffline) {
        if (!hltJet) {
            data.boolVars.at("hlt_matched") = false;
            data.floatVars.at("hlt_jet_pt") = -999;
            data.floatVars.at("hlt_jet_eta") = -999;
            data.floatVars.at("hlt_jet_phi") = -999;
            data.floatVars.at("hlt_jet_energy") = -999;
            data.floatVars.at("hlt_jet_sdmass") = -999;
            data.intVars["hlt_jet_nparticles"] = 0;
            data.floatVars.at("hlt_jet_tau1") = -999;
            data.floatVars.at("hlt_jet_tau2") = -999;
            data.floatVars.at("hlt_jet_tau3") = -999;
            data.floatVars.at("hlt_jet_tau4") = -999;
            data.floatVars.at("hlt_jet_dr_offline") = -999;
            return;
        }
        data.boolVars.at("hlt_matched") = true;
        data.floatVars.at("hlt_jet_pt") = hltJet->PT;
        data.floatVars.at("hlt_jet_eta") = hltJet->Eta;
        data.floatVars.at("hlt_jet_phi") = hltJet->Phi;
        data.floatVars.at("hlt_jet_energy") = hltJet->P4().Energy();
        data.floatVars.at("hlt_jet_sdmass") = hltJet->SoftDroppedP4[0].M();
        data.floatVars.at("hlt_jet_tau1") = hltJet->Tau[0];
        data.floatVars.at("hlt_jet_tau2") = hltJet->Tau[1];
        data.floatVars.at("hlt_jet_tau3") = hltJet->Tau[2];
        data.floatVars.at("hlt_jet_tau4") = hltJet->Tau[3];
        data.floatVars.at("hlt_jet_dr_offline") = drToOffline;

        std::vector<ParticleInfo> particles;
        for (Int_t j = 0; j < hltJet->Constituents.GetEntriesFast(); ++j) {
            const TObject *object = hltJet->Constituents.At(j);
            if (!object) continue;
            if (object->IsA() == GenParticle::Class()) {
                particles.emplace_back((GenParticle *)object);
            } else if (object->IsA() == ParticleFlowCandidate::Class()) {
                particles.emplace_back((ParticleFlowCandidate *)object);
            }
            const auto &p = particles.back();
            if (std::abs(p.pz) > 10000 || std::abs(p.eta) > 5 || p.pt <= 0) {
                particles.pop_back();
            }
        }
        std::sort(particles.begin(), particles.end(), [](const auto &a, const auto &b) { return a.pt > b.pt; });

        // dz against the HLT primary vertex. d0 is not vertex-subtracted on either
        // side: PileUpMerger puts the hard-scatter vertex at x = y = 0 and smears
        // only z and t, so D0 from the origin already is D0 from the primary vertex.
        // The Vertex branch's own X/Y are not a position at all and subtracting them
        // would corrupt d0.
        const Vertex *hltPv = (hltBranchVertex != nullptr && hltBranchVertex->GetEntriesFast() > 0)
                                  ? ((Vertex *)hltBranchVertex->At(0)) : nullptr;

        data.intVars["hlt_jet_nparticles"] = particles.size();
        for (const auto &p : particles) {
            data.vfloatVars.at("hlt_part_px")->push_back(p.px);
            data.vfloatVars.at("hlt_part_py")->push_back(p.py);
            data.vfloatVars.at("hlt_part_pz")->push_back(p.pz);
            data.vfloatVars.at("hlt_part_energy")->push_back(p.energy);
            data.vfloatVars.at("hlt_part_deta")->push_back((hltJet->Eta > 0 ? 1 : -1) * (p.eta - hltJet->Eta));
            data.vfloatVars.at("hlt_part_dphi")->push_back(deltaPhi(p.phi, hltJet->Phi));
            data.vfloatVars.at("hlt_part_d0val")->push_back(p.d0);
            data.vfloatVars.at("hlt_part_d0err")->push_back(p.d0err);
            data.vfloatVars.at("hlt_part_dzval")->push_back((hltPv && p.dz != 0) ? (p.dz - hltPv->Z) : p.dz);
            data.vfloatVars.at("hlt_part_dzerr")->push_back(p.dzerr);
            data.vintVars.at("hlt_part_charge")->push_back(p.charge);
            data.vboolVars.at("hlt_part_isElectron")->push_back(p.pid == 11 || p.pid == -11);
            data.vboolVars.at("hlt_part_isMuon")->push_back(p.pid == 13 || p.pid == -13);
            data.vboolVars.at("hlt_part_isPhoton")->push_back(p.pid == 22);
            data.vboolVars.at("hlt_part_isChargedHadron")->push_back(p.charge != 0 && !(p.pid == 11 || p.pid == -11 || p.pid == 13 || p.pid == -13));
            data.vboolVars.at("hlt_part_isNeutralHadron")->push_back(p.charge == 0 && !(p.pid == 22));
        }
    };

    int num_processed = 0;
    for (Long64_t entry = 0; entry < allEntries; ++entry) {
        if (entry % 1000 == 0) {
            std::cerr << "processing " << entry << " of " << allEntries << " events." << std::endl;
        }
        offlineReader->ReadEntry(entry);
        hltReader->ReadEntry(entry);

        // Phase 1: select offline jets as makeNtuples.C does, keeping each one's
        // matching result so it need not be recomputed.
        struct SelectedJet {
            const Jet* jet;
            std::string label;
            int labelIndex;
        };
        std::vector<SelectedJet> selected;
        std::vector<int> genjet_used_inds = {};

        for (Int_t i = 0; i < offlineBranchJet->GetEntriesFast(); ++i) {
            const Jet *jet = (Jet *)offlineBranchJet->At(i);
            if (jet->PT < 120 || std::abs(jet->Eta) > 2.5)
                continue;

            fjmatch.getLabel(jet, offlineBranchParticle);
            auto fjlabel = fjmatch.getResult().label;
            if (fjlabel == "Invalid")
                continue;
            if (useV1Labels && fjmatch.shouldRejectV1())
                continue;

            SelectedJet sj;
            sj.jet = jet;
            sj.label = fjlabel;
            sj.labelIndex = fjmatch.findLabelIndex();
            selected.push_back(sj);
        }
        if (selected.empty())
            continue;

        // Phase 2: jet-level matching for this event, in one pass over all selected
        // offline jets, so two of them cannot claim the same HLT jet in an
        // order-dependent way.
        std::vector<const Jet*> offlineJetPtrs, hltJetPtrs;
        for (const auto& sj : selected) offlineJetPtrs.push_back(sj.jet);
        for (Int_t j = 0; j < hltBranchJet->GetEntriesFast(); ++j) {
            hltJetPtrs.push_back((Jet *)hltBranchJet->At(j));
        }
        std::vector<int> hltMatchIdx = matchJets(offlineJetPtrs, hltJetPtrs, hltMatchDR);

        // Phase 3: write one row per selected offline jet, with the same offline
        // content as makeNtuples.C, plus its matched HLT jet or the sentinel.
        for (size_t si = 0; si < selected.size(); ++si) {
            const Jet* jet = selected[si].jet;
            data.reset();

            data.intVars.at("jet_label") = selected[si].labelIndex;

            if (keepAuxGenParticles) {
                fjmatch.getLabel(jet, offlineBranchParticle);   // recompute result_ for this jet (cheap)
                auto fillAuxVars = [](EventData& data, const auto& part, bool isResX, bool isResY, bool isResDecayProd, bool isTauDecayProd, bool isQcdParton) {
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
                for (const auto &p : fjmatch.getResult().resParticles) { fillAuxVars(data, p, nRes == 0, nRes > 0, false, false, false); ++nRes; }
                for (const auto &p : fjmatch.getResult().decayParticles) fillAuxVars(data, p, false, false, true, false, false);
                for (const auto &p : fjmatch.getResult().tauDecayParticles) fillAuxVars(data, p, false, false, false, true, false);
                for (const auto &p : fjmatch.getResult().qcdPartons) fillAuxVars(data, p, false, false, false, false, true);
            }

            data.floatVars.at("jet_pt") = jet->PT;
            data.floatVars.at("jet_eta") = jet->Eta;
            data.floatVars.at("jet_phi") = jet->Phi;
            data.floatVars.at("jet_energy") = jet->P4().Energy();
            data.floatVars.at("jet_sdmass") = jet->SoftDroppedP4[0].M();
            data.floatVars.at("jet_tau1") = jet->Tau[0];
            data.floatVars.at("jet_tau2") = jet->Tau[1];
            data.floatVars.at("jet_tau3") = jet->Tau[2];
            data.floatVars.at("jet_tau4") = jet->Tau[3];

            std::vector<ParticleInfo> particles;
            for (Int_t j = 0; j < jet->Constituents.GetEntriesFast(); ++j) {
                const TObject *object = jet->Constituents.At(j);
                if (!object) continue;
                if (object->IsA() == GenParticle::Class()) {
                    particles.emplace_back((GenParticle *)object);
                } else if (object->IsA() == ParticleFlowCandidate::Class()) {
                    particles.emplace_back((ParticleFlowCandidate *)object);
                }
                const auto &p = particles.back();
                if (std::abs(p.pz) > 10000 || std::abs(p.eta) > 5 || p.pt <= 0) {
                    particles.pop_back();
                }
            }
            std::sort(particles.begin(), particles.end(), [](const auto &a, const auto &b) { return a.pt > b.pt; });

            const Vertex *pv = (offlineBranchVertex != nullptr) ? ((Vertex *)offlineBranchVertex->At(0)) : nullptr;

            data.intVars["jet_nparticles"] = particles.size();
            for (const auto &p : particles) {
                data.vfloatVars.at("part_px")->push_back(p.px);
                data.vfloatVars.at("part_py")->push_back(p.py);
                data.vfloatVars.at("part_pz")->push_back(p.pz);
                data.vfloatVars.at("part_energy")->push_back(p.energy);
                data.vfloatVars.at("part_deta")->push_back((jet->Eta > 0 ? 1 : -1) * (p.eta - jet->Eta));
                data.vfloatVars.at("part_dphi")->push_back(deltaPhi(p.phi, jet->Phi));
                data.vfloatVars.at("part_d0val")->push_back(p.d0);
                data.vfloatVars.at("part_d0err")->push_back(p.d0err);
                data.vfloatVars.at("part_dzval")->push_back((pv && p.dz != 0) ? (p.dz - pv->Z) : p.dz);
                data.vfloatVars.at("part_dzerr")->push_back(p.dzerr);
                data.vintVars.at("part_charge")->push_back(p.charge);
                data.vboolVars.at("part_isElectron")->push_back(p.pid == 11 || p.pid == -11);
                data.vboolVars.at("part_isMuon")->push_back(p.pid == 13 || p.pid == -13);
                data.vboolVars.at("part_isPhoton")->push_back(p.pid == 22);
                data.vboolVars.at("part_isChargedHadron")->push_back(p.charge != 0 && !(p.pid == 11 || p.pid == -11 || p.pid == 13 || p.pid == -13));
                data.vboolVars.at("part_isNeutralHadron")->push_back(p.charge == 0 && !(p.pid == 22));
            }

            int hi = hltMatchIdx[si];
            if (hi >= 0) {
                fillHltJet(data, hltJetPtrs[hi], deltaR(jet, hltJetPtrs[hi]));
            } else {
                fillHltJet(data, nullptr, -999);
            }

            if (keepGenJet || keepGenParticles) {
                float min_dr = 999;
                int min_dr_index = -1;
                for (Int_t j = 0; j < offlineBranchGenJet->GetEntriesFast(); ++j) {
                    const Jet *genjet = (Jet *)offlineBranchGenJet->At(j);
                    float dr = deltaR(genjet, jet);
                    bool is_used = std::find(genjet_used_inds.begin(), genjet_used_inds.end(), j) != genjet_used_inds.end();
                    if (dr < min_dr && !is_used) { min_dr = dr; min_dr_index = j; }
                }
                if (min_dr < jetR) {
                    genjet_used_inds.push_back(min_dr_index);
                    const Jet *genjet = (Jet *)offlineBranchGenJet->At(min_dr_index);

                    std::vector<ParticleInfo> genparticles;
                    for (Int_t j = 0; j < genjet->Constituents.GetEntriesFast(); ++j) {
                        const TObject *object = genjet->Constituents.At(j);
                        if (!object) continue;
                        if (object->IsA() == GenParticle::Class()) {
                            genparticles.emplace_back((GenParticle *)object);
                        }
                        const auto &p = genparticles.back();
                        if (std::abs(p.pz) > 10000 || std::abs(p.eta) > 5 || p.pt <= 0) {
                            genparticles.pop_back();
                        }
                    }
                    std::sort(genparticles.begin(), genparticles.end(), [](const auto &a, const auto &b) { return a.pt > b.pt; });

                    if (keepGenJet) {
                        data.floatVars.at("genjet_pt") = genjet->PT;
                        data.floatVars.at("genjet_eta") = genjet->Eta;
                        data.floatVars.at("genjet_phi") = genjet->Phi;
                        data.floatVars.at("genjet_energy") = genjet->P4().Energy();
                        data.floatVars.at("genjet_sdmass") = genjet->SoftDroppedP4[0].M();
                        data.intVars["genjet_nparticles"] = genparticles.size();
                    }
                    if (keepGenParticles) {
                        for (const auto &p : genparticles) {
                            data.vfloatVars.at("genpart_px")->push_back(p.px);
                            data.vfloatVars.at("genpart_py")->push_back(p.py);
                            data.vfloatVars.at("genpart_pz")->push_back(p.pz);
                            data.vfloatVars.at("genpart_energy")->push_back(p.energy);
                            data.vfloatVars.at("genpart_jet_deta")->push_back((jet->Eta > 0 ? 1 : -1) * (p.eta - jet->Eta));
                            data.vfloatVars.at("genpart_jet_dphi")->push_back(deltaPhi(p.phi, jet->Phi));
                            data.vfloatVars.at("genpart_z")->push_back(pv ? (p.z - pv->Z) : p.z);
                            data.vfloatVars.at("genpart_t")->push_back(pv ? (p.t - pv->T) : p.t);
                            float absz = std::abs(pv ? (p.z - pv->Z) : p.z);
                            data.vfloatVars.at("genpart_x")->push_back(absz < 1e-10 ? 0. : p.x);
                            data.vfloatVars.at("genpart_y")->push_back(absz < 1e-10 ? 0. : p.y);
                            data.vintVars.at("genpart_pid")->push_back(p.pid);
                        }
                    }
                }
            }

            tree->Fill();
            ++num_processed;
        }
    }

    tree->Write();
    std::cerr << TString::Format("** Written %d jets (offline-selected, HLT-matched where possible) to output %s",
                                  num_processed, outputFile.Data()) << std::endl;

    delete offlineReader;
    delete offlineChain;
    delete hltReader;
    delete hltChain;
    delete fout;
}
