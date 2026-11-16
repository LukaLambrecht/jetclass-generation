// Count jets in a Delphes-level ROOT file at two stages, to isolate where jets get lost
// between two Delphes cards. Driven by test_hlt_vs_offline_njets.py, which runs this on
// the same events.hepmc through both cards, so any difference comes only from the
// detector modelling.
//
//   STAGE_A: raw entries in `jetBranch`, i.e. Delphes' own clustering result. The
//            clustering pT cut is identical in both cards, but the stored PT is after
//            the jet energy scale correction, which is not.
//   STAGE_B: of those, how many pass the same pT and |eta| cut makeNtuples.C applies
//            before writing a jet. Identical threshold in both cards.
//
// If STAGE_A already differs, jets are being lost before this cut runs - never
// clustered at all, an upstream tracking or particle-flow effect. If STAGE_A is similar
// but STAGE_B differs, the jets are clustered but their corrected PT falls below the
// shared threshold more often for one card, which is a jet-energy-scale effect
// surfacing through a shared cut rather than a different one.
//
// Also prints the STAGE_A jet PT mean and median, which show a scale shift directly,
// and the mean candidate multiplicity per event, which is the particle-level input to
// clustering.
//
// Usage:
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
