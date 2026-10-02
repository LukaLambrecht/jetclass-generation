#ifndef StandaloneTypes_h
#define StandaloneTypes_h

// Minimal stand-ins for the handful of Delphes classes the SHARED ntuplizer
// headers need, so that delphes_analyzers/FatJetMatching.h, ParticleInfo.h and
// ParticleID.h can be reused VERBATIM by a ntuplizer that has no Delphes at all
// (fullsim_analyzers/makeNtuplesFullSim.C, which reads CMSSW AODSIM instead).
//
// Why reuse rather than reimplement: FatJetMatching.h is ~1200 lines of subtle
// gen-level jet-labelling logic, validated against central JetClass. Writing a
// second copy of it against reco::GenParticle would be the single most likely
// place for the two backends' labels to silently drift apart. Instead the
// FullSim ntuplizer fills these structs from the CMSSW objects and runs the
// exact same labelling code. FatJetMatching.h picks this header up instead of
// classes/DelphesClasses.h when JETCLASS_STANDALONE_TYPES is defined.
//
// The only field set that matters is the one those three headers actually touch
// (checked exhaustively, they use nothing else):
//   GenParticle:              PID Status M1 M2 D1 D2 PT Eta Phi Mass Charge X Y Z T P4()
//   ParticleFlowCandidate:    PID Charge PT Eta Phi Mass D0 ErrorD0 DZ ErrorDZ
//   Jet:                      PT Eta Phi Mass P4()
//
// TObject base: FatJetMatching::getLabel() takes the gen-particle collection as
// a TObjArray (a TClonesArray IS-A TObjArray, so the Delphes callers are
// unaffected), which stores TObject*. Deriving from TObject is enough for
// TObjArray; no ROOT dictionary is needed, since these objects are never
// written to a file - they only ever live for the duration of one event.

#include <cmath>
#include "TObject.h"
#include "TObjArray.h"
#include "TVector2.h"
#include "TLorentzVector.h"

class GenParticle : public TObject {
public:
  int PID = 0;
  int Status = 0;
  int IsPU = 0;
  int M1 = -1;   // first/last mother index, Delphes convention (see makeNtuplesFullSim.C)
  int M2 = -1;
  int D1 = -1;   // first/last daughter index - getDaughters() walks the whole [D1, D2] RANGE
  int D2 = -1;
  int Charge = 0;
  float Mass = 0;
  float PT = 0;
  float Eta = 0;
  float Phi = 0;
  float E = 0;
  float X = 0;    // production vertex, mm (Delphes units)
  float Y = 0;
  float Z = 0;
  float T = 0;

  TLorentzVector P4() const {
    TLorentzVector v;
    v.SetPtEtaPhiM(PT, Eta, Phi, Mass);
    return v;
  }
};

class ParticleFlowCandidate : public TObject {
public:
  int PID = 0;
  int Charge = 0;
  float Mass = 0;
  float PT = 0;
  float Eta = 0;
  float Phi = 0;
  float E = 0;
  float D0 = 0;        // mm, Delphes sign convention - see makeNtuplesFullSim.C
  float ErrorD0 = 0;
  float DZ = 0;        // mm, w.r.t. the primary vertex
  float ErrorDZ = 0;

  TLorentzVector P4() const {
    TLorentzVector v;
    v.SetPtEtaPhiM(PT, Eta, Phi, Mass);
    return v;
  }
};

class Jet : public TObject {
public:
  float PT = 0;
  float Eta = 0;
  float Phi = 0;
  float Mass = 0;

  TLorentzVector P4() const {
    TLorentzVector v;
    v.SetPtEtaPhiM(PT, Eta, Phi, Mass);
    return v;
  }
};

#endif
