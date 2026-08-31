// Counts jets in a Delphes-level ROOT file at two stages, to isolate WHERE
// jets get lost between two Delphes cards (e.g. offline vs HLT) - driven by
// test_hlt_vs_offline_njets.py, which runs this on the *same* events.hepmc
// through both cards so any difference is attributable only to detector
// modeling, not independent proton collisions.
//
//   STAGE_A: raw entries in `jetBranch` - i.e. Delphes' own clustering
//            result (FastJetFinderPUPPIAK8's own JetPTMin=200 cut, applied
//            at clustering time, identical in both the offline and HLT
//            cards) - but the PT stored here is POST the
//            JetEnergyScalePUPPIAK8 correction module, which is NOT
//            identical between cards (see delphes_cards/
//            delphes_card_CMS_JetClassII_onlyFatJet_HLT_noPU.tcl's header
//            comment).
//   STAGE_B: of those, how many pass `PT >= ptCut && |Eta| <= etaCut` - the
//            SAME cut (same code, same default values) makeNtuples.C
//            itself applies before writing a jet to the ntuple. Identical
//            threshold in both cards, applied here exactly as there.
//
// If STAGE_A already differs a lot between cards, jets are being lost
// before this cut even runs (never clustered/surviving the shared 200 GeV
// clustering threshold in the first place - a tracking/PF-candidate
// upstream effect). If STAGE_A is similar but STAGE_B differs, jets ARE
// being clustered but their JES-corrected PT falls below the (identical)
// ptCut more often for one card - a downstream JES-correction effect
// surfacing through a shared threshold, not a different one.
//
// Also prints the STAGE_A jet PT mean/median (to show any JES-driven shift
// directly) and the mean ParticleFlowCandidate multiplicity per event (the
// upstream particle-level input to clustering, driven by
// ChargedHadronTrackingEfficiency and calorimeter response - see the HLT
// card's own header comment for the tracking-efficiency curves).
//
// Usage (matches makeNtuples.C's own ACLiC invocation style):
//   root -b -q "count_delphes_jets.C++(\"events_delphes.root\", \"JetPUPPIAK8\", 120, 2.5)"

#include <iostream>
#include <vector>
#include <algorithm>
#include <cmath>
#include "TChain.h"
#include "TString.h"
#include "TClonesArray.h"
#include "classes/DelphesClasses.h"
#include "ExRootAnalysis/ExRootTreeReader.h"

void count_delphes_jets(TString inputFile, TString jetBranch = "JetPUPPIAK8", double ptCut = 120, double etaCut = 2.5) {
    TChain *chain = new TChain("Delphes");
    chain->Add(inputFile);
    ExRootTreeReader *treeReader = new ExRootTreeReader(chain);
    Long64_t allEntries = treeReader->GetEntries();

    TClonesArray *branchJet = treeReader->UseBranch(jetBranch);
    TClonesArray *branchPFCand = treeReader->UseBranch("ParticleFlowCandidate");

    long stageA = 0, stageB = 0;
    long totalPFCand = 0;
    std::vector<double> pts;

    for (Long64_t entry = 0; entry < allEntries; ++entry) {
        treeReader->ReadEntry(entry);
        totalPFCand += branchPFCand->GetEntriesFast();
        for (Int_t i = 0; i < branchJet->GetEntriesFast(); ++i) {
            const Jet *jet = (Jet *)branchJet->At(i);
            stageA++;
            pts.push_back(jet->PT);
            if (jet->PT >= ptCut && std::abs(jet->Eta) <= etaCut) {
                stageB++;
            }
        }
    }

    std::sort(pts.begin(), pts.end());
    double ptMean = 0, ptMedian = 0;
    if (!pts.empty()) {
        for (double p : pts) ptMean += p;
        ptMean /= pts.size();
        ptMedian = pts[pts.size() / 2];
    }
    double pfcandMean = allEntries ? (double)totalPFCand / allEntries : 0;

    // parsed by test_hlt_vs_offline_njets.py - keep this exact "KEY value" format
    std::cout << "NEVENTS " << allEntries << std::endl;
    std::cout << "STAGE_A " << stageA << std::endl;
    std::cout << "STAGE_B " << stageB << std::endl;
    std::cout << "PT_MEAN " << ptMean << std::endl;
    std::cout << "PT_MEDIAN " << ptMedian << std::endl;
    std::cout << "PFCAND_MEAN " << pfcandMean << std::endl;
}
