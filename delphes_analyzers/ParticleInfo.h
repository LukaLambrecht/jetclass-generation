#ifndef ParticleInfo_h
#define ParticleInfo_h

// Angular helpers and one flat view over the particle types the ntuplizers read.

// Signed phi difference, wrapped into (-pi, pi].
double deltaPhi(double phi1, double phi2) { return TVector2::Phi_mpi_pi(phi1 - phi2); }

// Angular distance in the (eta, phi) plane.
double deltaR(double eta1, double phi1, double eta2, double phi2) {
  double deta = eta1 - eta2;
  double dphi = deltaPhi(phi1, phi2);
  return std::hypot(deta, dphi);
}

// deltaR between any two objects exposing Eta and Phi.
template <class T1, class T2>
double deltaR(const T1 &a, const T2 &b) {
  return deltaR(a->Eta, a->Phi, b->Eta, b->Phi);
}

// One particle's kinematics and identity, built from either a generator particle or
// a reconstructed candidate, so the ntuplizers can fill their branches from a single
// type. Fields a given source does not carry keep their zero default: a GenParticle
// has no impact parameters, and a candidate has no production vertex.
struct ParticleInfo {
  // From a generator particle: adds the production vertex, no impact parameters.
  ParticleInfo(const GenParticle *particle) {
    pt = particle->PT;
    eta = particle->Eta;
    phi = particle->Phi;
    mass = particle->Mass;
    p4 = ROOT::Math::PtEtaPhiMVector(pt, eta, phi, mass);
    px = p4.px();
    py = p4.py();
    pz = p4.pz();
    energy = p4.energy();
    charge = particle->Charge;
    pid = particle->PID;
    x = particle->X;
    y = particle->Y;
    z = particle->Z;
    t = particle->T;
  }

  // From a reconstructed candidate: adds the impact parameters, no vertex.
  ParticleInfo(const ParticleFlowCandidate *particle) {
    pt = particle->PT;
    eta = particle->Eta;
    phi = particle->Phi;
    mass = particle->Mass;
    p4 = ROOT::Math::PtEtaPhiMVector(pt, eta, phi, mass);
    px = p4.px();
    py = p4.py();
    pz = p4.pz();
    energy = p4.energy();
    charge = particle->Charge;
    pid = particle->PID;
    d0 = particle->D0;
    d0err = particle->ErrorD0;
    dz = particle->DZ;
    dzerr = particle->ErrorDZ;
  }

  double pt;
  double eta;
  double phi;
  double mass;
  double px;
  double py;
  double pz;
  double energy;
  ROOT::Math::PtEtaPhiMVector p4;

  int charge;
  int pid;

  float d0 = 0;
  float d0err = 0;
  float dz = 0;
  float dzerr = 0;

  float x = 0;
  float y = 0;
  float z = 0;
  float t = 0;
};

#endif
